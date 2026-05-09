"""
Nós de verificação: avaliar_confianca e verificar_resposta.
"""
from __future__ import annotations

from typing import Any

import structlog

from feature_1_ia_personalizada.services.ai.nodes._helpers import obter_escritorio_cliente
from feature_1_ia_personalizada.services.ai.state import (
    ConversationState,
    NodeDeps,
    erros_total,
)
from feature_1_ia_personalizada.services.messaging.templates import TEMPLATE_ERRO_GENERICO
from shared.config.constants import MENSAGENS_FALLBACK

logger = structlog.get_logger(__name__)


class _InteracaoStub:
    """Stub passado ao FactChecker quando não há interação persistida ainda."""
    metadata_json: dict[str, Any] | None = None


async def node_avaliar_confianca(state: ConversationState, deps: NodeDeps) -> dict[str, Any]:
    """
    Avalia a confiança da resposta Claude e decide se deve escalar para Opus.
    Falha de forma silenciosa — nunca derruba o fluxo principal.
    """
    log = logger.bind(
        escritorio_id=state["escritorio_id"],
        cliente_id=state["cliente_id"],
        intencao=state.get("intencao"),
    )

    if state.get("usando_fallback"):
        return {"_escalar_para_opus": False}

    try:
        async with deps.session_factory() as session:
            escritorio, _ = await obter_escritorio_cliente(
                session, state["escritorio_id"], state["cliente_id"]
            )

        if not escritorio:
            return {"_escalar_para_opus": False}

        rag_docs = state.get("rag_docs_com_score") or []

        fact_check_result: dict[str, Any] = {}
        fact_check_para_router: dict[str, Any] = {}
        if state.get("dados_processo") and state.get("processo_id"):
            try:
                fact_check_result = await deps.fact_checker.verificar_status_processo(
                    processo_id=str(state["processo_id"]),
                    afirmacao_ia=state.get("resposta_ia") or "",
                    interacao=_InteracaoStub(),
                )
                correcoes = fact_check_result.get("correcoes", [])
                hallucination_score = (
                    0.0
                    if fact_check_result.get("verificado", True)
                    else min(1.0, len(correcoes) / 3)
                )
                fact_check_para_router = {"hallucination_score": hallucination_score}
            except Exception as exc_fc:
                log.warning("avaliar_confianca_fact_check_falhou", erro=str(exc_fc))

        score = deps.confidence_router.avaliar(
            mensagem=state["mensagem_original"],
            resposta_claude=state.get("resposta_ia"),
            tipo_intencao=state.get("intencao", "outro"),
            rag_docs=rag_docs,
            fact_check_result=fact_check_para_router,
            historico_cliente=state.get("historico", []),
            tentativas_geracao=state.get("tentativas_correcao", 0),
            escritorio_id=state["escritorio_id"],
        )
        destino = deps.confidence_router.rotear(score, escritorio)
        deve_escalar = destino == "escalacao"

        log.info("confidence_avaliado", score=score.valor, deve_escalar=deve_escalar, motivo=score.motivo)

        if deve_escalar:
            try:
                from feature_1_ia_personalizada.api.routes.metrics import escalacao_roteamentos_total
                motivo_label = "forcado" if score.deve_escalar else "score_baixo"
                escalacao_roteamentos_total.labels(
                    escritorio_id=str(state["escritorio_id"]), motivo=motivo_label
                ).inc()
            except Exception:
                pass

        return {
            "confidence_score": score.valor,
            "_escalar_para_opus": deve_escalar,
            "fact_check_result": fact_check_result,
        }

    except Exception as exc:
        erros_total.labels(no="avaliar_confianca").inc()
        log.warning("avaliar_confianca_erro_graceful", erro=str(exc))
        return {"_escalar_para_opus": False}


async def node_verificar_resposta(state: ConversationState, deps: NodeDeps) -> dict[str, Any]:
    log = logger.bind(escritorio_id=state["escritorio_id"], cliente_id=state["cliente_id"])

    if state.get("usando_fallback"):
        return {"resposta_verificada": state.get("resposta_ia"), "precisa_regenerar": False}

    resposta = state.get("resposta_ia", "")
    if not resposta:
        return {"erro": "verificar_resposta:resposta_vazia"}

    try:
        stub = _InteracaoStub()
        eh_sobre_processo = state.get("intencao") in ("status", "perspectivas")
        resposta_filtrada = deps.fact_checker.filtrar_resposta(
            resposta_ia=resposta,
            interacao=stub,
            adicionar_disclaimer=eh_sobre_processo,
        )

        precisa_regenerar = False
        if state.get("dados_processo") and state.get("processo_id"):
            resultado_fc = state.get("fact_check_result") or {}
            if not resultado_fc:
                resultado_fc = await deps.fact_checker.verificar_status_processo(
                    processo_id=str(state["processo_id"]),
                    afirmacao_ia=resposta_filtrada,
                    interacao=stub,
                )
            if not resultado_fc.get("verificado", True):
                tentativas = state.get("tentativas_correcao") or 0
                if tentativas < 2:
                    precisa_regenerar = True
                    log.warning(
                        "fact_check_divergencia",
                        correcoes=resultado_fc["correcoes"],
                        tentativa=tentativas,
                    )
                else:
                    log.error("fact_check_max_tentativas_atingidas")
                    resposta_filtrada = MENSAGENS_FALLBACK.get("indisponivel", TEMPLATE_ERRO_GENERICO)

        updates: dict[str, Any] = {
            "resposta_verificada": resposta_filtrada,
            "precisa_regenerar": precisa_regenerar,
        }
        if precisa_regenerar:
            updates["tentativas_correcao"] = state.get("tentativas_correcao", 0) + 1
        return updates

    except Exception as exc:
        erros_total.labels(no="verificar_resposta").inc()
        log.error("verificar_resposta_erro", erro=str(exc))
        return {"resposta_verificada": resposta, "precisa_regenerar": False}
