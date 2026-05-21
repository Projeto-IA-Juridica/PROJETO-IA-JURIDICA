# feature_1_ia_personalizada/services/legal_data/score_risco.py
"""
Score de Risco Processual (Feature 2).

NÃO prevê vitória/derrota (vedado pelo Provimento OAB 205/2021).
Calcula complexidade/risco operacional para uso interno do advogado.
O cliente nunca vê este número diretamente.

Fórmula (pesos em shared/config/constants.py → SCORE_RISCO_PESOS):
  1. Complexidade jurídica  25%  (tipo_acao → SCORE_RISCO_COMPLEXIDADE_POR_TIPO)
  2. Duração estimada       25%  (DataJud: tempo_medio_tramitacao_dias, normalizado)
  3. Histórico da vara      20%  (taxa_procedencia_autor do DataJud + polo do cliente)
  4. Valor da causa         15%  (faixas em salários-mínimos)
  5. Fase processual atual  15%  (SCORE_RISCO_POR_FASE — risco decresce com avanço)

Performance: cálculo em memória <50ms. DataJud já cacheado pelo cache_manager (TTL 6h).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from shared.config.constants import (
    SCORE_RISCO_COMPLEXIDADE_POR_TIPO,
    SCORE_RISCO_PESOS,
    SCORE_RISCO_POR_FASE,
    SCORE_RISCO_PRAZO_MAX_REFERENCIA,
    SCORE_RISCO_SALARIO_MINIMO_REF,
)


class ComponentesScore(BaseModel):
    complexidade_juridica: int = Field(..., ge=0, le=100)
    duracao_estimada: int = Field(..., ge=0, le=100)
    historico_vara: int = Field(..., ge=0, le=100)
    valor_causa: int = Field(..., ge=0, le=100)
    fase_processual: int = Field(..., ge=0, le=100)


class ScoreRisco(BaseModel):
    score: int = Field(..., ge=0, le=100, description="Score global 0–100")
    nivel: str = Field(..., description="baixo | moderado | alto | critico")
    componentes: ComponentesScore
    interpretacao: str = Field(..., description="Texto para o advogado — sem previsão de resultado")
    atualizado_em: datetime


def _normalizar_score(valor: float, minimo: float, maximo: float) -> int:
    if maximo <= minimo:
        return 50
    norm = (valor - minimo) / (maximo - minimo)
    return int(round(max(0.0, min(1.0, norm)) * 100))


def _componente_complexidade(tipo_acao: str | None) -> int:
    if not tipo_acao:
        return 50
    chave = tipo_acao.lower().strip()
    # Busca exata primeiro, depois substring para nomes completos do DataJud
    if chave in SCORE_RISCO_COMPLEXIDADE_POR_TIPO:
        return SCORE_RISCO_COMPLEXIDADE_POR_TIPO[chave]
    for k, v in SCORE_RISCO_COMPLEXIDADE_POR_TIPO.items():
        if k in chave or chave in k:
            return v
    return 50


def _componente_duracao(datajud_data: dict | None) -> int:
    if not datajud_data:
        return 50
    media_dias = datajud_data.get("tempo_medio_tramitacao_dias")
    if media_dias is None:
        return 50
    return _normalizar_score(float(media_dias), 0, SCORE_RISCO_PRAZO_MAX_REFERENCIA)


def _componente_historico_vara(datajud_data: dict | None, polo_cliente: str | None) -> int:
    if not datajud_data:
        return 50
    taxa = datajud_data.get("taxa_procedencia_autor")
    if taxa is None:
        return 50
    # Para o réu: risco = taxa de procedência do autor
    # Para o autor: risco = taxa de improcedência
    if polo_cliente and polo_cliente.lower() == "reu":
        return int(round(float(taxa) * 100))
    return int(round((1.0 - float(taxa)) * 100))


def _componente_valor_causa(valor_causa: float | None) -> int:
    if not valor_causa or valor_causa <= 0:
        return 50
    sm = valor_causa / SCORE_RISCO_SALARIO_MINIMO_REF
    if sm < 10:
        return 10
    if sm < 40:
        return 30
    if sm < 100:
        return 55
    if sm < 200:
        return 75
    return 95


def _componente_fase(fase_processual: str | None) -> int:
    if not fase_processual:
        return SCORE_RISCO_POR_FASE.get("conhecimento", 80)
    return SCORE_RISCO_POR_FASE.get(fase_processual.lower(), 50)


def _gerar_interpretacao_score(
    score: int,
    nivel: str,
    componentes: ComponentesScore,
    tipo_acao: str | None,
) -> str:
    """
    Texto explicativo para o advogado baseado nos componentes mais altos.
    Não menciona probabilidade de vitória/derrota (compliance OAB).
    """
    tipo_label = (tipo_acao or "processo").replace("_", " ").capitalize()

    cabecalhos = {
        "baixo": f"{tipo_label} com baixa complexidade operacional.",
        "moderado": f"{tipo_label} com complexidade moderada — acompanhamento padrão recomendado.",
        "alto": f"{tipo_label} com alta complexidade — atenção redobrada aos prazos.",
        "critico": f"{tipo_label} com complexidade crítica — revisão estratégica recomendada.",
    }
    partes = [cabecalhos.get(nivel, f"Score de risco: {score}/100.")]

    comp_dict = {
        "complexidade jurídica": componentes.complexidade_juridica,
        "duração estimada": componentes.duracao_estimada,
        "histórico da vara": componentes.historico_vara,
        "valor da causa": componentes.valor_causa,
        "fase processual": componentes.fase_processual,
    }
    top2 = sorted(comp_dict.items(), key=lambda x: x[1], reverse=True)[:2]
    drivers = " e ".join(f"{nome} ({val}/100)" for nome, val in top2 if val > 50)
    if drivers:
        partes.append(f"Principais fatores: {drivers}.")

    if componentes.duracao_estimada >= 75:
        partes.append(
            "A vara apresenta tempo médio de tramitação elevado — "
            "comunique prazo realista ao cliente."
        )
    elif componentes.duracao_estimada <= 25:
        partes.append("Vara com tramitação ágil — expectativa de prazo abaixo da média.")

    if componentes.valor_causa >= 75:
        partes.append(
            "Valor da causa elevado: documente todas as movimentações com rigor redobrado."
        )

    return " ".join(partes)


class ScoreRiscoCalculator:
    """
    Calcula o ScoreRisco de um processo judicial.

    Uso no worker:
        calc = ScoreRiscoCalculator()
        score = calc.calcular(processo, datajud_data)

    `processo` precisa ter: tipo_acao, valor_causa, fase_processual, polo_cliente
    `datajud_data` é o dict já cacheado pelo cache_manager:
        tempo_medio_tramitacao_dias, taxa_procedencia_autor
    """

    def calcular(self, processo: Any, datajud_data: dict | None = None) -> ScoreRisco:
        tipo_acao = getattr(processo, "tipo_acao", None)
        valor_causa = getattr(processo, "valor_causa", None)
        fase_processual = getattr(processo, "fase_processual", None)
        polo_cliente = getattr(processo, "polo_cliente", None)

        c_complexidade = _componente_complexidade(tipo_acao)
        c_duracao = _componente_duracao(datajud_data)
        c_historico = _componente_historico_vara(datajud_data, polo_cliente)
        c_valor = _componente_valor_causa(float(valor_causa) if valor_causa else None)
        c_fase = _componente_fase(fase_processual)

        componentes = ComponentesScore(
            complexidade_juridica=c_complexidade,
            duracao_estimada=c_duracao,
            historico_vara=c_historico,
            valor_causa=c_valor,
            fase_processual=c_fase,
        )

        score = int(
            round(
                c_complexidade * SCORE_RISCO_PESOS["complexidade_juridica"]
                + c_duracao * SCORE_RISCO_PESOS["duracao_estimada"]
                + c_historico * SCORE_RISCO_PESOS["historico_vara"]
                + c_valor * SCORE_RISCO_PESOS["valor_causa"]
                + c_fase * SCORE_RISCO_PESOS["fase_processual"]
            )
        )

        if score <= 25:
            nivel = "baixo"
        elif score <= 50:
            nivel = "moderado"
        elif score <= 75:
            nivel = "alto"
        else:
            nivel = "critico"

        return ScoreRisco(
            score=score,
            nivel=nivel,
            componentes=componentes,
            interpretacao=_gerar_interpretacao_score(score, nivel, componentes, tipo_acao),
            atualizado_em=datetime.now(UTC),
        )
