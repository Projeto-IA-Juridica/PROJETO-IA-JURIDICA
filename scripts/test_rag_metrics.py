#!/usr/bin/env python3
"""
Script para testar métricas Prometheus do RAG Retriever localmente.

Simula:
  - Buscas com contexto (RAG encontra documentos relevantes)
  - Buscas sem contexto (RAG retorna vazio)
  - Latência de busca
  - Cache hits

Exporta as métricas em formato Prometheus após os testes.

Uso:
    python scripts/test_rag_metrics.py
"""

import asyncio
import sys
from dataclasses import dataclass
from typing import Any

from prometheus_client import REGISTRY, generate_latest

# Adiciona o path da aplicação
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from feature_1_ia_personalizada.services.rag.retriever import RAGRetriever


# ============================================================================
# Mock: VectorStore simples para testes
# ============================================================================

@dataclass
class ResultadoBuscaMock:
    id: int
    escritorio_id: int
    titulo: str
    tipo: str
    conteudo: str
    chunk_index: int
    doc_hash: str | None
    metadata_json: dict[str, Any]
    distancia: float


class VectorStoreMock:
    """
    Mock simples do VectorStore que retorna resultados pré-programados.
    """

    def __init__(self):
        # Documentos de teste com distâncias variadas
        self.docs_relevantes = [
            ResultadoBuscaMock(
                id=1,
                escritorio_id=1,
                titulo="Lei de Proteção de Dados (LGPD)",
                tipo="Lei",
                conteudo="A LGPD estabelece direitos e deveres sobre dados pessoais...",
                chunk_index=0,
                doc_hash="hash_lgpd_1",
                metadata_json={"tipo_acao": "LGPD", "tribunal": "STF"},
                distancia=0.15,  # Altamente relevante (< 0.25)
            ),
            ResultadoBuscaMock(
                id=2,
                escritorio_id=1,
                titulo="Artigos sobre conformidade LGPD",
                tipo="Jurisprudência",
                conteudo="Empresas precisam fazer conformidade com LGPD...",
                chunk_index=0,
                doc_hash="hash_lgpd_2",
                metadata_json={"tipo_acao": "LGPD", "tribunal": "TJ"},
                distancia=0.22,
            ),
        ]

        self.docs_baixa_relevancia = [
            ResultadoBuscaMock(
                id=10,
                escritorio_id=1,
                titulo="Código Penal Brasileiro",
                tipo="Lei",
                conteudo="Código penal com artigos sobre crimes...",
                chunk_index=0,
                doc_hash="hash_cp_1",
                metadata_json={"tipo_acao": "Penal", "tribunal": "STF"},
                distancia=0.45,  # Baixa relevância (> 0.25)
            ),
        ]

    async def buscar_por_texto(
        self,
        query_texto: str,
        escritorio_id: int,
        top_k: int = 10,
        filtros: dict[str, Any] | None = None,
    ) -> list[ResultadoBuscaMock]:
        """Retorna documentos baseado na query."""
        await asyncio.sleep(0.05)  # Simula latência de DB

        # Se query contém "LGPD", retorna documentos relevantes
        if "lgpd" in query_texto.lower() or "dados" in query_texto.lower():
            return self.docs_relevantes[:top_k]

        # Se query contém "irrelevante", retorna documentos de baixa relevância
        if "irrelevante" in query_texto.lower():
            return self.docs_baixa_relevancia[:top_k]

        # Query genérica → sem resultado relevante
        return []


# ============================================================================
# Testes
# ============================================================================

async def test_rag_metrics():
    """Executa série de testes contra o RAG retriever e coleta métricas."""

    print("\n" + "=" * 70)
    print("TESTE DE MÉTRICAS PROMETHEUS — RAG Retriever")
    print("=" * 70 + "\n")

    # Cria mocks
    vector_store = VectorStoreMock()
    retriever = RAGRetriever(vector_store=vector_store)

    # ========================================================================
    # Teste 1: Buscas com contexto encontrado (incrementa _rag_usado)
    # ========================================================================

    print("📊 [Teste 1] Buscas COM contexto encontrado")
    print("-" * 70)

    queries_com_contexto = [
        ("Qual é a LGPD?", None),
        ("Proteção de dados pessoais", None),
        ("Conformidade LGPD", {"tipo_acao": "LGPD", "tribunal": "STF"}),
    ]

    for query, contexto in queries_com_contexto:
        resultado = await retriever.buscar(
            query=query,
            escritorio_id=1,
            contexto_processo=contexto,
        )
        status = "✓ Contexto encontrado" if resultado else "✗ Sem contexto"
        print(f"  Query: '{query}' → {status}")

    print()

    # ========================================================================
    # Teste 2: Buscas sem contexto relevante (incrementa _rag_vazio)
    # ========================================================================

    print("📊 [Teste 2] Buscas SEM contexto encontrado (threshold)")
    print("-" * 70)

    queries_sem_contexto = [
        "termo completamente irrelevante para banco",
        "palavra aleatória xyz",
        "recurso desconhecido",
    ]

    for query in queries_sem_contexto:
        resultado = await retriever.buscar(
            query=query,
            escritorio_id=1,
        )
        status = "✓ Vazio (como esperado)" if not resultado else "✗ Com contexto"
        print(f"  Query: '{query}' → {status}")

    print()

    # ========================================================================
    # Teste 3: Teste com scores
    # ========================================================================

    print("📊 [Teste 3] Busca com scores de similaridade")
    print("-" * 70)

    contexto, scores = await retriever.buscar_com_scores(
        query="LGPD e proteção de dados",
        escritorio_id=1,
    )

    if scores:
        print(f"  Documentos encontrados: {len(scores)}")
        for i, score_info in enumerate(scores, 1):
            print(f"    {i}. Score: {score_info['score']:.4f}")
    else:
        print("  Nenhum documento com score encontrado")

    print()

    # ========================================================================
    # Coleta e exibe métricas
    # ========================================================================

    print("📈 MÉTRICAS PROMETHEUS COLETADAS")
    print("=" * 70 + "\n")

    metrics_output = generate_latest(REGISTRY).decode("utf-8")

    # Filtra apenas métricas do RAG
    rag_metrics = [
        line
        for line in metrics_output.split("\n")
        if "rag_" in line and not line.startswith("#")
    ]

    if rag_metrics:
        print("Métricas RAG Retriever:")
        for line in rag_metrics:
            print(f"  {line}")
    else:
        print("⚠️  Nenhuma métrica RAG encontrada")

    print()

    # Exibe resumo
    print("📋 RESUMO")
    print("=" * 70)
    print("""
Métricas coletadas:
  • rag_contexto_injetado_total — Respostas com contexto RAG no prompt
  • rag_contexto_vazio_total — Buscas RAG sem resultado acima do threshold
  • rag_vector_search_seconds — Latência da busca vetorial (histogram)
  • rag_search_cache_hits_total — Buscas servidas do cache Redis
  • rag_searches_total — Total de buscas realizadas (com label 'tipo')

Em produção, essas métricas são scrapeadas por Prometheus e visualizadas
em Grafana para monitorar performance e hit rate do RAG.
""")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    try:
        asyncio.run(test_rag_metrics())
        print("\n✅ Testes de métricas concluídos com sucesso!\n")
    except Exception as e:
        print(f"\n❌ Erro durante testes: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
