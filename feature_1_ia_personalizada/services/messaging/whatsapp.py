from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Protocol

import structlog
from prometheus_client import Counter
from sqlalchemy import func, select

from shared.database.connection import worker_session_factory
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio
from shared.models.interacao import Interacao
from shared.models.mensagem_agendada import MensagemAgendada
from shared.models.processo import Processo as ProcessoModel
from shared.utils.formatters import remover_emojis

from .evolution_client import EvolutionClient, EvolutionError, EvolutionOfflineError
from .templates import carregar_templates

logger = structlog.get_logger(__name__)

_mensagens_enviadas = Counter(
    "whatsapp_messages_sent_total",
    "Total de mensagens WhatsApp enviadas com sucesso via Evolution API",
    labelnames=["escritorio_id", "tipo"],
)


# Protocols (DB / Repositórios)


class RepositorioWhatsApp(Protocol):
    async def obter_instancia_por_escritorio(self, escritorio_id: int) -> str: ...
    async def obter_numero_cliente(self, cliente_id: int) -> str: ...

    async def obter_preferencia_horario_notificacao(self, cliente_id: int) -> str:
        """
        Retorna algo como:
        - "comercial"  (só 08-18)
        - "livre"      (qualquer horário)
        """

    async def contar_mensagens_enviadas_hoje(self, cliente_id: int) -> int: ...

    async def salvar_interacao(
        self,
        escritorio_id: int,
        cliente_id: int,
        texto: str,
        processo_id: int | None,
        status: str,
        payload_resposta: dict[str, Any] | None = None,
        metadata_extra: dict[str, Any] | None = None,
    ) -> None: ...

    async def agendar_envio_mensagem(
        self,
        escritorio_id: int,
        cliente_id: int,
        texto: str,
        processo_id: int | None,
        enviar_em: datetime,
        motivo: str,
    ) -> None:
        """
        Se você ainda não tiver scheduler, pode implementar como "TODO" no seu repo.
        A ideia é registrar no banco para um worker/beat enviar depois.
        """


# Config de horário


_FUSO_HORARIO_PADRAO = int(os.getenv("FUSO_HORARIO_PADRAO", "-3"))
_HORA_INICIO_ENVIO = int(os.getenv("HORA_INICIO_ENVIO", "8"))
_HORA_FIM_ENVIO = int(os.getenv("HORA_FIM_ENVIO", "20"))


@dataclass(frozen=True)
class JanelaComercial:
    inicio: time = time(_HORA_INICIO_ENVIO, 0)
    fim: time = time(_HORA_FIM_ENVIO, 0)


# Service


