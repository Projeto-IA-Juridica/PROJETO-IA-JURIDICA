"""
feature_1_ia_personalizada/tests/unit/test_escalacoes_query.py
==============================================================
Regressão das queries que filtram escalações por status dentro de
`Interacao.metadata_json`.

Dois bugs reais motivaram estes testes:

1. `GET /escalacoes` usava `.astext`, que só existe no tipo JSONB do dialeto
   Postgres. Como `Interacao.metadata_json` é `JSON` genérico, a expressão
   levantava AttributeError na CONSTRUÇÃO da query — 500 em toda listagem, em
   qualquer ambiente.

2. `CRMDataAggregator` lia a chave plana `metadata_json["escalacao_status"]`,
   que nunca é escrita (o EscalacaoManager grava aninhado em
   `{"escalacao": {"status": ...}}`). A query era válida, então não falhava:
   apenas contava sempre zero escalações, distorcendo a análise de CRM.

Ambos passam despercebidos sem teste com banco: o primeiro só aparece ao
construir a query, o segundo só aparece ao conferir o número retornado.
"""

from __future__ import annotations

import pytest
from sqlalchemy import and_, func, select
from sqlalchemy.dialects import postgresql, sqlite

from shared.models.interacao import Interacao

pytestmark = pytest.mark.asyncio

_ESC_STATUS = Interacao.metadata_json["escalacao"]["status"].as_string()


def _escalacao(escritorio_id: int, cliente_id: int, status: str) -> Interacao:
    return Interacao(
        escritorio_id=escritorio_id,
        cliente_id=cliente_id,
        tipo="escalacao",
        direcao="saida",
        mensagem_cliente="Quero saber do meu processo",
        mensagem_ia="Sugestão gerada pela IA",
        metadata_json={
            "escalacao": {
                "status": status,
                "motivo": "duvida_juridica_complexa",
                "sugestao_resposta": "Sugestão gerada pela IA",
            }
        },
    )


class TestCompilacaoMultiDialeto:
    """O filtro precisa compilar tanto em Postgres (produção) quanto SQLite (testes)."""

    @pytest.mark.parametrize(
        "dialeto",
        [postgresql.dialect(), sqlite.dialect()],
        ids=["postgresql", "sqlite"],
    )
    async def test_filtro_compila_no_dialeto(self, dialeto):
        # Não deve levantar: era exatamente aqui que `.astext` estourava.
        sql = str((_ESC_STATUS == "pendente").compile(dialect=dialeto))
        assert sql

    async def test_astext_continua_indisponivel_neste_modelo(self):
        """Documenta a causa raiz: `.astext` não existe em coluna JSON genérica."""
        with pytest.raises(AttributeError):
            Interacao.metadata_json["escalacao"]["status"].astext  # noqa: B018


