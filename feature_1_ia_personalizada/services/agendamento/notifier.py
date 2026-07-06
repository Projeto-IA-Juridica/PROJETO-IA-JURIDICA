"""
AgendamentoNotifier — todas as mensagens WhatsApp do fluxo de agendamento.

| Método                            | Destinatário       | Flag de idempotência                      |
|-----------------------------------|--------------------|-------------------------------------------|
| enviar_proposta_cliente           | Cliente            | whatsapp_proposta_cliente_enviado          |
| enviar_notificacao_advogado       | Advogado           | whatsapp_notificacao_advogado_enviado      |
| enviar_confirmacao_cliente        | Cliente            | whatsapp_confirmacao_cliente_enviado       |
| enviar_confirmacao_pre_reuniao    | Cliente            | whatsapp_confirmacao_pre_reuniao_enviado   |
| enviar_cancelamento               | Cliente            | —                                          |
| enviar_lembrete                   | Cliente + Advogado | dedup via Redis no worker                  |
| processar_resposta_advogado       | —                  | Redis SET NX agendamento_confirmar:{id}    |
| processar_resposta_cliente        | —                  | transição de status                        |

Regras críticas:
  - "Primeiro canal ganha": lock Redis `agendamento_confirmar:{id}` (TTL 30s)
    impede dupla confirmação Hub + WhatsApp simultânea.
  - Transições de estado são COMMITADAS antes do envio das mensagens —
    persistência primeiro, notificação depois (at-least-once).
  - Regex barata antes de Claude: só gasta tokens quando o texto é ambíguo.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.messaging.evolution_client import EvolutionClient
from shared.models.agendamento import Agendamento
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Métricas (opcionais — nunca quebram o fluxo)
# ---------------------------------------------------------------------------

try:
    from feature_1_ia_personalizada.api.routes.metrics import (
        agendamentos_confirmados_total,
        tempo_aprovacao_advogado_segundos,
    )
except Exception:  # pragma: no cover — métricas indisponíveis em alguns contextos
    agendamentos_confirmados_total = None  # type: ignore[assignment]
    tempo_aprovacao_advogado_segundos = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Interpretação de respostas (regex antes de Claude — economiza tokens)
# ---------------------------------------------------------------------------

CONFIRMAR = re.compile(r"\b(1|sim|confirmar?|ok|pode|confirmado|aprovado?)\b", re.IGNORECASE)
RECUSAR = re.compile(r"\b(2|n[aã]o|recusar?|cancelar?|nao)\b", re.IGNORECASE)

# Cliente escolhendo opção: mensagem inteira é "1"/"2"/"3" (com ruído leve)
_RE_ESCOLHA_ISOLADA = re.compile(
    r"^\s*(?:op[çc][aã]o\s*)?([1-3])[ªa°]?\s*[.!)]*\s*$", re.IGNORECASE
)
_RE_ESCOLHA_FRASE = re.compile(r"\bop[çc][aã]o\s*([1-3])\b", re.IGNORECASE)

_LOCK_TTL_S = 30
_PROPOSTA_TTL_H = 48

_PROMPT_INTERPRETAR_ADVOGADO = (
    "Você interpreta a resposta de um advogado a uma solicitação de reunião "
    "enviada por WhatsApp. Ele deveria responder 1 (confirmar) ou 2 (recusar), "
    "mas escreveu em linguagem natural.\n\n"
    "Responda EXCLUSIVAMENTE com JSON válido, sem texto adicional.\n"
    'Formato: {"acao": "confirmar"} ou {"acao": "recusar"} ou {"acao": "outro"}\n'
    'Use "outro" quando a mensagem não expressar claramente confirmação nem recusa.'
)


def _prompt_interpretar_cliente(labels: list[str]) -> str:
    opcoes = "\n".join(f"{i + 1}) {label}" for i, label in enumerate(labels))
    return (
        "Você interpreta a resposta de um cliente a uma proposta de horários de reunião "
        "enviada por WhatsApp. As opções oferecidas foram:\n"
        f"{opcoes}\n\n"
        "Responda EXCLUSIVAMENTE com JSON válido, sem texto adicional.\n"
        'Formato: {"opcao": <1|2|3|0>}\n'
        "Use 0 quando a mensagem NÃO escolher claramente uma das opções "
        "(ex: é outra pergunta, ou o cliente diz que nenhum horário serve)."
    )


# ---------------------------------------------------------------------------
# Normalização de números
# ---------------------------------------------------------------------------


def _apenas_digitos(numero: str | None) -> str:
    return re.sub(r"\D", "", numero or "")


def _aware(dt: datetime | None) -> datetime | None:
    """Normaliza datetimes lidos do banco — SQLite (testes) devolve naive; assume UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def normalizar_numero_whatsapp(numero: str | None) -> str:
    """Formato aceito pela Evolution: código do país + DDD + número."""
    dig = _apenas_digitos(numero)
    if len(dig) in (10, 11):  # DDD + número, sem código do país (BR)
        dig = "55" + dig
    return dig