class WhatsAppService:
    """
    Wrapper de alto nível.
    - resolve instância do escritório
    - aplica horário comercial (se cliente preferir)
    - aplica rate limit (5 msgs/dia por cliente) (exceto respostas a perguntas, se você quiser sinalizar isso)
    - envia via EvolutionClient
    - salva interação
    """

    LIMITE_MENSAGENS_DIA_POR_CLIENTE = 5

    def __init__(
        self,
        evolution_client: EvolutionClient,
        repositorio: RepositorioWhatsApp,
        janela_comercial: JanelaComercial = JanelaComercial(),
    ) -> None:
        self.evolution_client = evolution_client
        self.repo = repositorio
        self.janela_comercial = janela_comercial

    # Regras: horário e limite

    def _esta_na_janela_comercial(self, agora: datetime) -> bool:
        t = agora.time()
        return self.janela_comercial.inicio <= t <= self.janela_comercial.fim

    def _proxima_janela_comercial(self, agora: datetime) -> datetime:
        """
        Se fora do horário, agenda para o próximo início (08:00).
        """
        if agora.time() < self.janela_comercial.inicio:
            return agora.replace(
                hour=self.janela_comercial.inicio.hour,
                minute=self.janela_comercial.inicio.minute,
                second=0,
                microsecond=0,
            )
        # depois das 18h => próximo dia 08h
        proximo_dia = agora.replace(
            hour=self.janela_comercial.inicio.hour,
            minute=self.janela_comercial.inicio.minute,
            second=0,
            microsecond=0,
        )
        return proximo_dia.replace(day=agora.day) if False else (proximo_dia + _um_dia(agora))

    async def _pode_enviar_agora(self, cliente_id: int, agora: datetime) -> tuple[bool, str | None]:
        preferencia = await self.repo.obter_preferencia_horario_notificacao(cliente_id)
        if preferencia == "comercial" and not self._esta_na_janela_comercial(agora):
            return False, "fora_horario_comercial"

        qtd = await self.repo.contar_mensagens_enviadas_hoje(cliente_id)
        if qtd >= self.LIMITE_MENSAGENS_DIA_POR_CLIENTE:
            return False, "rate_limit_diario"

        return True, None

    # API principal

    async def enviar_mensagem(
        self,
        escritorio_id: int,
        cliente_id: int,
        texto: str,
        processo_id: int | None = None,
        permitir_agendamento: bool = True,
    ) -> dict[str, Any]:
        """
        Resolve instância do escritório e envia ao cliente.
        Se fora do horário comercial ou rate limit excedido, agenda (se permitir_agendamento).
        """
        texto = remover_emojis(texto)  # cliente nunca recebe emoji
        agora = datetime.now(tz=timezone(timedelta(hours=_FUSO_HORARIO_PADRAO)))
        pode, motivo_bloqueio = await self._pode_enviar_agora(cliente_id, agora)

        if not pode:
            if not permitir_agendamento:
                await self.repo.salvar_interacao(
                    escritorio_id=escritorio_id,
                    cliente_id=cliente_id,
                    texto=texto,
                    processo_id=processo_id,
                    status=f"bloqueado:{motivo_bloqueio}",
                    payload_resposta=None,
                )
                return {"ok": False, "motivo": motivo_bloqueio}

            enviar_em = (
                self._proxima_janela_comercial(agora)
                if motivo_bloqueio == "fora_horario_comercial"
                else agora.replace(hour=9, minute=0, second=0, microsecond=0)
            )
            await self.repo.agendar_envio_mensagem(
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                texto=texto,
                processo_id=processo_id,
                enviar_em=enviar_em,
                motivo=motivo_bloqueio or "bloqueado",
            )
            await self.repo.salvar_interacao(
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                texto=texto,
                processo_id=processo_id,
                status=f"agendado:{motivo_bloqueio}",
                payload_resposta={"enviar_em": enviar_em.isoformat()},
            )
            return {
                "ok": True,
                "agendado": True,
                "enviar_em": enviar_em.isoformat(),
                "motivo": motivo_bloqueio,
            }

        # Envio normal
        instancia = await self.repo.obter_instancia_por_escritorio(escritorio_id)
        numero = await self.repo.obter_numero_cliente(cliente_id)

        try:
            resposta = await self.evolution_client.enviar_texto(instancia, numero, texto)
            await self.repo.salvar_interacao(
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                texto=texto,
                processo_id=processo_id,
                status="enviado",
                payload_resposta=resposta,
            )
            _mensagens_enviadas.labels(escritorio_id=str(escritorio_id), tipo="texto").inc()
            return {"ok": True, "agendado": False, "resposta": resposta}

        except EvolutionOfflineError as e:
            logger.warning(
                "whatsapp_instancia_offline",
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                erro=str(e),
            )
            await self.repo.salvar_interacao(
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                texto=texto,
                processo_id=processo_id,
                status="falha:instancia_offline",
                payload_resposta={"erro": str(e)},
            )
            return {"ok": False, "erro": "instancia_offline"}

        except EvolutionError as e:
            logger.error(
                "whatsapp_falha_evolution",
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                erro=str(e),
                exc_info=True,
            )
            await self.repo.salvar_interacao(
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                texto=texto,
                processo_id=processo_id,
                status="falha:evolution",
                payload_resposta={"erro": str(e)},
            )
            return {"ok": False, "erro": "evolution_error"}

    # Mensagens “prontas”

    async def _obter_contexto_processo(self, processo_id: int) -> tuple[int, int] | None:
        """Retorna (escritorio_id, cliente_id) do processo, ou None se não encontrado."""
        async with worker_session_factory() as session:
            result = await session.execute(
                select(ProcessoModel.escritorio_id, ProcessoModel.cliente_id).where(
                    ProcessoModel.id == processo_id
                )
            )
            row = result.one_or_none()
        if row is None:
            logger.warning("processo_nao_encontrado", processo_id=processo_id)
            return None
        return row.escritorio_id, row.cliente_id

    async def enviar_notificacao_andamento(
        self, processo_id: int, andamento: str
    ) -> dict[str, Any]:
        contexto = await self._obter_contexto_processo(processo_id)
        if contexto is None:
            return {"ok": False, "erro": "processo_nao_encontrado"}
        escritorio_id, cliente_id = contexto
        texto = (
            "Atualização do seu processo:\n\n"
            f"{andamento}\n\n"
            "Se desejar, posso explicar em linguagem mais simples."
        )
        return await self.enviar_mensagem(escritorio_id, cliente_id, texto, processo_id=processo_id)

    async def enviar_boas_vindas(self, escritorio_id: int, cliente_id: int) -> dict[str, Any]:
        async with worker_session_factory() as db:
            tmpl = await carregar_templates(escritorio_id, db=db)
        texto = tmpl["boas_vindas"]
        return await self.enviar_mensagem(escritorio_id, cliente_id, texto, processo_id=None)

    async def enviar_pesquisa_satisfacao(
        self, escritorio_id: int, cliente_id: int
    ) -> dict[str, Any]:
        """
        Pesquisa NPS (1-5) via botões.
        """
        instancia = await self.repo.obter_instancia_por_escritorio(escritorio_id)
        numero = await self.repo.obter_numero_cliente(cliente_id)

        texto = "De 1 a 5, como você avalia nosso atendimento hoje? (1 = ruim, 5 = excelente)"

        botoes = [
            {"buttonId": "nps_1", "buttonText": {"displayText": "1"}, "type": 1},
            {"buttonId": "nps_2", "buttonText": {"displayText": "2"}, "type": 1},
            {"buttonId": "nps_3", "buttonText": {"displayText": "3"}, "type": 1},
            {"buttonId": "nps_4", "buttonText": {"displayText": "4"}, "type": 1},
            {"buttonId": "nps_5", "buttonText": {"displayText": "5"}, "type": 1},
        ]

        try:
            resposta = await self.evolution_client.enviar_botoes(instancia, numero, texto, botoes)
            await self.repo.salvar_interacao(
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                texto=texto,
                processo_id=None,
                status="enviado:nps",
                payload_resposta=resposta,
                metadata_extra={"aguardando_nps": True},
            )
            return {"ok": True, "resposta": resposta}
        except EvolutionError as e:
            await self.repo.salvar_interacao(
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                texto=texto,
                processo_id=None,
                status="falha:nps",
                payload_resposta={"erro": str(e)},
            )
            return {"ok": False, "erro": "falha_envio_nps"}

    async def enviar_sem_movimentacao(self, processo_id: int) -> dict[str, Any]:
        contexto = await self._obter_contexto_processo(processo_id)
        if contexto is None:
            return {"ok": False, "erro": "processo_nao_encontrado"}
        escritorio_id, cliente_id = contexto
        async with worker_session_factory() as db:
            tmpl = await carregar_templates(escritorio_id, db=db)
        texto = tmpl["sem_novidade"]
        return await self.enviar_mensagem(escritorio_id, cliente_id, texto, processo_id=processo_id)


