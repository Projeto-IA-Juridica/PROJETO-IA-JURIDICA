# feature_1_ia_personalizada/services/rag/retriever.py
"""
RAGRetriever — interface de alto nível entre o orquestrador e o VectorStore.

Recebe uma query em texto e retorna um bloco formatado pronto para injeção
no system prompt do Claude.

Funcionalidades:
  - Filtra candidatos pelo threshold RAG_MIN_SIMILARITY (descarta irrelevantes)
  - Re-ranking MMR (Maximum Marginal Relevance) — seleciona RAG_TOP_K_FINAL chunks
    que são ao mesmo tempo relevantes para a query E diversos entre si.
    Sem custo extra de embedding: usa Jaccard de tokens entre os conteúdos.
  - Se `contexto_processo` fornecido (tipo_acao), prioriza docs do mesmo tipo.
  - Retorna string vazia quando nenhum doc passa o threshold — sem poluir o prompt.
"""

from __future__ import annotations

from typing import Any

import structlog
from prometheus_client import Counter

from feature_1_ia_personalizada.services.rag.vector_store import (
    ResultadoBusca,
    VectorStore,
)
from shared.config.constants import (
    RAG_MIN_SIMILARITY,
    RAG_TOP_K_CANDIDATOS,
    RAG_TOP_K_FINAL,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

_rag_usado = Counter(
    "rag_contexto_injetado_total",
    "Respostas que receberam contexto RAG no prompt",
)
_rag_vazio = Counter(
    "rag_contexto_vazio_total",
    "Buscas RAG sem resultado acima do threshold",
)

# Limiar de distância coseno equivalente a RAG_MIN_SIMILARITY
_MAX_DISTANCIA = 1.0 - RAG_MIN_SIMILARITY  # 0.25


# ---------------------------------------------------------------------------
# RAGRetriever
# ---------------------------------------------------------------------------


class RAGRetriever:
    """
    Interface de alto nível para o orquestrador chamar o RAG.

    Instanciar uma vez e reutilizar (VectorStore é stateless por request).
    """

    def __init__(self, vector_store: VectorStore) -> None:
        self._store = vector_store

    async def buscar(
        self,
        query: str,
        escritorio_id: int,
        contexto_processo: dict[str, Any] | None = None,
    ) -> str:
        """
        Busca contexto jurídico relevante para a query.

        Args:
            query:            mensagem ou termo a buscar.
            escritorio_id:    tenant.
            contexto_processo: dict opcional com campos do processo em andamento,
                              ex: {"tipo_acao": "Ação de Indenização", "tribunal": "TJSP"}.
                              Usado para filtrar candidatos preferindo o mesmo tipo_acao.

        Returns:
            Bloco de texto formatado para injeção no prompt, ou string vazia
            quando nenhum documento passa o threshold de relevância.
        """
        # Extrai filtro de tipo_acao do contexto do processo (se disponível)
        filtros: dict[str, Any] | None = None
        if contexto_processo and contexto_processo.get("tipo_acao"):
            filtros = {"tipo_acao": contexto_processo["tipo_acao"]}

        candidatos = await self._store.buscar_por_texto(
            query_texto=query,
            escritorio_id=escritorio_id,
            top_k=RAG_TOP_K_CANDIDATOS,
            filtros=filtros,
        )

        # Se filtro retornou poucos candidatos, busca sem filtro para complementar
        if filtros and len(candidatos) < RAG_TOP_K_FINAL:
            candidatos_sem_filtro = await self._store.buscar_por_texto(
                query_texto=query,
                escritorio_id=escritorio_id,
                top_k=RAG_TOP_K_CANDIDATOS,
            )
            # Junta, deduplica por id, mantendo os filtrados primeiro
            ids_vistos = {c.id for c in candidatos}
            for c in candidatos_sem_filtro:
                if c.id not in ids_vistos:
                    candidatos.append(c)
                    ids_vistos.add(c.id)

        # Filtra pelo threshold de relevância
        relevantes = [c for c in candidatos if c.distancia <= _MAX_DISTANCIA]

        if not relevantes:
            _rag_vazio.inc()
            logger.debug(
                "rag_sem_resultado_relevante",
                escritorio_id=escritorio_id,
                threshold=_MAX_DISTANCIA,
                n_candidatos=len(candidatos),
            )
            return ""

        # Re-ranking MMR — seleciona os RAG_TOP_K_FINAL mais complementares
        selecionados = _mmr(relevantes, k=RAG_TOP_K_FINAL)

        _rag_usado.inc()
        logger.debug(
            "rag_contexto_encontrado",
            escritorio_id=escritorio_id,
            n_selecionados=len(selecionados),
        )

        return _formatar_contexto(selecionados)


# ---------------------------------------------------------------------------
# Re-ranking: Maximum Marginal Relevance (MMR)
# ---------------------------------------------------------------------------


def _mmr(candidatos: list[ResultadoBusca], k: int) -> list[ResultadoBusca]:
    """
    Seleciona k chunks que maximizam relevância (distância baixa à query)
    e diversidade (diferença entre si).

    Usa Jaccard de tokens entre os textos dos chunks como medida de similaridade
    cruzada — sem custo extra de embedding.

    Algoritmo:
      1. Começa com o chunk mais próximo da query.
      2. A cada passo, escolhe o chunk com maior:
           relevância_normalizada - max(similaridade_com_já_selecionados)
      3. Repete até k selecionados.
    """
    if len(candidatos) <= k:
        return candidatos

    # Normaliza distâncias para [0, 1] (0 = mais similar)
    max_dist = max(c.distancia for c in candidatos) or 1.0
    relevancia = {c.id: 1.0 - (c.distancia / max_dist) for c in candidatos}

    # Tokeniza cada chunk para Jaccard
    tokens_por_id = {c.id: _tokenizar(c.conteudo) for c in candidatos}

    selecionados: list[ResultadoBusca] = []
    restantes = list(candidatos)

    while len(selecionados) < k and restantes:
        if not selecionados:
            # Primeiro: mais relevante
            melhor = max(restantes, key=lambda c: relevancia[c.id])
        else:
            tokens_sel = [tokens_por_id[s.id] for s in selecionados]

            def _score(c: ResultadoBusca) -> float:
                max_sim = max(_jaccard(tokens_por_id[c.id], t) for t in tokens_sel)
                return relevancia[c.id] - max_sim

            melhor = max(restantes, key=_score)

        selecionados.append(melhor)
        restantes.remove(melhor)

    return selecionados


def _tokenizar(texto: str) -> frozenset[str]:
    """Tokens de palavras com 3+ caracteres (ignora stopwords curtas)."""
    return frozenset(w.lower() for w in texto.split() if len(w) >= 3)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Similaridade de Jaccard entre dois conjuntos de tokens."""
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


# ---------------------------------------------------------------------------
# Formatação do contexto para o prompt
# ---------------------------------------------------------------------------


def _formatar_contexto(chunks: list[ResultadoBusca]) -> str:
    """
    Formata os chunks selecionados em bloco XML para injeção no system prompt.
    Cada chunk recebe um número e a fonte (título + tipo).
    """
    linhas = ["<contexto_juridico_escritorio>"]
    for i, chunk in enumerate(chunks, start=1):
        tipo_label = chunk.tipo.replace("_", " ").title()
        linhas.append(f"[{i}] {tipo_label} — {chunk.titulo}")
        linhas.append(chunk.conteudo.strip())
        linhas.append("")
    linhas.append("</contexto_juridico_escritorio>")
    return "\n".join(linhas)