def _nucleo_numero(dig: str) -> tuple[str | None, str]:
    """Retorna (DDD, últimos 8 dígitos) tolerando código do país e nono dígito."""
    dig = dig.lstrip("0")
    if dig.startswith("55") and len(dig) >= 12:
        dig = dig[2:]
    ddd = dig[:2] if len(dig) >= 10 else None
    return ddd, dig[-8:]


def mesmo_numero(a: str | None, b: str | None) -> bool:
    """Compara números tolerando formatação, código do país e nono dígito."""
    da, db = _apenas_digitos(a), _apenas_digitos(b)
    if len(da) < 8 or len(db) < 8:
        return False
    ddd_a, nucleo_a = _nucleo_numero(da)
    ddd_b, nucleo_b = _nucleo_numero(db)
    if nucleo_a != nucleo_b:
        return False
    if ddd_a and ddd_b and ddd_a != ddd_b:
        return False
    return True


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_EMOJIS_OPCAO = ["1️⃣", "2️⃣", "3️⃣"]


def montar_mensagem_proposta(
    nome_cliente: str,
    opcoes: list[dict[str, Any]],
    reproposta: bool = False,
) -> str:
    primeiro_nome = nome_cliente.split(" ")[0] if nome_cliente else ""
    linhas = []
    for i, op in enumerate(opcoes[:3]):
        emoji = _EMOJIS_OPCAO[i] if i < len(_EMOJIS_OPCAO) else f"{i + 1})"
        linhas.append(f"{emoji}  {op.get('label', '')}")
    corpo = "\n".join(linhas)

    if reproposta:
        intro = (
            f"Olá, {primeiro_nome}! O advogado precisou ajustar a agenda "
            "e me pediu para sugerir novos horários para a reunião:"
        )
    else:
        intro = (
            f"Olá, {primeiro_nome}! Para agendarmos nossa conversa, "
            "tenho os seguintes horários disponíveis:"
        )

    return f"{intro}\n\n{corpo}\n\n" "É só responder com o número da opção (1, 2 ou 3). 😊"


def _label_opcao_selecionada(ag: Agendamento) -> str:
    if ag.opcoes_propostas and ag.opcao_selecionada_pos is not None:
        try:
            return str(ag.opcoes_propostas[ag.opcao_selecionada_pos].get("label", ""))
        except (IndexError, TypeError):
            pass
    if ag.data_hora_inicio:
        return ag.data_hora_inicio.strftime("%d/%m às %Hh (UTC)")
    return "horário a confirmar"


def _formatar_local(dt_utc: datetime, tz_str: str) -> tuple[str, str]:
    """Retorna (data 'dd/mm', hora 'HHhMM'|'HHh') no fuso do escritório."""
    local = dt_utc.astimezone(ZoneInfo(tz_str))
    hora = local.strftime("%Hh%M") if local.minute else local.strftime("%Hh")
    return local.strftime("%d/%m"), hora


