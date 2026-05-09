"""
Nó buscar_dados: carrega processo, andamentos (cache/DataJud) e RAG em paralelo.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import structlog

from feature_1_ia_personalizada.services.ai.nodes._helpers import (
    buscar_rag,
    listar_processos_ativos,
)
from feature_1_ia_personalizada.services.ai.state import (
    TIMEOUT_DATAJUD_SEGUNDOS,
    ConversationState,
    NodeDeps,
    erros_total,
)
from feature_1_ia_personalizada.services.messaging.templates import TEMPLATE_CLIENTE_SEM_PROCESSO

logger = structlog.get_logger(__name__)

_CNJ_NA_MENSAGEM = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")


async def node_buscar_dados(state: ConversationState, deps: NodeDeps) -> dict[str, Any]:
    log = logger.bind(escritorio_id=state["escritorio_id"], cliente_id=state["cliente_id"])
    try:
        async with deps.session_factory() as session:
            processos = await listar_processos_ativos(
                session, state["escritorio_id"], state["cliente_id"]
            )

        if not processos:
            log.info("cliente_sem_processos")
            return {"resposta_verificada": TEMPLATE_CLIENTE_SEM_PROCESSO}

        # Seleciona processo: CNJ explícito na mensagem ou o mais recente
        processo = processos[0]
        match_cnj = _CNJ_NA_MENSAGEM.search(state["mensagem_original"])
        if match_cnj and len(processos) > 1:
            cnj_mencionado = match_cnj.group(0)
            for p in processos:
                if p.numero_cnj and cnj_mencionado in p.numero_cnj:
                    processo = p
                    break

        numero_cnj = processo.numero_cnj
        rag_docs_com_score: list[dict[str, Any]] = []

        andamentos = await deps.cache.get_andamentos(numero_cnj)
        if andamentos:
            log.debug("andamentos_do_cache", cnj=numero_cnj)
            contexto_rag, rag_docs_com_score = await buscar_rag(state, deps)
        else:
            contexto_processo_para_rag = {
                "tipo_acao": getattr(processo, "tipo_acao", None),
                "tribunal": processo.tribunal,
            }
            try:
                (andamentos, (contexto_rag, rag_docs_com_score)) = await asyncio.wait_for(
                    asyncio.gather(
                        deps.datajud.buscar_andamentos_async(numero_cnj),
                        buscar_rag(state, deps, contexto_processo_para_rag),
                    ),
                    timeout=TIMEOUT_DATAJUD_SEGUNDOS,
                )
                if andamentos:
                    await deps.cache.set_andamentos(numero_cnj, andamentos)
                log.info("andamentos_do_datajud", cnj=numero_cnj, total=len(andamentos))
            except TimeoutError:
                log.warning(
                    "datajud_timeout_usando_dados_banco",
                    timeout_s=TIMEOUT_DATAJUD_SEGUNDOS,
                    cnj=numero_cnj,
                )
                andamentos = []
                contexto_rag = ""

        ultimo_andamento = (
            andamentos[0].get("descricao", "")
            if andamentos
            else (processo.ultimo_andamento or "sem movimentação recente")
        )
        data_ultimo = (
            andamentos[0].get("data", "")
            if andamentos
            else (
                processo.data_ultimo_andamento.isoformat()
                if processo.data_ultimo_andamento
                else "N/D"
            )
        )

        termos_detectados = deps.translator.identificar_termos_tecnicos(ultimo_andamento)
        glossario_andamento: dict[str, str] = {}
        for termo in termos_detectados:
            trad = deps.translator.traduzir_termo(termo)
            if trad:
                glossario_andamento[termo] = trad.split("\n\n")[0]

        andamentos_recentes = [
            {"descricao": a.get("descricao", ""), "data": a.get("data", "")}
            for a in andamentos[:5]
            if a.get("descricao")
        ]
        outros_processos = [
            {"numero_cnj": p.numero_cnj, "tipo_acao": getattr(p, "tipo_acao", None) or "N/D"}
            for p in processos
            if p.id != processo.id
        ]

        dados_processo = {
            "processo_id": processo.id,
            "numero_cnj": numero_cnj,
            "tribunal": processo.tribunal or "N/D",
            "vara": processo.vara or "N/D",
            "polo_cliente": processo.polo_cliente or "autor",
            "ultimo_andamento": ultimo_andamento,
            "data_ultimo_andamento": data_ultimo,
            "andamentos_recentes": andamentos_recentes,
            "glossario_andamento": glossario_andamento,
            "outros_processos_ativos": outros_processos,
        }

        log.info(
            "dados_processo_obtidos",
            cnj=numero_cnj,
            rag_ativo=bool(contexto_rag),
            total_processos=len(processos),
        )
        return {
            "processo_id": processo.id,
            "dados_processo": dados_processo,
            "contexto_rag": contexto_rag or None,
            "rag_docs_com_score": rag_docs_com_score,
        }

    except Exception as exc:
        erros_total.labels(no="buscar_dados").inc()
        log.error("buscar_dados_erro", erro=str(exc))
        return {"erro": f"buscar_dados:{exc}"}
