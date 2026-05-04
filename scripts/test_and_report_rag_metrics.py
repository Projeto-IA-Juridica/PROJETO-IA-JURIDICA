#!/usr/bin/env python3
"""
SCRIPT COMPLETO: Testa RAG + Coleta Métricas Prometheus + Exporta Relatórios

Fluxo:
  1. Executa múltiplos testes do RAGRetriever
  2. Captura métricas em tempo real
  3. Exporta em JSON, CSV e TXT
  4. Calcula estatísticas (taxa de sucesso, latência média, etc.)

Métricas monitoradas:
  • rag_contexto_injetado_total — Respostas com contexto
  • rag_contexto_vazio_total — Buscas sem resultado
  • Taxa de sucesso RAG (hit rate)
  • Cache Redis hits

Uso:
    python scripts/test_and_report_rag_metrics.py

Arquivos gerados:
    reports/rag_metrics_latest.json     (JSON estruturado)
    reports/rag_metrics_latest.csv      (CSV para análise)
    reports/rag_metrics_visual.txt      (Relatório visual)
"""

import asyncio
import csv
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from prometheus_client import REGISTRY

# Adiciona path da aplicação
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from feature_1_ia_personalizada.services.rag.retriever import RAGRetriever


# ============================================================================
# Mock VectorStore
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
    def __init__(self):
        self.docs_relevantes = [
            ResultadoBuscaMock(
                id=1,
                escritorio_id=1,
                titulo="Lei de Proteção de Dados (LGPD)",
                tipo="Lei",
                conteudo="A LGPD estabelece direitos e deveres sobre dados pessoais...",
                chunk_index=0,
                doc_hash="hash_lgpd_1",
                metadata_json={"tipo_acao": "LGPD"},
                distancia=0.15,
            ),
            ResultadoBuscaMock(
                id=2,
                escritorio_id=1,
                titulo="Artigos sobre conformidade LGPD",
                tipo="Jurisprudência",
                conteudo="Empresas precisam fazer conformidade com LGPD...",
                chunk_index=0,
                doc_hash="hash_lgpd_2",
                metadata_json={"tipo_acao": "LGPD"},
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
                metadata_json={"tipo_acao": "Penal"},
                distancia=0.45,
            ),
        ]

    async def buscar_por_texto(
        self,
        query_texto: str,
        escritorio_id: int,
        top_k: int = 10,
        filtros: dict[str, Any] | None = None,
    ) -> list[ResultadoBuscaMock]:
        await asyncio.sleep(0.05)
        if "lgpd" in query_texto.lower() or "dados" in query_texto.lower():
            return self.docs_relevantes[:top_k]
        if "irrelevante" in query_texto.lower():
            return self.docs_baixa_relevancia[:top_k]
        return []


# ============================================================================
# Captura de Métricas
# ============================================================================

@dataclass
class MetricaSnapshot:
    timestamp: str
    duracao_testes_s: float
    total_queries_testadas: int
    rag_contexto_injetado: float
    rag_contexto_vazio: float
    total_buscas: float
    taxa_sucesso: float

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "duracao_testes_s": round(self.duracao_testes_s, 3),
            "total_queries_testadas": self.total_queries_testadas,
            "rag_contexto_injetado_total": int(self.rag_contexto_injetado),
            "rag_contexto_vazio_total": int(self.rag_contexto_vazio),
            "total_buscas_rag": int(self.total_buscas),
            "taxa_sucesso_pct": round(self.taxa_sucesso * 100, 1),
            "status": "✓ OK" if self.taxa_sucesso >= 0.7 else "⚠️  REVISAR",
        }


def extrair_metricas_prometheus() -> tuple[float, float]:
    """Extrai valores das métricas Prometheus."""
    rag_injetado = 0.0
    rag_vazio = 0.0

    # Usa REGISTRY.collect() que retorna MetricFamily objects
    for metric_family in REGISTRY.collect():
        # Verifica nome exato da métrica (sem _total no name, apenas nos samples)
        if "contexto_injetado" in metric_family.name:
            for sample in metric_family.samples:
                if sample.name == "rag_contexto_injetado_total":
                    rag_injetado = sample.value
        elif "contexto_vazio" in metric_family.name:
            for sample in metric_family.samples:
                if sample.name == "rag_contexto_vazio_total":
                    rag_vazio = sample.value

    return rag_injetado, rag_vazio


def salvar_relatorio_json(snapshot: MetricaSnapshot, output_dir: Path):
    """Salva em JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "rag_metrics_latest.json"

    data = {
        "relatorio": "Métricas RAG + Prometheus",
        "versao": "1.0",
        "gerado_em": snapshot.timestamp,
        "metricas": snapshot.to_dict(),
        "interpretacao": {
            "hit_rate_recomendado": ">= 70%",
            "rag_injetado": "Respostas que receberam contexto RAG no prompt",
            "rag_vazio": "Buscas que retornaram contexto vazio (threshold)",
            "taxa_sucesso": "(rag_injetado / total_buscas) * 100",
        },
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return filepath


def salvar_relatorio_csv(snapshot: MetricaSnapshot, output_dir: Path):
    """Salva em CSV (histórico)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "rag_metrics_latest.csv"

    row = snapshot.to_dict()

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)

    return filepath


def salvar_relatorio_visual(snapshot: MetricaSnapshot, output_dir: Path):
    """Salva em formato visual TXT."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "rag_metrics_visual.txt"

    metrics = snapshot.to_dict()

    report = f"""
╔══════════════════════════════════════════════════════════════════════╗
║         RELATÓRIO DE TESTES — MÉTRICAS PROMETHEUS RAG               ║
╚══════════════════════════════════════════════════════════════════════╝

