

from __future__ import annotations

import structlog
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Dict, Optional, Protocol

from prometheus_client import Counter

from .evolution_client import EvolutionClient, EvolutionError, EvolutionOfflineError

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
        processo_id: Optional[int],
        status: str,
        payload_resposta: Optional[Dict[str, Any]] = None,
    ) -> None: ...

    async def agendar_envio_mensagem(
        self,
        escritorio_id: int,
        cliente_id: int,
        texto: str,
        processo_id: Optional[int],
        enviar_em: datetime,
        motivo: str,
    ) -> None:
        """
        Se você ainda não tiver scheduler, pode implementar como "TODO" no seu repo.
        A ideia é registrar no banco para um worker/beat enviar depois.
        """




# Config de horário

@dataclass(frozen=True)
class JanelaComercial:
    inicio: time = time(8, 0)
    fim: time = time(18, 0)



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
            return agora.replace(hour=self.janela_comercial.inicio.hour, minute=self.janela_comercial.inicio.minute, second=0, microsecond=0)
        # depois das 18h => próximo dia 08h
        proximo_dia = agora.replace(hour=self.janela_comercial.inicio.hour, minute=self.janela_comercial.inicio.minute, second=0, microsecond=0)
        return proximo_dia.replace(day=agora.day) if False else (proximo_dia + _um_dia(agora))

    async def _pode_enviar_agora(self, cliente_id: int, agora: datetime) -> tuple[bool, Optional[str]]:
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
        processo_id: Optional[int] = None,
        permitir_agendamento: bool = True,
    ) -> Dict[str, Any]:
        """
        Resolve instância do escritório e envia ao cliente.
        Se fora do horário comercial ou rate limit excedido, agenda (se permitir_agendamento).
        """
        agora = datetime.now()
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

            enviar_em = self._proxima_janela_comercial(agora) if motivo_bloqueio == "fora_horario_comercial" else agora.replace(hour=9, minute=0, second=0, microsecond=0)
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
            return {"ok": True, "agendado": True, "enviar_em": enviar_em.isoformat(), "motivo": motivo_bloqueio}

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
   

    async def enviar_notificacao_andamento(self, processo_id: int, andamento: str) -> Dict[str, Any]:
        """
        Você precisa que o seu RepositorioWhatsApp saiba:
        - mapear processo_id -> (escritorio_id, cliente_id)
        Se ainda não tiver, faça esse método no repo depois.
        """
        # TODO: implementar no repo: obter contexto do processo
        raise NotImplementedError("Implemente no repositório: obter (escritorio_id, cliente_id) pelo processo_id")

    async def enviar_boas_vindas(self, escritorio_id: int, cliente_id: int) -> Dict[str, Any]:
        texto = (
            "Olá! 👋 Seja bem-vindo(a).\n"
            "Este canal é para atualizações e dúvidas rápidas do seu atendimento.\n"
            "⚠️ Aviso: informações enviadas aqui não substituem orientação jurídica formal.\n"
            "Se precisar de algo, é só responder esta mensagem."
        )
        return await self.enviar_mensagem(escritorio_id, cliente_id, texto, processo_id=None)

    async def enviar_pesquisa_satisfacao(self, escritorio_id: int, cliente_id: int) -> Dict[str, Any]:
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

    async def enviar_sem_movimentacao(self, processo_id: int) -> Dict[str, Any]:
        # TODO: implementar quando seu repo mapear processo_id -> (escritorio_id, cliente_id)
        raise NotImplementedError("Implemente no repositório: obter (escritorio_id, cliente_id) pelo processo_id")



# Utils internas


def _um_dia(agora: datetime):
    # sem importar timedelta no topo para manter simples
    from datetime import timedelta
    return timedelta(days=1)