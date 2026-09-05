"""
feature_1_ia_personalizada/tests/unit/test_agenda_diaria.py
============================================================
Agenda diária do advogado — "o seu dia em uma mensagem".

O que os testes garantem:

- **Cada um recebe só a sua carteira.** O corte por responsável é a razão de o
  aviso ser útil; se vazasse cliente de colega, viraria ruído e um problema de
  confidencialidade interna.
- **Silêncio quando não há nada.** Um "nada para hoje" diário treina a equipe a
  ignorar a mensagem — então advogado sem itens não entra no resultado.
- **A janela de prazos é respeitada.** Prazo distante não polui o aviso de hoje.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import update

from feature_1_ia_personalizada.services.relacionamento.agenda_diaria import (
    DIAS_DE_PRAZO,
    ItemAgenda,
    montar_agenda_do_escritorio,
    montar_mensagem,
)
from shared.models.agendamento import Agendamento
from shared.models.cliente import Cliente
from shared.models.usuario import Usuario

pytestmark = pytest.mark.asyncio

HOJE = date(2026, 8, 14)


class _PrazoFake:
    def __init__(self, cliente_id, quando, descricao="Contestação", estimado=False):
        self.cliente_id = cliente_id
        self.data = quando
        self.descricao = descricao
        self.estimado = estimado
        self.processo_id = 1
        self.numero_cnj = "1111111-11.2026.8.26.0100"


async def _advogado(db, usuario_factory, escritorio_id, numero="5511999998888"):
    u = await usuario_factory(escritorio_id=escritorio_id)
    await db.execute(update(Usuario).where(Usuario.id == u.id).values(whatsapp_numero=numero))
    await db.commit()
    await db.refresh(u)
    return u


async def _cliente_de(db, cliente_factory, escritorio_id, advogado_id, **campos):
    c = await cliente_factory(escritorio_id=escritorio_id)
    await db.execute(
        update(Cliente)
        .where(Cliente.id == c.id)
        .values(advogado_responsavel_id=advogado_id, **campos)
    )
    await db.commit()
    await db.refresh(c)
    return c


class TestMontarMensagem:
    async def test_lista_prazos_reunioes_e_riscos(self):
        cliente = Cliente(id=7, nome="Construtora Alfa", escritorio_id=1)
        cliente.crm_score = 15
        item = ItemAgenda(
            prazos=[_PrazoFake(7, HOJE)],
            reunioes=[
                Agendamento(
                    cliente_id=7,
                    escritorio_id=1,
                    status="confirmado",
                    data_hora_inicio=datetime(2026, 8, 14, 15, 0, tzinfo=UTC),
                )
            ],
            clientes_em_risco=[cliente],
        )
        texto = montar_mensagem("Marina Souza", item, HOJE, {7: "Construtora Alfa"})

        assert "Marina" in texto
        assert "HOJE" in texto and "Contestação" in texto
        assert "15:00" in texto
        assert "Construtora Alfa" in texto and "15/100" in texto

    async def test_marca_prazo_estimado_com_aproximacao(self):
        item = ItemAgenda(prazos=[_PrazoFake(7, HOJE + timedelta(days=3), estimado=True)])
        texto = montar_mensagem("Ana", item, HOJE, {7: "Cliente X"})
        assert "≈" in texto

    async def test_secoes_vazias_nao_aparecem(self):
        item = ItemAgenda(prazos=[_PrazoFake(7, HOJE)])
        texto = montar_mensagem("Ana", item, HOJE, {7: "Cliente X"})
        assert "REUNIÕES" not in texto
        assert "EM RISCO" not in texto


class TestMontagemDoEscritorio:
    async def test_cada_advogado_recebe_apenas_sua_carteira(
        self, db_session, escritorio_factory, usuario_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        ana = await _advogado(db_session, usuario_factory, escritorio.id)
        bruno = await _advogado(db_session, usuario_factory, escritorio.id, "5511977776666")

        await _cliente_de(
            db_session, cliente_factory, escritorio.id, ana.id, crm_nivel="em_risco", crm_score=20
        )
        await _cliente_de(
            db_session, cliente_factory, escritorio.id, bruno.id, crm_nivel="critico", crm_score=5
        )

        agendas = await montar_agenda_do_escritorio(db_session, escritorio.id, hoje=HOJE)

        assert set(agendas) == {ana.id, bruno.id}
        assert len(agendas[ana.id].clientes_em_risco) == 1
        assert len(agendas[bruno.id].clientes_em_risco) == 1
        assert agendas[ana.id].clientes_em_risco[0].id != agendas[bruno.id].clientes_em_risco[0].id

    async def test_advogado_sem_nada_fica_de_fora(
        self, db_session, escritorio_factory, usuario_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        ana = await _advogado(db_session, usuario_factory, escritorio.id)
        # cliente saudável, sem prazo e sem reunião
        await _cliente_de(
            db_session,
            cliente_factory,
            escritorio.id,
            ana.id,
            crm_nivel="satisfeito",
            crm_score=70,
        )

        agendas = await montar_agenda_do_escritorio(db_session, escritorio.id, hoje=HOJE)
        assert agendas == {}

    async def test_reuniao_de_hoje_entra_a_de_amanha_nao(
        self, db_session, escritorio_factory, usuario_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        ana = await _advogado(db_session, usuario_factory, escritorio.id)
        cliente = await _cliente_de(db_session, cliente_factory, escritorio.id, ana.id)

        db_session.add(
            Agendamento(
                cliente_id=cliente.id,
                escritorio_id=escritorio.id,
                status="confirmado",
                data_hora_inicio=datetime(2026, 8, 14, 10, 0, tzinfo=UTC),
            )
        )
        db_session.add(
            Agendamento(
                cliente_id=cliente.id,
                escritorio_id=escritorio.id,
                status="confirmado",
                data_hora_inicio=datetime(2026, 8, 15, 10, 0, tzinfo=UTC),
            )
        )
        await db_session.commit()

        agendas = await montar_agenda_do_escritorio(db_session, escritorio.id, hoje=HOJE)
        assert len(agendas[ana.id].reunioes) == 1

    async def test_reuniao_nao_confirmada_e_ignorada(
        self, db_session, escritorio_factory, usuario_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        ana = await _advogado(db_session, usuario_factory, escritorio.id)
        cliente = await _cliente_de(db_session, cliente_factory, escritorio.id, ana.id)
        db_session.add(
            Agendamento(
                cliente_id=cliente.id,
                escritorio_id=escritorio.id,
                status="proposto",
                data_hora_inicio=datetime(2026, 8, 14, 10, 0, tzinfo=UTC),
            )
        )
        await db_session.commit()

        agendas = await montar_agenda_do_escritorio(db_session, escritorio.id, hoje=HOJE)
        assert agendas == {}

    async def test_cliente_sem_responsavel_nao_gera_agenda(
        self, db_session, escritorio_factory, usuario_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        await _advogado(db_session, usuario_factory, escritorio.id)
        # cliente em risco, mas sem dono
        cliente = await cliente_factory(escritorio_id=escritorio.id)
        await db_session.execute(
            update(Cliente).where(Cliente.id == cliente.id).values(crm_nivel="critico", crm_score=4)
        )
        await db_session.commit()

        agendas = await montar_agenda_do_escritorio(db_session, escritorio.id, hoje=HOJE)
        assert agendas == {}

    async def test_carteira_de_outro_escritorio_nao_vaza(
        self, db_session, escritorio_factory, usuario_factory, cliente_factory
    ):
        esc_a = await escritorio_factory()
        esc_b = await escritorio_factory()
        ana = await _advogado(db_session, usuario_factory, esc_a.id)
        bruno = await _advogado(db_session, usuario_factory, esc_b.id, "5511966665555")
        await _cliente_de(
            db_session, cliente_factory, esc_b.id, bruno.id, crm_nivel="critico", crm_score=3
        )

        agendas = await montar_agenda_do_escritorio(db_session, esc_a.id, hoje=HOJE)
        assert ana.id not in agendas


class TestJanelaDePrazos:
    async def test_janela_e_de_uma_semana(self):
        assert DIAS_DE_PRAZO == 7
