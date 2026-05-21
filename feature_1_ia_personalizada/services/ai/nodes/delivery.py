"""
Nós de entrega: enviar_resposta e tratar_erro.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import structlog

from feature_1_ia_personalizada.services.ai.nodes._helpers import (
    obter_escritorio_cliente,
    salvar_interacao,
)
from feature_1_ia_personalizada.services.ai.state import (
    ConversationState,
    NodeDeps,
    delay_digitacao_whatsapp,
    erros_total,
    fragmentar_resposta,
)
from feature_1_ia_personalizada.services.messaging.templates import TEMPLATE_ERRO_GENERICO
from shared.models.interacao import Interacao

logger = structlog.get_logger(__name__)


async def node_enviar_resposta(state: ConversationState, deps: NodeDeps) -> dict[str, Any]:
    log = logger.bind(escritorio_id=state["escritorio_id"], cliente_id=state["cliente_id"])

    resposta_final = (
        state.get("resposta_verificada") or state.get("resposta_ia") or TEMPLATE_ERRO_GENERICO
    )
    tokens = state.get("tokens_usados") or {"input": 0, "output": 0}
    custo = Decimal(tokens.get("custo_str", "0"))

    try:
        async with deps.session_factory() as session:
            escritorio, cliente = await obter_escritorio_cliente(
                session, state["escritorio_id"], state["cliente_id"]
            )

            if not escritorio or not cliente:
                log.error("escritorio_ou_cliente_nao_encontrado")
                return {"erro": "enviar_resposta:entidade_nao_encontrada"}

            instance = escritorio.webhook_whatsapp_instance
            numero = cliente.telefone_whatsapp

            if instance and numero:
                try:
                    partes = fragmentar_resposta(resposta_final)
                    for i, parte in enumerate(partes):
                        await deps.evolution.enviar_texto(instance, numero, parte)
                        if i < len(partes) - 1:
                            await asyncio.sleep(delay_digitacao_whatsapp(partes[i + 1]))
                    log.info(
                        "mensagem_enviada_whatsapp",
                        numero_parcial=numero[:4] + "***",
                        partes=len(partes),
                    )
                except Exception as exc_wa:
                    log.warning("falha_envio_whatsapp", erro=str(exc_wa))
            else:
                log.warning("instancia_ou_numero_ausente", instance=instance, numero=bool(numero))

            await deps.memory.salvar_mensagem(
                state["escritorio_id"], state["cliente_id"], "user", state["mensagem_original"]
            )
            await deps.memory.salvar_mensagem(
                state["escritorio_id"], state["cliente_id"], "assistant", resposta_final
            )
            await salvar_interacao(session, state, resposta_final, tokens, custo)

        log.info(
            "fluxo_concluido",
            intencao=state.get("intencao"),
            usando_fallback=state.get("usando_fallback"),
            tokens=tokens,
        )
        return {"precisa_regenerar": False}

    except Exception as exc:
        erros_total.labels(no="enviar_resposta").inc()
        log.error("enviar_resposta_erro", erro=str(exc))
        return {"erro": f"enviar_resposta:{exc}"}


async def node_tratar_erro(state: ConversationState, deps: NodeDeps) -> dict[str, Any]:
    erro = state.get("erro", "erro_desconhecido")
    log = logger.bind(
        escritorio_id=state["escritorio_id"],
        cliente_id=state["cliente_id"],
        erro=erro,
    )
    log.error("fluxo_erro_nao_recuperavel")
    erros_total.labels(no="tratar_erro").inc()

    try:
        async with deps.session_factory() as session:
            escritorio, cliente = await obter_escritorio_cliente(
                session, state["escritorio_id"], state["cliente_id"]
            )

            if (
                escritorio
                and cliente
                and escritorio.webhook_whatsapp_instance
                and cliente.telefone_whatsapp
            ):
                try:
                    await deps.evolution.enviar_texto(
                        escritorio.webhook_whatsapp_instance,
                        cliente.telefone_whatsapp,
                        TEMPLATE_ERRO_GENERICO,
                    )
                except Exception as exc_wa:
                    log.warning("falha_envio_mensagem_erro", erro=str(exc_wa))

            interacao = Interacao(
                escritorio_id=state["escritorio_id"],
                cliente_id=state["cliente_id"],
                processo_id=state.get("processo_id"),
                tipo=state.get("tipo_mensagem", "texto"),
                direcao="saida",
                mensagem_cliente=state["mensagem_original"],
                mensagem_ia=TEMPLATE_ERRO_GENERICO,
                tokens_input=0,
                tokens_output=0,
                custo_estimado=Decimal("0"),
                metadata_json={"erro": True, "tipo_erro": erro},
            )
            session.add(interacao)
            await session.commit()

    except Exception as exc_inner:
        log.error("tratar_erro_falhou_persistir", exc_inner=str(exc_inner))

    return {"usando_fallback": True}
