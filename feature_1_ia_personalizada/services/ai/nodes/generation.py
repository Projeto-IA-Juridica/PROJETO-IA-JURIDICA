"""
Nós de geração: gerar_resposta (Claude padrão) e gerar_resposta_escalacao (Opus).
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Any

import structlog

from feature_1_ia_personalizada.services.ai.escalation_client import EscalacaoIndisponivelError
from feature_1_ia_personalizada.services.ai.nodes._helpers import (
    obter_escritorio_cliente,
    obter_persona,
)
from feature_1_ia_personalizada.services.ai.prompts import (
    SYSTEM_PROMPT_BASE,
    SYSTEM_PROMPT_BOAS_VINDAS,
    SYSTEM_PROMPT_DESABAFO,
    SYSTEM_PROMPT_DUVIDA_GERAL,
    SYSTEM_PROMPT_ESCALACAO_CLIENTE_BASE,
    SYSTEM_PROMPT_ESCALACAO_PERGUNTA_JURIDICA,
    SYSTEM_PROMPT_PERSPECTIVAS,
    SYSTEM_PROMPT_SAUDACAO_RECORRENTE,
    SYSTEM_PROMPT_STATUS_PROCESSO,
    SYSTEM_PROMPT_TRADUZIR_TERMO,
)
from feature_1_ia_personalizada.services.ai.state import (
    TIMEOUT_CLAUDE_SEGUNDOS,
    ConversationState,
    NodeDeps,
    erros_total,
)
from feature_1_ia_personalizada.services.messaging.templates import TEMPLATE_ERRO_GENERICO
from shared.config.constants import MENSAGENS_FALLBACK

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Mensagens de fallback por intenção (Claude indisponível)
# ---------------------------------------------------------------------------

_FALLBACKS: dict[str, str] = {
    "status": (
        "Recebemos sua mensagem sobre o processo {numero}. "
        "No momento estou com dificuldades técnicas, "
        "mas o escritório retornará em breve."
    ),
    "perspectivas": (
        "Entendo sua dúvida sobre as perspectivas do processo. "
        "Estou com uma instabilidade técnica agora — "
        "o escritório entrará em contato em breve para esclarecer. ⚖️"
    ),
    "duvida_termo": (
        "Obrigado pela pergunta! Estou com uma dificuldade técnica temporária. "
        "Encaminhei sua dúvida ao escritório."
    ),
    "duvida_geral": (
        "Obrigado pela pergunta! Estou com uma dificuldade técnica temporária. "
        "Encaminhei sua dúvida ao escritório."
    ),
    "saudacao": (
        "Olá! No momento estou passando por uma manutenção rápida. "
        "O escritório entrará em contato em breve."
    ),
    "desabafo": (
        "Entendo que esse momento pode ser muito difícil. "
        "Estou com uma instabilidade técnica agora, mas o escritório "
        "está ciente e entrará em contato com você em breve. 🤝"
    ),
}


def _montar_system_prompt(
    intencao: str,
    dados: dict[str, Any],
    nome_escritorio: str,
    nome_cliente: str,
) -> str:
    if intencao == "status" and dados:
        andamentos_lista = dados.get("andamentos_recentes") or []
        andamentos_str = (
            "\n".join(
                (f"- {a['data']}: {a['descricao']}" if a.get("data") else f"- {a['descricao']}")
                for a in andamentos_lista
            )
            or "Histórico não disponível"
        )
        prompt = SYSTEM_PROMPT_STATUS_PROCESSO.format(
            nome_escritorio=nome_escritorio,
            nome_cliente=nome_cliente,
            numero_cnj=dados.get("numero_cnj", "N/D"),
            tribunal=dados.get("tribunal", "N/D"),
            vara=dados.get("vara", "N/D"),
            ultimo_andamento=dados.get("ultimo_andamento", "sem movimentação recente"),
            data_ultimo_andamento=dados.get("data_ultimo_andamento", "N/D"),
            polo_cliente=dados.get("polo_cliente", "N/D"),
            andamentos_recentes=andamentos_str,
        )
        glossario = dados.get("glossario_andamento") or {}
        if glossario:
            linhas = "\n".join(f"- {t}: {d}" for t, d in glossario.items())
            prompt += f"\n\n<glossario_termos>\n{linhas}\n</glossario_termos>"
        return prompt

    if intencao == "perspectivas" and dados:
        return SYSTEM_PROMPT_PERSPECTIVAS.format(
            nome_escritorio=nome_escritorio,
            nome_cliente=nome_cliente,
            numero_cnj=dados.get("numero_cnj", "N/D"),
            tribunal=dados.get("tribunal", "N/D"),
            polo_cliente=dados.get("polo_cliente", "N/D"),
            ultimo_andamento=dados.get("ultimo_andamento", "sem movimentação recente"),
        )

    if intencao == "duvida_geral" and dados:
        return SYSTEM_PROMPT_DUVIDA_GERAL.format(
            nome_escritorio=nome_escritorio,
            nome_cliente=nome_cliente,
            numero_cnj=dados.get("numero_cnj", "N/D"),
            tribunal=dados.get("tribunal", "N/D"),
            polo_cliente=dados.get("polo_cliente", "N/D"),
            ultimo_andamento=dados.get("ultimo_andamento", "sem movimentação recente"),
            data_ultimo_andamento=dados.get("data_ultimo_andamento", "N/D"),
        )

    if intencao == "duvida_termo":
        return SYSTEM_PROMPT_TRADUZIR_TERMO.format(
            nome_escritorio=nome_escritorio,
            nome_cliente=nome_cliente,
            numero_cnj=dados.get("numero_cnj", "N/D"),
            ultimo_andamento=dados.get("ultimo_andamento", "N/D"),
        )

    if intencao == "saudacao":
        template = (
            SYSTEM_PROMPT_SAUDACAO_RECORRENTE
            if dados.get("_cliente_recorrente")
            else SYSTEM_PROMPT_BOAS_VINDAS
        )
        return template.format(
            nome_escritorio=nome_escritorio,
            nome_cliente=nome_cliente,
            numero_cnj=dados.get("numero_cnj", "N/D"),
            ultimo_andamento=dados.get("ultimo_andamento", "N/D"),
            data_ultimo_andamento=dados.get("data_ultimo_andamento", "N/D"),
        )

    if intencao == "desabafo":
        return SYSTEM_PROMPT_DESABAFO.format(
            nome_escritorio=nome_escritorio,
            nome_cliente=nome_cliente,
        )

    return SYSTEM_PROMPT_BASE.format(
        nome_escritorio=nome_escritorio,
        nome_cliente=nome_cliente,
    )


async def node_gerar_resposta(state: ConversationState, deps: NodeDeps) -> dict[str, Any]:
    log = logger.bind(
        escritorio_id=state["escritorio_id"],
        cliente_id=state["cliente_id"],
        intencao=state.get("intencao"),
    )
    try:
        intencao = state.get("intencao", "outro")
        dados = state.get("dados_processo") or {}

        if intencao == "duvida_termo":
            traducao_local = deps.translator.traduzir_termo(state["mensagem_original"])
            if traducao_local:
                log.debug("termo_traduzido_dicionario_local")
                return {"resposta_ia": traducao_local, "precisa_regenerar": False}

        async with deps.session_factory() as session:
            escritorio, cliente = await obter_escritorio_cliente(
                session, state["escritorio_id"], state["cliente_id"]
            )
        nome_escritorio = escritorio.nome if escritorio else "Escritório"
        nome_cliente = cliente.nome if cliente else "cliente"

        persona_instrucao = await obter_persona(deps.redis, state["escritorio_id"], escritorio)

        # Injeta flag de cliente recorrente para o template de saudação
        if intencao == "saudacao":
            dados = dict(dados)
            dados["_cliente_recorrente"] = len(state.get("historico", [])) > 0

        system_prompt = _montar_system_prompt(intencao, dados, nome_escritorio, nome_cliente)
        if persona_instrucao:
            system_prompt = persona_instrucao + system_prompt

        contexto_rag = state.get("contexto_rag") or ""
        if contexto_rag:
            system_prompt += f"\n\n{contexto_rag}"

        resultado = await asyncio.wait_for(
            deps.claude.enviar_mensagem(
                system_prompt=system_prompt,
                mensagens_historico=state.get("historico", []),
                mensagem_usuario=state["mensagem_original"],
                intencao=intencao,
            ),
            timeout=TIMEOUT_CLAUDE_SEGUNDOS,
        )

        tokens_anteriores = state.get("tokens_usados") or {"input": 0, "output": 0}
        custo_anterior = Decimal(tokens_anteriores.get("custo_str", "0"))
        tokens_atualizados = {
            "input": tokens_anteriores.get("input", 0) + resultado["tokens_input"],
            "output": tokens_anteriores.get("output", 0) + resultado["tokens_output"],
            "custo_str": str(custo_anterior + resultado["custo"]),
        }
        log.info("resposta_gerada", tokens=tokens_atualizados)
        return {
            "resposta_ia": resultado["resposta"],
            "tokens_usados": tokens_atualizados,
            "precisa_regenerar": False,
        }

    except (RuntimeError, TimeoutError) as exc:
        erros_total.labels(no="gerar_resposta").inc()
        _is_timeout = isinstance(exc, TimeoutError)
        log.error(
            (
                "claude_timeout_ativando_fallback"
                if _is_timeout
                else "claude_indisponivel_ativando_fallback"
            ),
            erro=str(exc),
            timeout_s=TIMEOUT_CLAUDE_SEGUNDOS if _is_timeout else None,
        )
        intencao = state.get("intencao", "outro")
        dados = state.get("dados_processo") or {}
        tpl = _FALLBACKS.get(
            intencao, MENSAGENS_FALLBACK.get("indisponivel", TEMPLATE_ERRO_GENERICO)
        )
        fallback_msg = (
            tpl.format(numero=dados.get("numero_cnj", "seu processo")) if "{numero}" in tpl else tpl
        )
        return {"resposta_ia": fallback_msg, "usando_fallback": True, "precisa_regenerar": False}

    except Exception as exc:
        erros_total.labels(no="gerar_resposta").inc()
        log.error("gerar_resposta_erro_inesperado", erro=str(exc))
        return {"erro": f"gerar_resposta:{exc}"}


async def node_gerar_resposta_escalacao(state: ConversationState, deps: NodeDeps) -> dict[str, Any]:
    """
    Gera resposta usando Claude Opus quando o ConfidenceRouter decide por escalação.
    Fallback: reutiliza resposta Claude padrão já no state.
    """
    log = logger.bind(
        escritorio_id=state["escritorio_id"],
        cliente_id=state["cliente_id"],
        intencao=state.get("intencao"),
    )
    intencao = state.get("intencao", "outro")

    try:
        async with deps.session_factory() as session:
            escritorio, cliente = await obter_escritorio_cliente(
                session, state["escritorio_id"], state["cliente_id"]
            )

        nome_escritorio = escritorio.nome if escritorio else "Escritório"
        nome_cliente = cliente.nome if cliente else "cliente"

        if intencao in ("perspectivas", "pergunta_juridica", "juridica_complexa"):
            system_prompt = SYSTEM_PROMPT_ESCALACAO_PERGUNTA_JURIDICA.format(
                nome_escritorio=nome_escritorio,
                nome_cliente=nome_cliente,
            )
        else:
            system_prompt = SYSTEM_PROMPT_ESCALACAO_CLIENTE_BASE.format(
                nome_escritorio=nome_escritorio,
                nome_cliente=nome_cliente,
                contexto_documentos=state.get("contexto_rag") or "",
            )

        t_inicio = time.perf_counter()
        resultado = await asyncio.wait_for(
            deps.escalacao_client.gerar_resposta(
                system_prompt=system_prompt,
                mensagem_usuario=state["mensagem_original"],
                contexto_rag=state.get("contexto_rag") or "",
                escritorio_id=state["escritorio_id"],
            ),
            timeout=50.0,
        )
        latencia = int((time.perf_counter() - t_inicio) * 1000)

        # Métricas de escalação (lazy import para evitar circular)
        try:
            from feature_1_ia_personalizada.api.routes.metrics import (
                escalacao_latencia_ms,
                escalacao_requests_total,
                escalacao_tokens_total,
            )

            escalacao_latencia_ms.observe(latencia)
            escalacao_requests_total.labels(
                escritorio_id=str(state["escritorio_id"]), resultado="sucesso"
            ).inc()
            escalacao_tokens_total.labels(
                escritorio_id=str(state["escritorio_id"]), tipo="input"
            ).inc(resultado.tokens_input)
            escalacao_tokens_total.labels(
                escritorio_id=str(state["escritorio_id"]), tipo="output"
            ).inc(resultado.tokens_output)
        except Exception:
            pass

        from sqlalchemy import update

        from shared.models.escritorio import Escritorio

        try:
            async with deps.session_factory() as session:
                await session.execute(
                    update(Escritorio)
                    .where(Escritorio.id == state["escritorio_id"])
                    .values(
                        escalacao_tokens_usados_mes=Escritorio.escalacao_tokens_usados_mes
                        + resultado.tokens_input
                        + resultado.tokens_output
                    )
                )
                await session.commit()
        except Exception as exc_quota:
            log.warning("escalacao_atualizar_quota_falhou", erro=str(exc_quota))

        tokens_anteriores = state.get("tokens_usados") or {"input": 0, "output": 0}
        custo_anterior = Decimal(tokens_anteriores.get("custo_str", "0"))
        tokens_atualizados = {
            "input": tokens_anteriores.get("input", 0) + resultado.tokens_input,
            "output": tokens_anteriores.get("output", 0) + resultado.tokens_output,
            "custo_str": str(custo_anterior + resultado.custo_estimado),
        }
        log.info("resposta_escalacao_gerada", latencia_ms=latencia, tokens=tokens_atualizados)
        return {
            "resposta_ia": resultado.conteudo,
            "tokens_usados": tokens_atualizados,
            "modelo_ia_usado": "claude_opus",
            "precisa_regenerar": False,
        }

    except (EscalacaoIndisponivelError, TimeoutError) as exc:
        try:
            from feature_1_ia_personalizada.api.routes.metrics import escalacao_requests_total

            escalacao_requests_total.labels(
                escritorio_id=str(state["escritorio_id"]), resultado="fallback_claude"
            ).inc()
        except Exception:
            pass
        log.warning("escalacao_indisponivel_usando_claude", erro=str(exc))
        return {"modelo_ia_usado": "claude_opus_fallback", "precisa_regenerar": False}

    except Exception as exc:
        erros_total.labels(no="gerar_resposta_escalacao").inc()
        log.error("gerar_resposta_escalacao_erro_inesperado", erro=str(exc))
        return {"modelo_ia_usado": "claude_opus_fallback", "precisa_regenerar": False}