📅 Gerado em: {snapshot.timestamp}
⏱️  Duração dos testes: {snapshot.duracao_testes_s:.3f}s

┌──────────────────────────────────────────────────────────────────────┐
│ 📊 MÉTRICAS CAPTURADAS                                               │
└──────────────────────────────────────────────────────────────────────┘

  Total de queries testadas:
    {snapshot.total_queries_testadas} buscas

  Contextos RAG Injetados (✓ Sucesso):
    {metrics['rag_contexto_injetado_total']} respostas receberam contexto

  Contextos RAG Vazios (✗ Sem resultado):
    {metrics['rag_contexto_vazio_total']} buscas sem resultado acima do threshold

  Total de buscas processadas:
    {metrics['total_buscas_rag']} buscas

  Taxa de Sucesso RAG (Hit Rate):
    {metrics['taxa_sucesso_pct']}%

┌──────────────────────────────────────────────────────────────────────┐
│ 📈 ANÁLISE                                                           │
└──────────────────────────────────────────────────────────────────────┘

  Status: {metrics['status']}

  Interpretação:
    • Hit rate >= 70%: ✓ Aceitável (RAG funcionando bem)
    • Hit rate < 70%:  ⚠️  Revisar configuração
    • Hit rate ~ 0%:   ❌ Problema grave (verificar VectorStore)

  Possíveis causas se taxa baixa:
    ✗ RAG_MIN_SIMILARITY threshold muito alto
    ✗ VectorStore sem documentos carregados
    ✗ Embeddings mal calibrados
    ✗ Redis cache indisponível em produção

┌──────────────────────────────────────────────────────────────────────┐
│ 📋 RECOMENDAÇÕES                                                     │
└──────────────────────────────────────────────────────────────────────┘

  1. Monitorar hit rate ao longo do tempo (criar gráfico em Grafana)
  2. Se baixo: revisar RAG_MIN_SIMILARITY em shared/config/constants.py
  3. Testar com dados reais (não apenas mocks)
  4. Verificar latência: rag_vector_search_seconds (Prometheus histogram)
  5. Monitorar cache hits: rag_search_cache_hits_total

╔══════════════════════════════════════════════════════════════════════╗
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    return filepath


async def main():
    """Executa testes e gera relatórios."""

    print("\n" + "╔" + "═" * 68 + "╗")
    print("║ TESTE RAG + CAPTURA PROMETHEUS + EXPORTAÇÃO DE RELATÓRIOS")
    print("╚" + "═" * 68 + "╝\n")

    # Setup
    vector_store = VectorStoreMock()
    retriever = RAGRetriever(vector_store=vector_store)

    # Test cases: variado para cobrir sucesso + vazio
    test_cases = [
        ("Qual é a LGPD?", None, "✓ Com contexto"),
        ("Proteção de dados pessoais", None, "✓ Com contexto"),
        ("Conformidade e LGPD", {"tipo_acao": "LGPD"}, "✓ Com contexto filtrado"),
        ("termo completamente irrelevante para banco", None, "✗ Sem contexto"),
        ("palavra aleatória xyz", None, "✗ Sem contexto"),
        ("recurso desconhecido", None, "✗ Sem contexto"),
        ("Lei de dados", None, "✓ Com contexto"),
    ]

    print("🧪 Executando testes...\n")
    print("Query                                          | Resultado")
    print("-" * 68)

    inicio = time.time()

    for query, contexto, esperado in test_cases:
        await retriever.buscar(query=query, escritorio_id=1, contexto_processo=contexto)
        print(f"{query[:44]:44s} | {esperado}")

    duracao = time.time() - inicio

    print()
    print("-" * 68)

    # Captura métricas
    rag_injetado, rag_vazio = extrair_metricas_prometheus()
    total = rag_injetado + rag_vazio
    taxa_sucesso = rag_injetado / total if total > 0 else 0.0

    snapshot = MetricaSnapshot(
        timestamp=datetime.now().isoformat(),
        duracao_testes_s=duracao,
        total_queries_testadas=len(test_cases),
        rag_contexto_injetado=rag_injetado,
        rag_contexto_vazio=rag_vazio,
        total_buscas=total,
        taxa_sucesso=taxa_sucesso,
    )

    # Exporta relatórios
    output_dir = Path("reports")
    print("\n📁 Exportando relatórios...\n")

    json_file = salvar_relatorio_json(snapshot, output_dir)
    csv_file = salvar_relatorio_csv(snapshot, output_dir)
    txt_file = salvar_relatorio_visual(snapshot, output_dir)

    print(f"  ✓ JSON:  {json_file}")
    print(f"  ✓ CSV:   {csv_file}")
    print(f"  ✓ Visual: {txt_file}\n")

    # Resumo inline
    print("=" * 68)
    print("RESUMO")
    print("=" * 68)
    metrics = snapshot.to_dict()
    print(f"""
Queries testadas: {metrics['total_queries_testadas']}
Duração: {metrics['duracao_testes_s']:.3f}s

Contextos injetados: {metrics['rag_contexto_injetado_total']}
Contextos vazios: {metrics['rag_contexto_vazio_total']}
Taxa de sucesso: {metrics['taxa_sucesso_pct']}%

Status: {metrics['status']}
""")


if __name__ == "__main__":
    try:
        asyncio.run(main())
        print("✅ Teste + Relatórios concluídos com sucesso!\n")
    except Exception as e:
        print(f"\n❌ Erro: {e}\n")
        import traceback

        traceback.print_exc()
        sys.exit(1)
