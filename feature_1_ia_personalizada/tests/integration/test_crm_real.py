# feature_1_ia_personalizada/tests/integration/test_crm_real.py
"""
Testes de integração para CRM Inteligente (Feature 7).

Usa banco SQLite em memória (via conftest). Claude é mockado.

Cobertura:
  - CRMDataAggregator agrega corretamente sem duplicar dados
  - Multi-tenant: cliente de outro escritório não aparece
  - GET /crm/clientes?nivel=em_risco retorna apenas clientes naquele nível
  - POST /crm/clientes/{id}/analisar persiste resultado no banco
  - GET /crm/resumo conta corretamente por nível
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.cliente import Cliente
from shared.models.interacao import Interacao
from shared.models.processo import Processo
from shared.security.jwt import criar_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers(user_id: int, escritorio_id: int) -> dict:
    token = criar_token(user_id=user_id, escritorio_id=escritorio_id, role="admin")
    return {"Authorization": f"Bearer {token}"}


async def _criar_cliente(db: AsyncSession, escritorio_id: int, nome: str = "Cliente Teste") -> Cliente:
    from faker import Faker
    fake = Faker("pt_BR")
    cliente = Cliente(
        escritorio_id=escritorio_id,
        nome=nome,
        telefone_whatsapp="5511" + fake.msisdn()[4:],
        cpf=fake.cpf(),
    )
    db.add(cliente)
    await db.commit()
    await db.refresh(cliente)
    return cliente


async def _criar_interacao(
    db: AsyncSession,
    cliente_id: int,
    escritorio_id: int,
    satisfacao: int | None = None,
) -> Interacao:
    interacao = Interacao(
        cliente_id=cliente_id,
        escritorio_id=escritorio_id,
        tipo="whatsapp_texto",
        direcao="entrada",
        mensagem_cliente="Olá, como está meu processo?",
        mensagem_ia="Seu processo está em andamento.",
        satisfacao=satisfacao,
    )
    db.add(interacao)
    await db.commit()
    await db.refresh(interacao)
    return interacao


async def _criar_processo(
    db: AsyncSession,
    cliente_id: int,
    escritorio_id: int,
    score_nivel: str = "baixo",
) -> Processo:
    processo = Processo(
        cliente_id=cliente_id,
        escritorio_id=escritorio_id,
        numero_cnj=f"000000{cliente_id}-00.2024.8.26.0100",
        polo_cliente="autor",
        status="ativo",
        score_nivel=score_nivel,
    )
    db.add(processo)
    await db.commit()
    await db.refresh(processo)
    return processo


# ---------------------------------------------------------------------------
# CRMDataAggregator — sem duplicatas
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aggregator_sem_duplicatas(
    async_db: AsyncSession,
    escritorio_factory,
):
    from feature_1_ia_personalizada.services.crm.aggregator import CRMDataAggregator

    escritorio = await escritorio_factory()
    cliente = await _criar_cliente(async_db, escritorio.id)

    # Cria 3 interações com NPS
    for nota in [3, 4, 5]:
        await _criar_interacao(async_db, cliente.id, escritorio.id, satisfacao=nota)
    await _criar_processo(async_db, cliente.id, escritorio.id)

    aggregator = CRMDataAggregator(async_db)
    ctx = await aggregator.coletar_contexto_cliente(cliente.id, escritorio.id)

    # NPS histórico deve ter exatamente 3 registros (sem duplicatas por JOIN)
    assert len(ctx.nps_historico) == 3
    assert ctx.nps_medio_3m is not None
    assert round(ctx.nps_medio_3m, 1) == round((3 + 4 + 5) / 3, 1)


# ---------------------------------------------------------------------------
# Multi-tenant — cliente de outro escritório não aparece
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aggregator_multitenant_bloqueia_outro_escritorio(
    async_db: AsyncSession,
    escritorio_factory,
):
    from feature_1_ia_personalizada.services.crm.aggregator import CRMDataAggregator

    escritorio_a = await escritorio_factory()
    escritorio_b = await escritorio_factory()

    cliente_b = await _criar_cliente(async_db, escritorio_b.id, "Cliente B")

    aggregator = CRMDataAggregator(async_db)

    with pytest.raises(ValueError, match="não encontrado"):
        await aggregator.coletar_contexto_cliente(cliente_b.id, escritorio_a.id)


# ---------------------------------------------------------------------------
# GET /crm/clientes?nivel=em_risco
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_listar_clientes_filtra_por_nivel(
    async_client: AsyncClient,
    async_db: AsyncSession,
    escritorio_factory,
    usuario_factory,
):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _headers(user_id=usuario.id, escritorio_id=escritorio.id)

    # Cria dois clientes com níveis distintos
    c1 = await _criar_cliente(async_db, escritorio.id, "Em Risco")
    c2 = await _criar_cliente(async_db, escritorio.id, "Excelente")

    await async_db.execute(
        update(Cliente).where(Cliente.id == c1.id).values(crm_nivel="em_risco", crm_score=20)
    )
    await async_db.execute(
        update(Cliente).where(Cliente.id == c2.id).values(crm_nivel="excelente", crm_score=90)
    )
    await async_db.commit()

    resp = await async_client.get("/crm/clientes?nivel=em_risco", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["nome"] == "Em Risco"
    assert data[0]["crm_nivel"] == "em_risco"


# ---------------------------------------------------------------------------
# POST /crm/clientes/{id}/analisar persiste resultado
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analisar_cliente_persiste_no_banco(
    async_client: AsyncClient,
    async_db: AsyncSession,
    escritorio_factory,
    usuario_factory,
):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _headers(user_id=usuario.id, escritorio_id=escritorio.id)

    cliente = await _criar_cliente(async_db, escritorio.id, "Cliente Análise")
    await _criar_interacao(async_db, cliente.id, escritorio.id, satisfacao=4)

    payload_claude = json.dumps({
        "resumo": "Cliente com bom engajamento.",
        "acao_sugerida": "Nenhuma ação necessária",
    })
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=payload_claude)]
    mock_msg.usage = MagicMock(input_tokens=150, output_tokens=40)

    with patch(
        "feature_1_ia_personalizada.api.routes.crm.ClaudeClient"
    ) as MockClaude:
        mock_claude_inst = MagicMock()
        mock_claude_inst._client = AsyncMock()
        mock_claude_inst._client.messages.create = AsyncMock(return_value=mock_msg)
        MockClaude.return_value = mock_claude_inst

        resp = await async_client.post(
            f"/crm/clientes/{cliente.id}/analisar", headers=headers
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["nivel"] in {"excelente", "satisfeito", "neutro", "em_risco", "critico"}
    assert "score" in data
    assert "resumo" in data

    # Verifica persistência no banco
    await async_db.refresh(cliente)
    assert cliente.crm_nivel is not None
    assert cliente.crm_score is not None
    assert cliente.crm_analisado_em is not None


# ---------------------------------------------------------------------------
# GET /crm/resumo conta corretamente por nível
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resumo_conta_por_nivel(
    async_client: AsyncClient,
    async_db: AsyncSession,
    escritorio_factory,
    usuario_factory,
):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _headers(user_id=usuario.id, escritorio_id=escritorio.id)

    niveis = ["critico", "critico", "em_risco", "neutro", "excelente"]
    for i, nivel in enumerate(niveis):
        c = await _criar_cliente(async_db, escritorio.id, f"Cliente {i}")
        await async_db.execute(
            update(Cliente).where(Cliente.id == c.id).values(crm_nivel=nivel, crm_score=10 * (i + 1))
        )
    # Um cliente sem análise
    await _criar_cliente(async_db, escritorio.id, "Sem análise")
    await async_db.commit()

    resp = await async_client.get("/crm/resumo", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["critico"] == 2
    assert data["em_risco"] == 1
    assert data["neutro"] == 1
    assert data["excelente"] == 1
    assert data["satisfeito"] == 0
    assert data["sem_analise"] == 1


# ---------------------------------------------------------------------------
# GET /crm/clientes/{id} retorna 404 para cliente de outro escritório
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detalhe_cliente_outro_escritorio_retorna_404(
    async_client: AsyncClient,
    async_db: AsyncSession,
    escritorio_factory,
    usuario_factory,
):
    escritorio_a = await escritorio_factory()
    escritorio_b = await escritorio_factory()
    usuario_a = await usuario_factory(escritorio_id=escritorio_a.id)
    headers_a = _headers(user_id=usuario_a.id, escritorio_id=escritorio_a.id)

    cliente_b = await _criar_cliente(async_db, escritorio_b.id, "Cliente B")

    resp = await async_client.get(f"/crm/clientes/{cliente_b.id}", headers=headers_a)
    assert resp.status_code == 404