class AgendamentoNotifier:
    """
    Envia mensagens WhatsApp do fluxo de agendamento e processa respostas.

    session: sessão async (o notifier COMMITA transições de estado).
    evolution: cliente Evolution API já configurado.
    redis: usado para o lock atômico de aprovação (SET NX). Opcional em testes.
    claude: usado como fallback de interpretação em linguagem natural. Opcional.
    """

    def __init__(
        self,
        session: AsyncSession,
        evolution: EvolutionClient,
        redis: Any = None,
        claude: Any = None,
    ) -> None:
        self._db = session
        self._evolution = evolution
        self._redis = redis
        self._claude = claude

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    async def _carregar_contexto(self, ag: Agendamento) -> tuple[Escritorio | None, Cliente | None]:
        escritorio = await self._db.get(Escritorio, ag.escritorio_id)
        cliente = await self._db.get(Cliente, ag.cliente_id)
        return escritorio, cliente

    async def _enviar(self, instance: str | None, numero: str | None, texto: str) -> bool:
        if not instance or not numero:
            logger.warning("agendamento_envio_sem_destino", instance=bool(instance))
            return False
        try:
            await self._evolution.enviar_texto(instance, normalizar_numero_whatsapp(numero), texto)
            return True
        except Exception as exc:
            logger.error("agendamento_envio_falhou", erro=str(exc))
            return False

    async def _interpretar_com_claude(self, system_prompt: str, texto: str) -> dict[str, Any]:
        if self._claude is None:
            return {}
        try:
            raw = await self._claude.classificar_intencao(
                system_prompt=system_prompt, mensagem=texto
            )
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("agendamento_claude_interpretacao_falhou", erro=str(exc))
            return {}

    # ------------------------------------------------------------------
    # Envios ao cliente
    # ------------------------------------------------------------------

    async def enviar_proposta_cliente(self, ag: Agendamento, reproposta: bool = False) -> bool:
        """Envia as 3 opções ao cliente. Idempotente pela flag."""
        if ag.whatsapp_proposta_cliente_enviado:
            return False
        escritorio, cliente = await self._carregar_contexto(ag)
        if not escritorio or not cliente or not ag.opcoes_propostas:
            return False

        texto = montar_mensagem_proposta(cliente.nome, ag.opcoes_propostas, reproposta=reproposta)
        ok = await self._enviar(
            escritorio.webhook_whatsapp_instance, cliente.telefone_whatsapp, texto
        )
        if ok:
            ag.whatsapp_proposta_cliente_enviado = True
            ag.proposta_enviada_em = datetime.now(UTC)
            await self._db.commit()
        return ok

    async def enviar_confirmacao_cliente(self, ag: Agendamento) -> bool:
        """Confirmação formal após aval do advogado. Idempotente pela flag."""
        if ag.whatsapp_confirmacao_cliente_enviado or not ag.data_hora_inicio:
            return False
        escritorio, cliente = await self._carregar_contexto(ag)
        if not escritorio or not cliente:
            return False

        data_str, hora_str = _formatar_local(ag.data_hora_inicio, escritorio.timezone)
        responsavel = escritorio.nome_responsavel or escritorio.nome
        texto = (
            "✅ *Reunião confirmada!*\n\n"
            f"📅 {_label_opcao_selecionada(ag)}\n"
            f"👤 Dr(a). {responsavel}\n"
            f"📋 Assunto: conversar sobre seu processo\n\n"
            f"Até {data_str} às {hora_str}! Qualquer imprevisto, é só avisar por aqui. 😊"
        )
        ok = await self._enviar(
            escritorio.webhook_whatsapp_instance, cliente.telefone_whatsapp, texto
        )
        if ok:
            ag.whatsapp_confirmacao_cliente_enviado = True
            await self._db.commit()
        return ok

    async def enviar_confirmacao_pre_reuniao(self, ag: Agendamento) -> bool:
        """Lembrete leve 3h antes — reduz no-show. Idempotente pela flag."""
        if ag.whatsapp_confirmacao_pre_reuniao_enviado or not ag.data_hora_inicio:
            return False
        escritorio, cliente = await self._carregar_contexto(ag)
        if not escritorio or not cliente:
            return False

        _, hora_str = _formatar_local(ag.data_hora_inicio, escritorio.timezone)
        responsavel = escritorio.nome_responsavel or escritorio.nome
        primeiro_nome = cliente.nome.split(" ")[0]
        texto = (
            f"Olá, {primeiro_nome}! Só passando para lembrar da sua reunião "
            f"com Dr(a). {responsavel} hoje às {hora_str}. 😊\n\n"
            "Qualquer imprevisto, é só avisar aqui!"
        )
        ok = await self._enviar(
            escritorio.webhook_whatsapp_instance, cliente.telefone_whatsapp, texto
        )
        if ok:
            ag.whatsapp_confirmacao_pre_reuniao_enviado = True
            await self._db.commit()
        return ok

    async def enviar_cancelamento(self, ag: Agendamento) -> bool:
        """Avisa o cliente que o horário não pôde ser confirmado."""
        escritorio, cliente = await self._carregar_contexto(ag)
        if not escritorio or not cliente:
            return False
        primeiro_nome = cliente.nome.split(" ")[0]
        texto = (
            f"Olá, {primeiro_nome}. Infelizmente o horário solicitado não pôde "
            "ser confirmado desta vez. 🙏\n\n"
            "Em breve entraremos em contato para combinar uma nova data. "
            "Se preferir, me diga aqui qual período costuma ser melhor para você."
        )
        return await self._enviar(
            escritorio.webhook_whatsapp_instance, cliente.telefone_whatsapp, texto
        )

    async def enviar_lembrete(self, ag: Agendamento) -> bool:
        """Lembrete 24h antes — cliente E advogado (dedup fica no worker)."""
        if not ag.data_hora_inicio:
            return False
        escritorio, cliente = await self._carregar_contexto(ag)
        if not escritorio or not cliente:
            return False

        data_str, hora_str = _formatar_local(ag.data_hora_inicio, escritorio.timezone)
        primeiro_nome = cliente.nome.split(" ")[0]
        instance = escritorio.webhook_whatsapp_instance

        ok_cliente = await self._enviar(
            instance,
            cliente.telefone_whatsapp,
            f"Olá, {primeiro_nome}! Lembrete: sua reunião com o escritório é amanhã, "
            f"{data_str} às {hora_str}. Até lá! 😊",
        )
        ok_advogado = True
        if escritorio.telefone_advogado:
            ok_advogado = await self._enviar(
                instance,
                escritorio.telefone_advogado,
                f"📅 Lembrete: reunião com *{cliente.nome}* amanhã, {data_str} às {hora_str}.",
            )
        return ok_cliente and ok_advogado

    # ------------------------------------------------------------------
    # Envio ao advogado
    # ------------------------------------------------------------------

    async def enviar_notificacao_advogado(
        self, ag: Agendamento, conflito_descricao: str | None = None
    ) -> bool:
        """
        Solicita a aprovação do advogado via WhatsApp (espelho do card do Hub).
        Idempotente pela flag whatsapp_notificacao_advogado_enviado.
        """
        if ag.whatsapp_notificacao_advogado_enviado:
            return False
        escritorio, cliente = await self._carregar_contexto(ag)
        if not escritorio or not cliente:
            return False
        if not escritorio.telefone_advogado:
            logger.warning(
                "agendamento_sem_telefone_advogado",
                escritorio_id=ag.escritorio_id,
                agendamento_id=ag.id,
            )
            return False

        partes = [
            "📅 *Solicitação de reunião*",
            "",
            f"Cliente: {cliente.nome}",
            f"Horário: {_label_opcao_selecionada(ag)}",
        ]
        if ag.motivo_cliente:
            partes += ["", f'Motivo: "{ag.motivo_cliente}"']
        if conflito_descricao:
            partes += ["", f"⚠️ {conflito_descricao} — verifique a agenda antes de confirmar."]
        partes += ["", "Responda *1* para confirmar ou *2* para recusar."]

        ok = await self._enviar(
            escritorio.webhook_whatsapp_instance,
            escritorio.telefone_advogado,
            "\n".join(partes),
        )
        if ok:
            ag.whatsapp_notificacao_advogado_enviado = True
            await self._db.commit()
        return ok

    # ------------------------------------------------------------------
    # Resposta do ADVOGADO (webhook WhatsApp)
    # ------------------------------------------------------------------

    async def processar_resposta_advogado(self, texto: str, escritorio_id: int) -> dict[str, Any]:
        """
        Processa "1"/"sim"/"2"/"não" (ou linguagem natural via Claude) do advogado.

        Primeiro canal ganha: lock Redis agendamento_confirmar:{id}; se o Hub
        confirmou antes, responde "já confirmada" sem re-processar.
        """
        escritorio = await self._db.get(Escritorio, escritorio_id)
        if not escritorio:
            return {"status": "escritorio_nao_encontrado"}
        instance = escritorio.webhook_whatsapp_instance
        numero_advogado = escritorio.telefone_advogado

        ag = (
            await self._db.execute(
                select(Agendamento)
                .where(
                    Agendamento.escritorio_id == escritorio_id,
                    Agendamento.status == "aguardando_advogado",
                    Agendamento.whatsapp_notificacao_advogado_enviado.is_(True),
                )
                .order_by(Agendamento.resposta_cliente_em.desc().nullslast())
                .limit(1)
            )
        ).scalar_one_or_none()

        if ag is None:
            # Sem pendências — se o Hub acabou de confirmar, informa (sincronização entre canais)
            recente = (
                await self._db.execute(
                    select(Agendamento)
                    .where(
                        Agendamento.escritorio_id == escritorio_id,
                        Agendamento.status == "confirmado",
                        Agendamento.canal_aprovacao == "hub",
                    )
                    .order_by(Agendamento.resposta_advogado_em.desc().nullslast())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if recente is not None:
                await self._enviar(
                    instance,
                    numero_advogado,
                    "Reunião já confirmada pelo sistema! ✅ Até lá.",
                )
                return {"status": "ja_confirmado", "agendamento_id": recente.id}
            return {"status": "sem_pendencias"}

        acao = self._interpretar_resposta_advogado_regex(texto)
        if acao == "outro":
            resultado = await self._interpretar_com_claude(_PROMPT_INTERPRETAR_ADVOGADO, texto)
            acao = resultado.get("acao", "outro")
        if acao not in {"confirmar", "recusar"}:
            cliente_pend = await self._db.get(Cliente, ag.cliente_id)
            nome_pend = cliente_pend.nome if cliente_pend else f"cliente #{ag.cliente_id}"
            await self._enviar(
                instance,
                numero_advogado,
                f"Não entendi. Sobre a reunião com *{nome_pend}*: "
                "responda *1* para confirmar ou *2* para recusar.",
            )
            return {"status": "nao_entendido", "agendamento_id": ag.id}

        # Lock atômico — primeiro canal ganha
        lock_key = f"agendamento_confirmar:{ag.id}"
        if self._redis is not None:
            adquirido = await self._redis.set(lock_key, "whatsapp", ex=_LOCK_TTL_S, nx=True)
            if not adquirido:
                await self._db.refresh(ag)
                if ag.status == "confirmado":
                    await self._enviar(
                        instance, numero_advogado, "Reunião já confirmada pelo sistema! ✅ Até lá."
                    )
                    return {"status": "ja_confirmado", "agendamento_id": ag.id}
                await self._enviar(
                    instance,
                    numero_advogado,
                    "Estou processando outra ação neste agendamento — tente novamente em instantes.",
                )
                return {"status": "lock_ocupado", "agendamento_id": ag.id}

        try:
            await self._db.refresh(ag)
            if ag.status != "aguardando_advogado":
                if ag.status == "confirmado":
                    await self._enviar(
                        instance, numero_advogado, "Reunião já confirmada pelo sistema! ✅ Até lá."
                    )
                    return {"status": "ja_confirmado", "agendamento_id": ag.id}
                return {"status": f"status_invalido:{ag.status}", "agendamento_id": ag.id}

            cliente = await self._db.get(Cliente, ag.cliente_id)
            nome_cliente = cliente.nome if cliente else f"cliente #{ag.cliente_id}"

            if acao == "confirmar":
                pos = ag.opcao_selecionada_pos
                if pos is None or not ag.opcoes_propostas or pos >= len(ag.opcoes_propostas):
                    return {"status": "sem_opcao_selecionada", "agendamento_id": ag.id}
                opcao = ag.opcoes_propostas[pos]
                agora = datetime.now(UTC)
                ag.status = "confirmado"
                ag.canal_aprovacao = "whatsapp"
                ag.resposta_advogado_em = agora
                ag.data_hora_inicio = datetime.fromisoformat(opcao["inicio"])
                ag.data_hora_fim = datetime.fromisoformat(opcao["fim"])
                await self._db.commit()

                _registrar_confirmacao_metricas(ag, agora)

                await self.enviar_confirmacao_cliente(ag)
                await self._enviar(
                    instance,
                    numero_advogado,
                    f"✅ Reunião com *{nome_cliente}* confirmada "
                    f"({_label_opcao_selecionada(ag)}). O cliente foi avisado."
                    + await self._sufixo_pendencias_restantes(escritorio_id),
                )
                logger.info(
                    "agendamento_confirmado",
                    id=ag.id,
                    canal="whatsapp",
                    escritorio_id=escritorio_id,
                )
                return {"status": "confirmado", "agendamento_id": ag.id}

            # acao == "recusar"
            ag.status = "cancelado"
            ag.canal_aprovacao = "whatsapp"
            ag.resposta_advogado_em = datetime.now(UTC)
            ag.motivo_cancelamento = "Recusado pelo advogado via WhatsApp"
            await self._db.commit()

            await self.enviar_cancelamento(ag)
            await self._enviar(
                instance,
                numero_advogado,
                f"Ok, recusei a solicitação de *{nome_cliente}* e avisei o cliente. "
                "Se preferir sugerir novos horários, use o Hub."
                + await self._sufixo_pendencias_restantes(escritorio_id),
            )
            logger.info(
                "agendamento_recusado", id=ag.id, canal="whatsapp", escritorio_id=escritorio_id
            )
            return {"status": "recusado", "agendamento_id": ag.id}
        finally:
            if self._redis is not None:
                try:
                    await self._redis.delete(lock_key)
                except Exception:
                    pass

    async def _sufixo_pendencias_restantes(self, escritorio_id: int) -> str:
        """
        Avisa o advogado quando ainda há outras solicitações na fila e mostra
        a próxima — permite despachar a fila inteira respondendo 1/2 no WhatsApp
        (processar_resposta_advogado sempre pega a pendência mais recente).
        """
        try:
            restantes = (
                (
                    await self._db.execute(
                        select(Agendamento)
                        .where(
                            Agendamento.escritorio_id == escritorio_id,
                            Agendamento.status == "aguardando_advogado",
                        )
                        .order_by(Agendamento.resposta_cliente_em.desc().nullslast())
                    )
                )
                .scalars()
                .all()
            )
        except Exception:
            return ""
        if not restantes:
            return ""

        proxima = restantes[0]
        cliente = await self._db.get(Cliente, proxima.cliente_id)
        nome = cliente.nome if cliente else f"cliente #{proxima.cliente_id}"
        plural = (
            f"Há mais *{len(restantes)}* solicitações"
            if len(restantes) > 1
            else ("Há mais *1* solicitação")
        )
        return (
            f"\n\n📋 {plural} aguardando. Próxima: *{nome}* — "
            f"{_label_opcao_selecionada(proxima)}. "
            "Responda *1* para confirmar ou *2* para recusar, ou use o Hub."
        )

    @staticmethod
    def _interpretar_resposta_advogado_regex(texto: str) -> str:
        confirma = bool(CONFIRMAR.search(texto))
        recusa = bool(RECUSAR.search(texto))
        if confirma and not recusa:
            return "confirmar"
        if recusa and not confirma:
            return "recusar"
        return "outro"

    # ------------------------------------------------------------------
    # Resposta do CLIENTE (escolha da opção 1/2/3)
    # ------------------------------------------------------------------

    async def processar_resposta_cliente(
        self, escritorio_id: int, cliente_id: int, texto: str
    ) -> str | None:
        """
        Se o cliente tem proposta pendente e o texto escolhe uma opção,
        efetiva a transição aguardando_cliente → aguardando_advogado,
        popula data_hora_inicio/fim e notifica o advogado (WhatsApp + Hub).

        Retorna o texto de resposta ao cliente quando a mensagem foi tratada,
        ou None para a mensagem seguir o fluxo normal da IA.
        """
        ag = (
            await self._db.execute(
                select(Agendamento)
                .where(
                    Agendamento.escritorio_id == escritorio_id,
                    Agendamento.cliente_id == cliente_id,
                    Agendamento.status == "aguardando_cliente",
                    Agendamento.whatsapp_proposta_cliente_enviado.is_(True),
                )
                .order_by(Agendamento.proposta_enviada_em.desc().nullslast())
                .limit(1)
            )
        ).scalar_one_or_none()

        if ag is None or not ag.opcoes_propostas:
            return None
        expira_em = _aware(ag.expira_em)
        if expira_em and expira_em <= datetime.now(UTC):
            return None  # worker expirar_propostas cuidará do status

        pos = self._extrair_escolha(texto, ag.opcoes_propostas)
        if pos is None:
            resultado = await self._interpretar_com_claude(
                _prompt_interpretar_cliente(
                    [str(op.get("label", "")) for op in ag.opcoes_propostas]
                ),
                texto,
            )
            try:
                opcao_claude = int(resultado.get("opcao", 0))
            except (TypeError, ValueError):
                opcao_claude = 0
            if 1 <= opcao_claude <= len(ag.opcoes_propostas):
                pos = opcao_claude - 1

        if pos is None or pos >= len(ag.opcoes_propostas):
            return None  # não é uma escolha — segue fluxo normal da IA

        opcao = ag.opcoes_propostas[pos]
        inicio = datetime.fromisoformat(opcao["inicio"])
        fim = datetime.fromisoformat(opcao["fim"])

        # Slot no passado (cliente respondeu perto do fim das 48h) ou ocupado
        # nesse meio-tempo por outro cliente → regenera opções na hora, sem
        # deixar o advogado receber pedido de horário inválido.
        if inicio <= datetime.now(UTC):
            return await self._repropor_por_indisponibilidade(ag, motivo="passou")
        if await self._slot_ocupado(ag, inicio, fim):
            return await self._repropor_por_indisponibilidade(ag, motivo="ocupado")

        ag.opcao_selecionada_pos = pos
        ag.status = "aguardando_advogado"
        ag.resposta_cliente_em = datetime.now(UTC)
        # Popular data_hora ativa o Caso 1 do detector para conflitos futuros
        ag.data_hora_inicio = inicio
        ag.data_hora_fim = fim
        await self._db.commit()

        conflito = None
        if opcao.get("conflito_prazo"):
            conflito = "Este horário cai próximo a um prazo processual do cliente"
        await self.enviar_notificacao_advogado(ag, conflito_descricao=conflito)

        cliente = await self._db.get(Cliente, cliente_id)
        primeiro_nome = cliente.nome.split(" ")[0] if cliente else ""
        logger.info(
            "agendamento_cliente_escolheu",
            id=ag.id,
            opcao=pos,
            escritorio_id=escritorio_id,
        )
        return (
            f"Perfeito, {primeiro_nome}! Anotei *{opcao.get('label', '')}*. 📅\n\n"
            "Vou confirmar a disponibilidade com o advogado e te aviso "
            "por aqui assim que estiver tudo certo. 😊"
        )

    async def _slot_ocupado(self, ag: Agendamento, inicio: datetime, fim: datetime) -> bool:
        """Outro agendamento (confirmado ou aguardando aval) já tomou o horário?"""
        row = (
            await self._db.execute(
                select(Agendamento.id)
                .where(
                    Agendamento.escritorio_id == ag.escritorio_id,
                    Agendamento.id != ag.id,
                    Agendamento.status.in_(["confirmado", "aguardando_advogado"]),
                    Agendamento.data_hora_inicio.isnot(None),
                    Agendamento.data_hora_fim.isnot(None),
                    Agendamento.data_hora_inicio < fim,
                    Agendamento.data_hora_fim > inicio,
                )
                .limit(1)
            )
        ).first()
        return row is not None

    async def _repropor_por_indisponibilidade(self, ag: Agendamento, motivo: str) -> str:
        """
        O slot escolhido não está mais disponível (passou ou foi ocupado por
        outro cliente). Gera 3 novas opções imediatamente — o cliente não fica
        preso a uma proposta inválida e o advogado não recebe pedido impossível.
        """
        from feature_1_ia_personalizada.services.agendamento.detector import AgendamentoDetector
        from feature_1_ia_personalizada.services.agendamento.prazos import (
            buscar_prazos_escritorio,
            datas_a_evitar,
        )

        escritorio, cliente = await self._carregar_contexto(ag)
        primeiro_nome = cliente.nome.split(" ")[0] if cliente else ""

        intro = (
            f"Poxa, {primeiro_nome} — esse horário acabou de ficar indisponível. 😕"
            if motivo == "ocupado"
            else f"Poxa, {primeiro_nome} — esse horário já passou. 😕"
        )

        slots: list[Any] = []
        if escritorio is not None:
            try:
                prazos = await buscar_prazos_escritorio(
                    self._db, ag.escritorio_id, cliente_id=ag.cliente_id
                )
                detector = AgendamentoDetector(
                    db=self._db,
                    escritorio_id=ag.escritorio_id,
                    timezone_str=escritorio.timezone or "America/Sao_Paulo",
                )
                slots = await detector.buscar_slots(
                    num_slots=3, datas_evitar=datas_a_evitar(prazos)
                )
            except Exception as exc:
                logger.error("agendamento_reproposta_falhou", agendamento_id=ag.id, erro=str(exc))

        if not slots:
            ag.status = "expirado"
            await self._db.commit()
            logger.warning("agendamento_reproposta_sem_slots", agendamento_id=ag.id)
            return (
                f"{intro}\n\n"
                "No momento não encontrei outros horários livres, mas o escritório "
                "vai entrar em contato para combinar a melhor data. 🙏"
            )

        agora = datetime.now(UTC)
        ag.opcoes_propostas = [
            {
                "inicio": s.inicio.isoformat(),
                "fim": s.fim.isoformat(),
                "label": s.label,
                "conflito_prazo": s.conflito_prazo,
            }
            for s in slots
        ]
        ag.opcao_selecionada_pos = None
        ag.data_hora_inicio = None
        ag.data_hora_fim = None
        ag.status = "aguardando_cliente"
        ag.proposta_enviada_em = agora
        ag.expira_em = agora + timedelta(hours=_PROPOSTA_TTL_H)
        # A resposta desta função é entregue pelo fluxo do orchestrator
        ag.whatsapp_proposta_cliente_enviado = True
        ag.whatsapp_notificacao_advogado_enviado = False
        ag.whatsapp_confirmacao_cliente_enviado = False
        ag.whatsapp_confirmacao_pre_reuniao_enviado = False
        await self._db.commit()

        linhas = "\n".join(
            f"{_EMOJIS_OPCAO[i]}  {op['label']}" for i, op in enumerate(ag.opcoes_propostas[:3])
        )
        logger.info("agendamento_reproposto", agendamento_id=ag.id, motivo=motivo)
        return (
            f"{intro}\n\n"
            f"Mas tenho estas novas opções:\n\n{linhas}\n\n"
            "É só responder com o número da opção (1, 2 ou 3). 😊"
        )

    @staticmethod
    def _extrair_escolha(texto: str, opcoes: list[dict[str, Any]]) -> int | None:
        """Regex + matching contra os labels — sem gastar tokens Claude."""
        m = _RE_ESCOLHA_ISOLADA.match(texto) or _RE_ESCOLHA_FRASE.search(texto)
        if m:
            pos = int(m.group(1)) - 1
            return pos if pos < len(opcoes) else None

        # Negação ("não posso às 10h", "nenhum desses") — nunca casar por label;
        # deixa o fallback Claude (ou o fluxo normal da IA) interpretar.
        if re.search(r"\b(n[aã]o|nao|nenhum|nenhuma)\b", texto, re.IGNORECASE):
            return None

        # Matching por partes do label: dia da semana, data dd/mm, hora "10h"
        texto_lower = texto.lower()
        scores: list[int] = []
        for op in opcoes:
            label = str(op.get("label", "")).lower()
            score = 0
            # "Segunda-feira, 07/07 às 10h" → dia da semana
            dia_semana = label.split("-feira")[0].split(",")[0].strip()
            if dia_semana and len(dia_semana) >= 4 and dia_semana in texto_lower:
                score += 1
            data_m = re.search(r"\b\d{2}/\d{2}\b", label)
            if data_m and data_m.group(0) in texto_lower:
                score += 2
            hora_m = re.search(r"\b(\d{1,2})h(\d{2})?\b", label)
            if hora_m:
                hora_pat = re.compile(
                    rf"\b{int(hora_m.group(1))}\s*(h|hs|hrs|horas?|:00)\b", re.IGNORECASE
                )
                if hora_pat.search(texto_lower):
                    score += 1
            scores.append(score)

        melhor = max(scores) if scores else 0
        if melhor > 0 and scores.count(melhor) == 1:
            return scores.index(melhor)
        return None


def _registrar_confirmacao_metricas(ag: Agendamento, agora: datetime) -> None:
    try:
        if agendamentos_confirmados_total is not None:
            agendamentos_confirmados_total.labels(escritorio_id=str(ag.escritorio_id)).inc()
        resposta_cliente_em = _aware(ag.resposta_cliente_em)
        if tempo_aprovacao_advogado_segundos is not None and resposta_cliente_em:
            delta = (agora - resposta_cliente_em).total_seconds()
            if delta >= 0:
                tempo_aprovacao_advogado_segundos.labels(
                    escritorio_id=str(ag.escritorio_id)
                ).observe(delta)
    except Exception:  # pragma: no cover
        pass
