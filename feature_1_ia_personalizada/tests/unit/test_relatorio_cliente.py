"""
feature_1_ia_personalizada/tests/unit/test_relatorio_cliente.py
================================================================
Relatório de acompanhamento por cliente.

A garantia mais importante aqui é sobre o que o relatório **não** contém: é um
documento que o cliente corporativo vai ler, então score de risco, nível de
relacionamento e resumo interno do CRM não podem vazar nele. Esses campos são
avaliações do escritório sobre o cliente, não informação para o cliente.

O resto cobre isolamento multi-tenant, período e degradação (relatório continua
sendo emitido mesmo se a sumarização falhar).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import update

from feature_1_ia_personalizada.services.relacionamento.relatorio_cliente import (
    gerar_relatorio,
)
from shared.models.cliente import Cliente
from shared.models.interacao import Interacao
from shared.models.processo import Processo

pytestmark = pytest.mark.asyncio


def _claude(resposta="Cliente pediu atualização do processo; foi informado da fase atual."):
    c = MagicMock()
    c.chamar_direto = AsyncMock(
        return_value={
            "resposta": resposta,
            "tokens_input": 100,
            "tokens_output": 30,
            "custo": Decimal("0.001"),
        }
    )
    return c


async def _processo(db, cliente_id, escritorio_id, cnj, **campos):
    p = Processo(
        cliente_id=cliente_id,
        escritorio_id=escritorio_id,
        numero_cnj=cnj,
        polo_cliente="autor",
        status=campos.pop("status", "ativo"),
        **campos,
    )
    db.add(p)
    await db.commit()
    return p


async def _interacoes(db, cliente_id, escritorio_id, quantas=3, dias_atras=2):
    for i in range(quantas):
        db.add(
            Interacao(
                cliente_id=cliente_id,
                escritorio_id=escritorio_id,
                tipo="whatsapp_texto",
                direcao="entrada",
                mensagem_cliente=f"Pergunta {i}",
                mensagem_ia=f"Resposta {i}",
                created_at=datetime.now(UTC) - timedelta(days=dias_atras),
            )
        )
    await db.commit()


class TestConteudo:
    async def test_inclui_processos_e_andamento(
        self, db_session, escritorio_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        cliente = await cliente_factory(escritorio_id=escritorio.id, nome="Construtora Alfa")
        await _processo(
            db_session,
            cliente.id,
            escritorio.id,
            "1111111-11.2026.8.26.0100",
            fase_processual="Instrução",
            ultimo_andamento="Juntada de petição",
            data_ultimo_andamento=datetime.now(UTC) - timedelta(days=3),
        )

        rel = await gerar_relatorio(
            db_session, _claude(), cliente.id, escritorio.id, nome_escritorio="Silva & Assoc."
        )

        assert rel is not None
        assert rel.cliente_nome == "Construtora Alfa"
        assert len(rel.processos) == 1
        assert "1111111-11.2026.8.26.0100" in rel.texto
        assert "Juntada de petição" in rel.texto
        assert "Silva & Assoc." in rel.texto

    async def test_conta_interacoes_do_periodo(
        self, db_session, escritorio_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        cliente = await cliente_factory(escritorio_id=escritorio.id)
        await _interacoes(db_session, cliente.id, escritorio.id, quantas=3, dias_atras=2)
        await _interacoes(db_session, cliente.id, escritorio.id, quantas=2, dias_atras=90)

        rel = await gerar_relatorio(db_session, _claude(), cliente.id, escritorio.id, dias=30)

        assert rel is not None
        assert rel.total_interacoes == 3, "interação fora da janela não pode entrar"

    async def test_sem_processo_ativo_informa_explicitamente(
        self, db_session, escritorio_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        cliente = await cliente_factory(escritorio_id=escritorio.id)

        rel = await gerar_relatorio(db_session, _claude(), cliente.id, escritorio.id)

        assert rel is not None
        assert "Nenhum processo ativo" in rel.texto

    async def test_processo_arquivado_nao_entra(
        self, db_session, escritorio_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        cliente = await cliente_factory(escritorio_id=escritorio.id)
        await _processo(
            db_session, cliente.id, escritorio.id, "2222222-22.2026.8.26.0100", status="arquivado"
        )

        rel = await gerar_relatorio(db_session, _claude(), cliente.id, escritorio.id)
        assert rel is not None
        assert rel.processos == []


class TestNaoVazaDadoInterno:
    async def test_score_e_nivel_de_risco_ficam_fora(
        self, db_session, escritorio_factory, cliente_factory
    ):
        """O cliente lê este documento: avaliação interna não pode aparecer."""
        escritorio = await escritorio_factory()
        cliente = await cliente_factory(escritorio_id=escritorio.id)
        await db_session.execute(
            update(Cliente)
            .where(Cliente.id == cliente.id)
            .values(
                crm_nivel="critico",
                crm_score=7,
                crm_resumo="Cliente difícil, reclama de tudo.",
                crm_acao_sugerida="Ligar antes que cancele o contrato",
            )
        )
        await db_session.commit()
        await _interacoes(db_session, cliente.id, escritorio.id, quantas=1)

        rel = await gerar_relatorio(db_session, _claude(), cliente.id, escritorio.id)

        assert rel is not None
        texto = rel.texto.lower()
        assert "critico" not in texto
        assert "7/100" not in texto
        assert "difícil" not in texto
        assert "cancele o contrato" not in texto


class TestIsolamentoEDegradacao:
    async def test_cliente_de_outro_escritorio_retorna_none(
        self, db_session, escritorio_factory, cliente_factory
    ):
        esc_a = await escritorio_factory()
        esc_b = await escritorio_factory()
        cliente_b = await cliente_factory(escritorio_id=esc_b.id)

        assert await gerar_relatorio(db_session, _claude(), cliente_b.id, esc_a.id) is None

    async def test_cliente_inativo_retorna_none(
        self, db_session, escritorio_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        cliente = await cliente_factory(escritorio_id=escritorio.id)
        await db_session.execute(
            update(Cliente).where(Cliente.id == cliente.id).values(ativo=False)
        )
        await db_session.commit()

        assert await gerar_relatorio(db_session, _claude(), cliente.id, escritorio.id) is None

    async def test_falha_da_sumarizacao_nao_impede_o_relatorio(
        self, db_session, escritorio_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        cliente = await cliente_factory(escritorio_id=escritorio.id)
        await _processo(db_session, cliente.id, escritorio.id, "3333333-33.2026.8.26.0100")
        await _interacoes(db_session, cliente.id, escritorio.id, quantas=2)

        claude = MagicMock()
        claude.chamar_direto = AsyncMock(side_effect=RuntimeError("modelo fora"))

        rel = await gerar_relatorio(db_session, claude, cliente.id, escritorio.id)

        assert rel is not None
        assert "3333333-33.2026.8.26.0100" in rel.texto
        assert "Não foi possível resumir" in rel.resumo_atendimento

    async def test_pode_dispensar_o_resumo(self, db_session, escritorio_factory, cliente_factory):
        escritorio = await escritorio_factory()
        cliente = await cliente_factory(escritorio_id=escritorio.id)
        await _interacoes(db_session, cliente.id, escritorio.id, quantas=2)
        claude = _claude()

        rel = await gerar_relatorio(
            db_session, claude, cliente.id, escritorio.id, incluir_resumo=False
        )

        assert rel is not None
        assert rel.resumo_atendimento == ""
        claude.chamar_direto.assert_not_awaited()
