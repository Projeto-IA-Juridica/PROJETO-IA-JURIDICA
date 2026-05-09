"""
Nós de intenção: classificar_intencao, avaliar_escalacao, preparar_escalacao.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from feature_1_ia_personalizada.services.ai.nodes._helpers import obter_escritorio_cliente
from feature_1_ia_personalizada.services.ai.prompts import SYSTEM_PROMPT_CLASSIFICAR_INTENCAO
from feature_1_ia_personalizada.services.ai.state import (
    ConversationState,
    NodeDeps,
    classificar_por_keywords,
    erros_total,
)

logger = structlog.get_logger(__name__)

_CATEGORIAS_VALIDAS = {
    "status",
    "perspectivas",
    "duvida_termo",
    "duvida_geral",
    "saudacao",
    "reclamacao",
    "desabafo",
    "parecer_juridico",
    "estrategia_processual",
    "negociacao",
    "decisao_judicial_impacto_alto",
    "outro",
}

_ESCALACAO_OBRIGATORIA = {
    "parecer_juridico",
    "estrategia_processual",
    "negociacao",
    "decisao_judicial_impacto_alto",
}

_MSG_ESCALACAO = (
    "Sua pergunta é muito importante e específica para o andamento do seu caso particular. "
    "Para garantir a melhor orientação jurídica, encaminhei sua mensagem imediatamente "
    "para o advogado responsável, que analisará a questão e retornará em breve."
)


async def node_classificar_intencao(state: ConversationState, deps: NodeDeps) -> dict[str, Any]:
    log = logger.bind(escritorio_id=state["escritorio_id"], cliente_id=state["cliente_id"])
    try:
        raw = await deps.claude.classificar_intencao(
            system_prompt=SYSTEM_PROMPT_CLASSIFICAR_INTENCAO,
            mensagem=state["mensagem_original"],
        )
        parsed = json.loads(raw)
        intencao = parsed.get("intencao", "outro")
        if intencao not in _CATEGORIAS_VALIDAS:
            intencao = "outro"
        log.info("intencao_classificada_claude", intencao=intencao)
    except Exception as exc:
        intencao = classificar_por_keywords(state["mensagem_original"])
        log.warning("intencao_fallback_keywords", intencao=intencao, erro=str(exc))

    return {"intencao": intencao}


async def node_avaliar_escalacao(state: ConversationState, deps: NodeDeps) -> dict[str, Any]:
    log = logger.bind(
        escritorio_id=state["escritorio_id"],
        cliente_id=state["cliente_id"],
        intencao=state.get("intencao"),
    )
    intencao = state.get("intencao", "outro")
    if intencao in _ESCALACAO_OBRIGATORIA:
        log.info("escalacao_detectada", motivo=intencao)
        return {"requer_escalacao": True, "motivo_escalacao": intencao}
    return {"requer_escalacao": False, "motivo_escalacao": None}


async def node_preparar_escalacao(state: ConversationState, deps: NodeDeps) -> dict[str, Any]:
    log = logger.bind(
        escritorio_id=state["escritorio_id"],
        cliente_id=state["cliente_id"],
        intencao=state.get("intencao"),
    )
    try:
        instancia_whatsapp = ""
        async with deps.session_factory() as session:
            escritorio, _ = await obter_escritorio_cliente(
                session, state["escritorio_id"], state["cliente_id"]
            )
            if escritorio:
                instancia_whatsapp = escritorio.webhook_whatsapp_instance or ""

        motivo = state.get("motivo_escalacao") or "indefinido"

        task = asyncio.create_task(
            deps.escalacao_manager.avaliar_e_notificar_advogados(
                escritorio_id=state["escritorio_id"],
                cliente_id=state["cliente_id"],
                mensagem_cliente=state["mensagem_original"],
                motivo=motivo,
                historico_recente=state.get("historico", []),
                instancia_whatsapp=instancia_whatsapp,
            )
        )

        def _log_error(t: asyncio.Task) -> None:  # type: ignore[type-arg]
            if not t.cancelled() and (exc := t.exception()):
                logger.error(
                    "escalacao_background_falhou",
                    escritorio_id=state["escritorio_id"],
                    erro=str(exc),
                )
                erros_total.labels(no="escalacao_background").inc()

        task.add_done_callback(_log_error)

        return {
            "resposta_ia": _MSG_ESCALACAO,
            "resposta_verificada": _MSG_ESCALACAO,
            "precisa_regenerar": False,
        }
    except Exception as exc:
        erros_total.labels(no="preparar_escalacao").inc()
        log.error("preparar_escalacao_erro_inesperado", erro=str(exc))
        return {"erro": f"preparar_escalacao:{exc}"}