class TestFiltroPorStatus:
    """Query da rota GET /escalacoes."""

    async def test_retorna_apenas_o_status_pedido(
        self, db_session, escritorio_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        cliente = await cliente_factory(escritorio_id=escritorio.id)
        for status in ("pendente", "pendente", "rejeitada", "aprovada"):
            db_session.add(_escalacao(escritorio.id, cliente.id, status))
        await db_session.commit()

        stmt = select(Interacao).where(
            Interacao.escritorio_id == escritorio.id,
            Interacao.tipo == "escalacao",
            _ESC_STATUS == "pendente",
        )
        pendentes = (await db_session.execute(stmt)).scalars().all()

        assert len(pendentes) == 2
        assert all(i.metadata_json["escalacao"]["status"] == "pendente" for i in pendentes)

    async def test_nao_vaza_escalacao_de_outro_escritorio(
        self, db_session, escritorio_factory, cliente_factory
    ):
        escritorio_a = await escritorio_factory()
        escritorio_b = await escritorio_factory()
        cliente_a = await cliente_factory(escritorio_id=escritorio_a.id)
        cliente_b = await cliente_factory(escritorio_id=escritorio_b.id)
        db_session.add(_escalacao(escritorio_a.id, cliente_a.id, "pendente"))
        db_session.add(_escalacao(escritorio_b.id, cliente_b.id, "pendente"))
        await db_session.commit()

        stmt = select(Interacao).where(
            Interacao.escritorio_id == escritorio_a.id,
            Interacao.tipo == "escalacao",
            _ESC_STATUS == "pendente",
        )
        assert len((await db_session.execute(stmt)).scalars().all()) == 1


class TestContagemDoAggregator:
    """Contagens que alimentam a análise de CRM."""

    async def test_conta_pendentes_e_rejeitadas(
        self, db_session, escritorio_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        cliente = await cliente_factory(escritorio_id=escritorio.id)
        for status in ("pendente", "pendente", "pendente", "rejeitada", "aprovada"):
            db_session.add(_escalacao(escritorio.id, cliente.id, status))
        await db_session.commit()

        stmt = select(
            func.count().filter(_ESC_STATUS == "pendente").label("pendentes"),
            func.count()
            .filter(and_(_ESC_STATUS == "rejeitada", Interacao.id.is_not(None)))
            .label("rejeitadas"),
        ).where(
            Interacao.cliente_id == cliente.id,
            Interacao.escritorio_id == escritorio.id,
        )
        row = (await db_session.execute(stmt)).one()

        # Com a chave plana antiga ("escalacao_status") ambos vinham zero.
        assert row.pendentes == 3
        assert row.rejeitadas == 1

    async def test_chave_plana_antiga_nao_encontra_nada(
        self, db_session, escritorio_factory, cliente_factory
    ):
        """Prova que o caminho antigo era silenciosamente vazio."""
        escritorio = await escritorio_factory()
        cliente = await cliente_factory(escritorio_id=escritorio.id)
        db_session.add(_escalacao(escritorio.id, cliente.id, "pendente"))
        await db_session.commit()

        antigo = Interacao.metadata_json["escalacao_status"].as_string()
        stmt = select(func.count().filter(antigo == "pendente").label("total")).where(
            Interacao.cliente_id == cliente.id
        )
        assert (await db_session.execute(stmt)).one().total == 0


class TestHandlerDaRota:
    """
    Exercita o handler real de GET /escalacoes contra o banco.

    Chama a função diretamente em vez de passar pelo cliente HTTP: o app
    completo carrega o prometheus-fastapi-instrumentator, que é incompatível
    com a versão de FastAPI instalada em algumas máquinas de desenvolvimento
    (`'_IncludedRouter' object has no attribute 'path'`). O objetivo aqui é o
    handler — autenticação e middlewares têm cobertura própria.
    """

    async def test_lista_apenas_pendentes_com_nome_do_cliente(
        self, db_session, escritorio_factory, cliente_factory
    ):
        from feature_1_ia_personalizada.api.routes.escalacoes import listar_escalacoes

        escritorio = await escritorio_factory()
        cliente = await cliente_factory(escritorio_id=escritorio.id, nome="Construtora Alfa")
        db_session.add(_escalacao(escritorio.id, cliente.id, "pendente"))
        db_session.add(_escalacao(escritorio.id, cliente.id, "aprovada"))
        await db_session.commit()

        itens = await listar_escalacoes(
            status_filtro="pendente",
            page=1,
            limit=25,
            escritorio_id=escritorio.id,
            db=db_session,
        )

        assert len(itens) == 1
        assert itens[0].status_escalacao == "pendente"
        assert itens[0].cliente_nome == "Construtora Alfa"
        assert itens[0].sugestao_resposta == "Sugestão gerada pela IA"
        assert itens[0].motivo == "duvida_juridica_complexa"

    async def test_status_invalido_levanta_422(self, db_session, escritorio_factory):
        from fastapi import HTTPException

        from feature_1_ia_personalizada.api.routes.escalacoes import listar_escalacoes

        escritorio = await escritorio_factory()

        with pytest.raises(HTTPException) as exc:
            await listar_escalacoes(
                status_filtro="inexistente",
                page=1,
                limit=25,
                escritorio_id=escritorio.id,
                db=db_session,
            )
        assert exc.value.status_code == 422

    async def test_sem_escalacoes_retorna_lista_vazia(self, db_session, escritorio_factory):
        from feature_1_ia_personalizada.api.routes.escalacoes import listar_escalacoes

        escritorio = await escritorio_factory()

        itens = await listar_escalacoes(
            status_filtro="pendente",
            page=1,
            limit=25,
            escritorio_id=escritorio.id,
            db=db_session,
        )
        assert itens == []