# Utils internas


def _um_dia(agora: datetime) -> timedelta:
    # sem importar timedelta no topo para manter simples
    from datetime import timedelta

    return timedelta(days=1)


class SQLWhatsAppRepository:
    """Implementa as rotinas de banco de dados para os envios de mensagens."""

    async def obter_instancia_por_escritorio(self, escritorio_id: int) -> str:
        async with worker_session_factory() as session:
            result = await session.execute(
                select(Escritorio.webhook_whatsapp_instance).where(Escritorio.id == escritorio_id)
            )
            val = result.scalar_one_or_none()
        if not val:
            raise ValueError(
                f"Escritório {escritorio_id} não possui instância do WhatsApp configurada."
            )
        return str(val)

    async def obter_numero_cliente(self, cliente_id: int) -> str:
        async with worker_session_factory() as session:
            result = await session.execute(
                select(Cliente.telefone_whatsapp).where(Cliente.id == cliente_id)
            )
            val = result.scalar_one_or_none()
        if not val:
            raise ValueError(f"Cliente {cliente_id} não encontrado ou sem telefone.")
        return str(val)

    async def obter_preferencia_horario_notificacao(self, cliente_id: int) -> str:
        async with worker_session_factory() as session:
            result = await session.execute(
                select(Cliente.preferencia_horario_notificacao).where(Cliente.id == cliente_id)
            )
            val = result.scalar_one_or_none()
        return val or "comercial"

    async def contar_mensagens_enviadas_hoje(self, cliente_id: int) -> int:
        hj = datetime.now().date()
        async with worker_session_factory() as session:
            result = await session.execute(
                select(func.count(Interacao.id)).where(
                    Interacao.cliente_id == cliente_id,
                    Interacao.direcao == "saida",
                    func.date(Interacao.created_at) == hj,
                )
            )
            qtd = result.scalar()
        return int(qtd) if qtd else 0

    async def salvar_interacao(
        self,
        escritorio_id: int,
        cliente_id: int,
        texto: str,
        processo_id: int | None,
        status: str,
        payload_resposta: dict[str, Any] | None = None,
        metadata_extra: dict[str, Any] | None = None,
    ) -> None:
        metadata: dict[str, Any] = {"status": status}
        if payload_resposta:
            metadata["payload_resposta"] = payload_resposta
        if metadata_extra:
            metadata.update(metadata_extra)

        async with worker_session_factory() as session:
            interacao = Interacao(
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                processo_id=processo_id,
                tipo="whatsapp_texto",  # Simplificado para padrão de saída
                direcao="saida",
                mensagem_ia=texto,
                metadata_json=metadata,
            )
            session.add(interacao)
            await session.commit()

    async def agendar_envio_mensagem(
        self,
        escritorio_id: int,
        cliente_id: int,
        texto: str,
        processo_id: int | None,
        enviar_em: datetime,
        motivo: str,
    ) -> None:
        async with worker_session_factory() as session:
            agendada = MensagemAgendada(
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                processo_id=processo_id,
                texto=texto,
                motivo=motivo,
                enviar_em=enviar_em,
                status="pendente",
                tentativas=0,
            )
            session.add(agendada)
            await session.commit()
        logger.info(
            "mensagem_agendada",
            cliente_id=cliente_id,
            enviar_em=enviar_em.isoformat(),
            motivo=motivo,
        )
