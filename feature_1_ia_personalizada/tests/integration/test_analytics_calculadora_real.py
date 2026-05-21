# feature_1_ia_personalizada/tests/integration/test_analytics_calculadora_real.py
"""
Testes de integração REAIS para CalculadoraAnalytics (Feature 5).

Estratégia:
  - Insere Interacao e Cliente reais no banco SQLite de testes (sem mocks).
  - Chama CalculadoraAnalytics com a sessão real.
  - Valida que os valores calculados batem exatamente com os dados inseridos.
  - tendencia_semanal usa date_trunc (PostgreSQL-only) → skipado com marca explícita.

Cobertura:
  - obter_resumo: total_interacoes, clientes_ativos, nps_medio, variacao_nps
  - obter_resumo: zero interações (edge case)
  - obter_resumo: isolamento multi-tenant
  - obter_eficiencia: percentual_autonomia, custo_total, horas_economizadas
  - obter_eficiencia: zero interações (sem divisão por zero)
  - ranking_clientes: em_risco=True (NPS baixo + sem contato recente)
  - ranking_clientes: sem_avaliacao=True (nenhum NPS respondido)
  - ranking_clientes: NPS baixo mas contato recente → não em_risco
  - ranking_clientes: isolamento multi-tenant (outro escritório não aparece)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.analytics.calculadora import CalculadoraAnalytics
from shared.models.cliente import Cliente
from shared.models.interacao import Interacao

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_cpf_seq = 0


def _cpf_unico() -> str:
    global _cpf_seq
    _cpf_seq += 1
    return f"{_cpf_seq:011d}"


async def _criar_cliente(db: AsyncSession, escritorio_id: int, nome: str = "Cliente Teste") -> Cliente:
    c = Cliente(
        escritorio_id=escritorio_id,
        nome=nome,
        telefone_whatsapp="5511999990000",
        cpf=_cpf_unico(),
        email=f"{nome.lower().replace(' ', '.')}_{_cpf_seq}@test.com",
    )
    db.add(c)
    await db.flush()
    return c


async def _criar_interacao(
    db: AsyncSession,
    escritorio_id: int,
    cliente_id: int,
    direcao: str = "saida",
    satisfacao: int | None = None,
    custo: Decimal = Decimal("0.01"),
    tempo_ms: int | None = 500,
) -> Interacao:
    i = Interacao(
        escritorio_id=escritorio_id,
        cliente_id=cliente_id,
        tipo="whatsapp_texto",
        direcao=direcao,
        mensagem_cliente="Olá",
        satisfacao=satisfacao,
        custo_estimado=custo,
        tempo_resposta_ms=tempo_ms,
    )
    db.add(i)
    await db.flush()
    return i


# ---------------------------------------------------------------------------
# obter_resumo — dados reais
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_obter_resumo_total_interacoes_real(async_db: AsyncSession, escritorio_factory):
    escritorio = await escritorio_factory()
    cliente = await _criar_cliente(async_db, escritorio.id)

    await _criar_interacao(async_db, escritorio.id, cliente.id)
    await _criar_interacao(async_db, escritorio.id, cliente.id)
    await _criar_interacao(async_db, escritorio.id, cliente.id)
    await async_db.commit()

    calc = CalculadoraAnalytics(async_db, escritorio_id=escritorio.id, dias=30)
    result = await calc.obter_resumo()

    assert result["total_interacoes"] == 3
    assert result["clientes_ativos"] == 1


@pytest.mark.asyncio
async def test_obter_resumo_clientes_ativos_distintos(async_db: AsyncSession, escritorio_factory):
    escritorio = await escritorio_factory()
    c1 = await _criar_cliente(async_db, escritorio.id, "Ana")
    c2 = await _criar_cliente(async_db, escritorio.id, "Bruno")

    await _criar_interacao(async_db, escritorio.id, c1.id)
    await _criar_interacao(async_db, escritorio.id, c1.id)
    await _criar_interacao(async_db, escritorio.id, c2.id)
    await async_db.commit()

    calc = CalculadoraAnalytics(async_db, escritorio_id=escritorio.id, dias=30)
    result = await calc.obter_resumo()

    assert result["total_interacoes"] == 3
    assert result["clientes_ativos"] == 2


@pytest.mark.asyncio
async def test_obter_resumo_nps_medio_calculado(async_db: AsyncSession, escritorio_factory):
    escritorio = await escritorio_factory()
    cliente = await _criar_cliente(async_db, escritorio.id)

    # NPS: 4, 2, 5 → média = 3.7
    await _criar_interacao(async_db, escritorio.id, cliente.id, satisfacao=4)
    await _criar_interacao(async_db, escritorio.id, cliente.id, satisfacao=2)
    await _criar_interacao(async_db, escritorio.id, cliente.id, satisfacao=5)
    # Interação sem NPS — não deve entrar na média
    await _criar_interacao(async_db, escritorio.id, cliente.id, satisfacao=None)
    await async_db.commit()

    calc = CalculadoraAnalytics(async_db, escritorio_id=escritorio.id, dias=30)
    result = await calc.obter_resumo()

    assert result["nps_medio"] == 3.7
    assert result["total_interacoes"] == 4


@pytest.mark.asyncio
async def test_obter_resumo_zero_interacoes(async_db: AsyncSession, escritorio_factory):
    escritorio = await escritorio_factory()

    calc = CalculadoraAnalytics(async_db, escritorio_id=escritorio.id, dias=30)
    result = await calc.obter_resumo()

    assert result["total_interacoes"] == 0
    assert result["clientes_ativos"] == 0
    assert result["nps_medio"] == 0.0
    assert result["variacao_nps"] == "+0.0"


@pytest.mark.asyncio
async def test_obter_resumo_isolamento_multitenancy(async_db: AsyncSession, escritorio_factory):
    esc1 = await escritorio_factory()
    esc2 = await escritorio_factory()

    c1 = await _criar_cliente(async_db, esc1.id, "Cliente ESC1")
    c2 = await _criar_cliente(async_db, esc2.id, "Cliente ESC2")

    # Escritório 1: 5 interações
    for _ in range(5):
        await _criar_interacao(async_db, esc1.id, c1.id)
    # Escritório 2: 2 interações
    for _ in range(2):
        await _criar_interacao(async_db, esc2.id, c2.id)

    await async_db.commit()

    resumo1 = await CalculadoraAnalytics(async_db, escritorio_id=esc1.id, dias=30).obter_resumo()
    resumo2 = await CalculadoraAnalytics(async_db, escritorio_id=esc2.id, dias=30).obter_resumo()

    assert resumo1["total_interacoes"] == 5
    assert resumo2["total_interacoes"] == 2


# ---------------------------------------------------------------------------
# obter_eficiencia — dados reais
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_obter_eficiencia_percentual_autonomia_real(async_db: AsyncSession, escritorio_factory):
    escritorio = await escritorio_factory()
    cliente = await _criar_cliente(async_db, escritorio.id)

    # 6 saídas (IA) + 4 entradas (cliente) = 10 total; autonomia = 60%
    for _ in range(6):
        await _criar_interacao(async_db, escritorio.id, cliente.id, direcao="saida")
    for _ in range(4):
        await _criar_interacao(async_db, escritorio.id, cliente.id, direcao="entrada")
    await async_db.commit()

    calc = CalculadoraAnalytics(async_db, escritorio_id=escritorio.id, dias=30)
    result = await calc.obter_eficiencia()

    assert result["interacoes_sem_humano"] == 6
    assert result["percentual_autonomia"] == 60.0
    # 6 saídas × 8min / 60 = 0.8 horas
    assert result["horas_economizadas_estimadas"] == 0.8


@pytest.mark.asyncio
async def test_obter_eficiencia_custo_total_real(async_db: AsyncSession, escritorio_factory):
    escritorio = await escritorio_factory()
    cliente = await _criar_cliente(async_db, escritorio.id)

    await _criar_interacao(async_db, escritorio.id, cliente.id, custo=Decimal("0.10"))
    await _criar_interacao(async_db, escritorio.id, cliente.id, custo=Decimal("0.25"))
    await _criar_interacao(async_db, escritorio.id, cliente.id, custo=Decimal("0.05"))
    await async_db.commit()

    calc = CalculadoraAnalytics(async_db, escritorio_id=escritorio.id, dias=30)
    result = await calc.obter_eficiencia()

    assert result["custo_total_usd"] == 0.40


@pytest.mark.asyncio
async def test_obter_eficiencia_zero_interacoes_sem_divisao_por_zero(
    async_db: AsyncSession, escritorio_factory
):
    escritorio = await escritorio_factory()

    calc = CalculadoraAnalytics(async_db, escritorio_id=escritorio.id, dias=30)
    result = await calc.obter_eficiencia()

    assert result["percentual_autonomia"] == 0.0
    assert result["horas_economizadas_estimadas"] == 0.0
    assert result["custo_total_usd"] == 0.0


# ---------------------------------------------------------------------------
# ranking_clientes — dados reais
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ranking_clientes_em_risco_real(async_db: AsyncSession, escritorio_factory):
    """NPS baixo + sem contato há > 30 dias → em_risco=True."""
    escritorio = await escritorio_factory()
    cliente = await _criar_cliente(async_db, escritorio.id, "Maria em Risco")

    interacao = await _criar_interacao(async_db, escritorio.id, cliente.id, satisfacao=2)
    await async_db.commit()

    # Simula contato antigo: 45 dias atrás
    await async_db.execute(
        text("UPDATE interacoes SET created_at = :dt WHERE id = :id"),
        {"dt": datetime.now(UTC) - timedelta(days=45), "id": interacao.id},
    )
    await async_db.commit()

    calc = CalculadoraAnalytics(async_db, escritorio_id=escritorio.id, dias=90)
    result = await calc.ranking_clientes()

    assert len(result) == 1
    assert result[0]["nome"] == "Maria em Risco"
    assert result[0]["em_risco"] is True
    assert result[0]["sem_avaliacao"] is False
    assert result[0]["nps_medio"] == 2.0


@pytest.mark.asyncio
async def test_ranking_clientes_sem_avaliacao_real(async_db: AsyncSession, escritorio_factory):
    """Interações sem nota NPS → sem_avaliacao=True, em_risco=False."""
    escritorio = await escritorio_factory()
    cliente = await _criar_cliente(async_db, escritorio.id, "João Sem Nota")

    await _criar_interacao(async_db, escritorio.id, cliente.id, satisfacao=None)
    await _criar_interacao(async_db, escritorio.id, cliente.id, satisfacao=None)
    await async_db.commit()

    calc = CalculadoraAnalytics(async_db, escritorio_id=escritorio.id, dias=30)
    result = await calc.ranking_clientes()

    assert len(result) == 1
    assert result[0]["sem_avaliacao"] is True
    assert result[0]["em_risco"] is False
    assert result[0]["nps_medio"] is None


@pytest.mark.asyncio
async def test_ranking_clientes_nps_baixo_contato_recente_nao_em_risco(
    async_db: AsyncSession, escritorio_factory
):
    """NPS baixo mas contato recente (< 30 dias) → não é em_risco."""
    escritorio = await escritorio_factory()
    cliente = await _criar_cliente(async_db, escritorio.id, "Ana Insatisfeita Ativa")

    # Interação com NPS baixo e created_at agora (recente)
    await _criar_interacao(async_db, escritorio.id, cliente.id, satisfacao=1)
    await async_db.commit()

    calc = CalculadoraAnalytics(async_db, escritorio_id=escritorio.id, dias=30)
    result = await calc.ranking_clientes()

    assert result[0]["em_risco"] is False
    assert result[0]["nps_medio"] == 1.0


@pytest.mark.asyncio
async def test_ranking_clientes_isolamento_multitenancy_real(
    async_db: AsyncSession, escritorio_factory
):
    """Clientes de outro escritório NÃO aparecem no ranking."""
    esc1 = await escritorio_factory()
    esc2 = await escritorio_factory()

    c1 = await _criar_cliente(async_db, esc1.id, "Cliente do ESC1")
    c2 = await _criar_cliente(async_db, esc2.id, "Cliente do ESC2")

    await _criar_interacao(async_db, esc1.id, c1.id, satisfacao=4)
    await _criar_interacao(async_db, esc2.id, c2.id, satisfacao=2)
    await async_db.commit()

    ranking_esc1 = await CalculadoraAnalytics(async_db, escritorio_id=esc1.id, dias=30).ranking_clientes()
    ranking_esc2 = await CalculadoraAnalytics(async_db, escritorio_id=esc2.id, dias=30).ranking_clientes()

    assert len(ranking_esc1) == 1
    assert ranking_esc1[0]["nome"] == "Cliente do ESC1"

    assert len(ranking_esc2) == 1
    assert ranking_esc2[0]["nome"] == "Cliente do ESC2"


@pytest.mark.asyncio
async def test_ranking_clientes_sem_interacoes_retorna_vazio(
    async_db: AsyncSession, escritorio_factory
):
    escritorio = await escritorio_factory()

    calc = CalculadoraAnalytics(async_db, escritorio_id=escritorio.id, dias=30)
    result = await calc.ranking_clientes()

    assert result == []


# ---------------------------------------------------------------------------
# tendencia_semanal — requer PostgreSQL (date_trunc não existe no SQLite)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="tendencia_semanal usa date_trunc (PostgreSQL-only). Rodar contra Postgres real.")
@pytest.mark.asyncio
async def test_tendencia_semanal_requer_postgres(async_db: AsyncSession, escritorio_factory):
    escritorio = await escritorio_factory()
    calc = CalculadoraAnalytics(async_db, escritorio_id=escritorio.id, dias=30)
    result = await calc.tendencia_semanal()
    assert isinstance(result, list)
