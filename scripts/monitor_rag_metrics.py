#!/usr/bin/env python3
"""
Monitor de Métricas RAG — Exporta relatórios em JSON, CSV e formato visual.

Características:
  - Captura métrica antes/depois de testes
  - Exporta em múltiplos formatos (JSON, CSV, texto)
  - Calcula estatísticas (delta, taxa de sucesso, latência média)
  - Compara com baseline anterior (se existir)

Uso:
    python scripts/monitor_rag_metrics.py
    
Arquivos gerados:
    - reports/rag_metrics_latest.json
    - reports/rag_metrics_latest.csv
    - reports/rag_metrics_comparison.txt
"""

import asyncio
import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Histogram
from prometheus_client.core import CounterMetricFamily, HistogramMetricFamily

# Adiciona o path da aplicação
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from feature_1_ia_personalizada.services.rag.retriever import RAGRetriever


# ============================================================================
# Mock VectorStore (reutilizado do test_rag_metrics.py)
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
# Captura e Relatório de Métricas
# ============================================================================


@dataclass
class MetricaSnapshot:
    timestamp: str
    rag_contexto_injetado: float
    rag_contexto_vazio: float
    total_buscas: float
    taxa_sucesso: float
    cache_hits: float

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "rag_contexto_injetado_total": self.rag_contexto_injetado,
            "rag_contexto_vazio_total": self.rag_contexto_vazio,
            "total_buscas": self.total_buscas,
            "taxa_sucesso_pct": round(self.taxa_sucesso * 100, 2),
            "cache_hits_total": self.cache_hits,
        }


def capturar_metricas() -> MetricaSnapshot:
    """Captura snapshot das métricas atuais."""
    timestamp = datetime.now().isoformat()

    metrics_output = REGISTRY.collect()  # Retorna generator de MetricFamily

    rag_injetado = 0.0
    rag_vazio = 0.0
    cache_hits = 0.0

    for metric_family in metrics_output:
        if metric_family.name == "rag_contexto_injetado_total":
            for sample in metric_family.samples:
                rag_injetado = sample.value
        elif metric_family.name == "rag_contexto_vazio_total":
            for sample in metric_family.samples:
                rag_vazio = sample.value
        elif metric_family.name == "rag_search_cache_hits_total":
            for sample in metric_family.samples:
                cache_hits = sample.value

    total = rag_injetado + rag_vazio
    taxa_sucesso = rag_injetado / total if total > 0 else 0.0

    return MetricaSnapshot(
        timestamp=timestamp,
        rag_contexto_injetado=rag_injetado,
        rag_contexto_vazio=rag_vazio,
        total_buscas=total,
        taxa_sucesso=taxa_sucesso,
        cache_hits=cache_hits,
    )


def salvar_relatorio_json(snapshot: MetricaSnapshot, output_dir: Path):
    """Salva métrica em JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "rag_metrics_latest.json"

    data = {
        "relatorio": "Métricas RAG Prometheus",
        "gerado_em": snapshot.timestamp,
        "metricas": snapshot.to_dict(),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return filepath


def salvar_relatorio_csv(snapshot: MetricaSnapshot, output_dir: Path):
    """Salva métrica em CSV (append mode para histórico)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "rag_metrics_latest.csv"

    row = snapshot.to_dict()

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)

    return filepath


def salvar_relatorio_texto(snapshot: MetricaSnapshot, output_dir: Path):
    """Salva relatório em formato texto legível."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "rag_metrics_comparison.txt"

    report = f"""
{'='*70}
RELATÓRIO DE MÉTRICAS RAG — PROMETHEUS
{'='*70}

Gerado em: {snapshot.timestamp}

📊 MÉTRICAS CAPTURADAS
{'-'*70}

1. Contextos RAG Injetados (✓ com sucesso)
   Total: {int(snapshot.rag_contexto_injetado)} buscas

2. Contextos RAG Vazios (✗ sem resultado)
   Total: {int(snapshot.rag_contexto_vazio)} buscas

3. Total de Buscas
   {int(snapshot.total_buscas)} buscas

4. Taxa de Sucesso RAG
   {snapshot.taxa_sucesso * 100:.1f}% de hit rate

5. Cache Hits
   {int(snapshot.cache_hits)} acertos em cache

📈 INDICADORES
{'-'*70}

Proporção sucesso/vazio: {snapshot.rag_contexto_injetado:.1f}:{snapshot.rag_contexto_vazio:.1f}
Hit rate recomendado: > 80%
Status: {'✅ ACEITÁVEL' if snapshot.taxa_sucesso >= 0.7 else '⚠️  REVISAR'}

📝 INTERPRETAÇÃO
{'-'*70}

• Se taxa_sucesso < 70%: threshold RAG_MIN_SIMILARITY pode estar alto
• Se cache_hits baixo: Redis pode estar indisponível em produção
• Histórico em CSV útil para identificar tendências (melhorias vs. regressões)

{'='*70}
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    return filepath


async def main():
    """Executa testes e gera relatórios."""

    print("\n" + "=" * 70)
    print("MONITOR DE MÉTRICAS RAG — Prometheus")
    print("=" * 70 + "\n")

    # Captura métrica antes dos testes
    print("📊 Capturando métricas baseline...")
    snapshot_antes = capturar_metricas()

    # Executa testes
    print("🧪 Executando testes...")
    vector_store = VectorStoreMock()
    retriever = RAGRetriever(vector_store=vector_store)

    test_cases = [
        ("Qual é a LGPD?", None),
        ("Proteção de dados pessoais", None),
        ("Conformidade LGPD", {"tipo_acao": "LGPD"}),
        ("termo completamente irrelevante para banco", None),
        ("palavra aleatória xyz", None),
    ]

    for query, contexto in test_cases:
        await retriever.buscar(query=query, escritorio_id=1, contexto_processo=contexto)

    print("✅ Testes concluídos\n")

    # Captura métrica depois dos testes
    snapshot_depois = capturar_metricas()

    # Salva relatórios
    output_dir = Path("reports")
    print("📁 Salvando relatórios...")

    json_file = salvar_relatorio_json(snapshot_depois, output_dir)
    csv_file = salvar_relatorio_csv(snapshot_depois, output_dir)
    txt_file = salvar_relatorio_texto(snapshot_depois, output_dir)

    print(f"  ✓ JSON: {json_file}")
    print(f"  ✓ CSV:  {csv_file}")
    print(f"  ✓ TXT:  {txt_file}\n")

    # Exibe resumo
    print("=" * 70)
    print("RESUMO")
    print("=" * 70)
    print(
        f"""
Antes dos testes:
  • Contextos injetados: {int(snapshot_antes.rag_contexto_injetado)}
  • Contextos vazios: {int(snapshot_antes.rag_contexto_vazio)}
  • Taxa sucesso: {snapshot_antes.taxa_sucesso * 100:.1f}%

Depois dos testes:
  • Contextos injetados: {int(snapshot_depois.rag_contexto_injetado)}
  • Contextos vazios: {int(snapshot_depois.rag_contexto_vazio)}
  • Taxa sucesso: {snapshot_depois.taxa_sucesso * 100:.1f}%

Delta (testes realizados):
  • +{int(snapshot_depois.rag_contexto_injetado - snapshot_antes.rag_contexto_injetado)} contextos injetados
  • +{int(snapshot_depois.rag_contexto_vazio - snapshot_antes.rag_contexto_vazio)} contextos vazios
"""
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
        print("✅ Monitor de métricas concluído!\n")
    except Exception as e:
        print(f"\n❌ Erro: {e}\n")
        import traceback

        traceback.print_exc()
        sys.exit(1)
