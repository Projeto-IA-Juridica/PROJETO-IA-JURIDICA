"""
feature_1_ia_personalizada/tests/unit/test_alerta_risco.py
===========================================================
Alerta de cliente em risco enviado ao advogado responsável.

O que estes testes protegem, além do caminho feliz:

- **Ninguém é alertado sem dono.** Sem responsável resolvido, não se manda para
  a lista inteira do escritório — isso viraria spam e diluiria a ação.
- **Permanecer em risco é silencioso; piorar não é.** A análise roda a cada
  conversa nova; sem a trava por cliente+nível o advogado receberia o mesmo
  aviso várias vezes por dia. Uma piora de nível fura a trava de propósito.
- **A precedência do responsável.** Atribuição direta no cliente ganha do
  responsável herdado do processo.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import update

from feature_1_ia_personalizada.services.relacionamento.alerta_risco import (
    alertar_se_em_risco,
    montar_mensagem,
)
from feature_1_ia_personalizada.services.relacionamento.responsavel import (
    resolver_responsavel,
)
from shared.models.cliente import Cliente
from shared.models.processo import Processo

pytestmark = pytest.mark.asyncio


async def _cliente_classificado(
    db, escritorio_id, cliente_factory, nivel="em_risco", score=20, **campos
):
    cliente = await cliente_factory(escritorio_id=escritorio_id)
    await db.execute(
        update(Cliente)
        .where(Cliente.id == cliente.id)
        .values(
            crm_nivel=nivel,
            crm_score=score,
            crm_resumo="Reclamou da falta de retorno duas vezes.",
            crm_acao_sugerida="Ligar hoje para retomar o contato",
            **campos,
        )
    )
    await db.commit()
    await db.refresh(cliente)
    return cliente


async def _preparar_para_envio(db, escritorio, advogado):
    """Deixa o cenário pronto para um envio real: instância + WhatsApp do advogado."""
    from shared.models.escritorio import Escritorio
    from shared.models.usuario import Usuario

    await db.execute(
        update(Escritorio)
        .where(Escritorio.id == escritorio.id)
        .values(webhook_whatsapp_instance="instancia-teste")
    )
    await db.execute(
        update(Usuario).where(Usuario.id == advogado.id).values(whatsapp_numero="5511988887777")
    )
    await db.commit()


def _patch_envio(retorno=True):
    return patch(
        "feature_1_ia_personalizada.services.relacionamento.alerta_risco.notificar_advogado",
        new=AsyncMock(return_value=retorno),
    )


class TestMontarMensagem:
    async def test_inclui_nome_score_resumo_e_acao(self):
        texto = montar_mensagem(
            "Construtora Alfa", "critico", 8, "Ameaçou trocar de escritório.", "Ligar agora"
        )
        assert "Construtora Alfa" in texto
        assert "8/100" in texto
        assert "CRÍTICO" in texto
        assert "Ameaçou trocar de escritório." in texto
        assert "Ligar agora" in texto

    async def test_funciona_sem_resumo_nem_acao(self):
        texto = montar_mensagem("Cliente X", "em_risco", 22, None, None)
        assert "Cliente X" in texto
        assert "EM RISCO" in texto


class TestQuandoAlerta:
    async def test_nivel_de_risco_notifica_o_responsavel(
        self, db_session, escritorio_factory, usuario_factory, cliente_factory, fake_redis
    ):
        escritorio = await escritorio_factory()
        advogado = await usuario_factory(escritorio_id=escritorio.id)
        await db_session.execute(
            update(type(advogado))
            .where(type(advogado).id == advogado.id)
            .values(whatsapp_numero="5511988887777")
        )
        cliente = await _cliente_classificado(
            db_session,
            escritorio.id,
            cliente_factory,
            advogado_responsavel_id=advogado.id,
        )

        with _patch_envio() as envio:
            alertou = await alertar_se_em_risco(
                db_session, cliente.id, escritorio.id, "em_risco", 20, redis=fake_redis
            )

        assert alertou is True
        destinatario = envio.await_args.args[0]
        assert destinatario.id == advogado.id

    @pytest.mark.parametrize("nivel", ["excelente", "satisfeito", "neutro"])
    async def test_nivel_saudavel_nao_notifica(
        self, db_session, escritorio_factory, usuario_factory, cliente_factory, fake_redis, nivel
    ):
        escritorio = await escritorio_factory()
        advogado = await usuario_factory(escritorio_id=escritorio.id)
        cliente = await _cliente_classificado(
            db_session,
            escritorio.id,
            cliente_factory,
            nivel=nivel,
            score=80,
            advogado_responsavel_id=advogado.id,
        )

        with _patch_envio() as envio:
            alertou = await alertar_se_em_risco(
                db_session, cliente.id, escritorio.id, nivel, 80, redis=fake_redis
            )

        assert alertou is False
        envio.assert_not_awaited()

    async def test_sem_responsavel_nao_dispara_para_ninguem(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        escritorio = await escritorio_factory()
        cliente = await _cliente_classificado(db_session, escritorio.id, cliente_factory)

        with _patch_envio() as envio:
            alertou = await alertar_se_em_risco(
                db_session, cliente.id, escritorio.id, "critico", 5, redis=fake_redis
            )

        assert alertou is False
        envio.assert_not_awaited()


class TestTravaAntiSpam:
    async def test_mesmo_nivel_nao_repete_o_aviso(
        self, db_session, escritorio_factory, usuario_factory, cliente_factory, fake_redis
    ):
        """A análise roda a cada conversa; o advogado só é avisado uma vez."""
        escritorio = await escritorio_factory()
        advogado = await usuario_factory(escritorio_id=escritorio.id)
        await _preparar_para_envio(db_session, escritorio, advogado)
        cliente = await _cliente_classificado(
            db_session,
            escritorio.id,
            cliente_factory,
            advogado_responsavel_id=advogado.id,
        )

        # Envio real (mockado no transporte) para a trava ser gravada de fato.
        with (
            patch("feature_1_ia_personalizada.services.relacionamento.notificador.settings") as cfg,
            patch(
                "feature_1_ia_personalizada.services.messaging.evolution_client.EvolutionClient"
            ) as MockEvo,
        ):
            cfg.EVOLUTION_API_URL = "http://evo"
            cfg.EVOLUTION_API_KEY = "k"
            MockEvo.return_value.enviar_texto = AsyncMock()
            MockEvo.return_value.close = AsyncMock()

            primeiro = await alertar_se_em_risco(
                db_session, cliente.id, escritorio.id, "em_risco", 20, redis=fake_redis
            )
            segundo = await alertar_se_em_risco(
                db_session, cliente.id, escritorio.id, "em_risco", 19, redis=fake_redis
            )

        assert primeiro is True
        assert segundo is False, "mesmo nível não pode alertar duas vezes"

    async def test_piora_de_nivel_fura_a_trava(
        self, db_session, escritorio_factory, usuario_factory, cliente_factory, fake_redis
    ):
        """em_risco → critico é informação nova: precisa alertar de novo."""
        escritorio = await escritorio_factory()
        advogado = await usuario_factory(escritorio_id=escritorio.id)
        await _preparar_para_envio(db_session, escritorio, advogado)
        cliente = await _cliente_classificado(
            db_session,
            escritorio.id,
            cliente_factory,
            advogado_responsavel_id=advogado.id,
        )

        with (
            patch("feature_1_ia_personalizada.services.relacionamento.notificador.settings") as cfg,
            patch(
                "feature_1_ia_personalizada.services.messaging.evolution_client.EvolutionClient"
            ) as MockEvo,
        ):
            cfg.EVOLUTION_API_URL = "http://evo"
            cfg.EVOLUTION_API_KEY = "k"
            MockEvo.return_value.enviar_texto = AsyncMock()
            MockEvo.return_value.close = AsyncMock()

            em_risco = await alertar_se_em_risco(
                db_session, cliente.id, escritorio.id, "em_risco", 20, redis=fake_redis
            )
            critico = await alertar_se_em_risco(
                db_session, cliente.id, escritorio.id, "critico", 6, redis=fake_redis
            )

        assert em_risco is True
        assert critico is True, "piora de nível precisa furar a trava"


class TestResolucaoDeResponsavel:
    async def test_atribuicao_direta_tem_precedencia_sobre_processo(
        self, db_session, escritorio_factory, usuario_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        dono = await usuario_factory(escritorio_id=escritorio.id)
        outro = await usuario_factory(escritorio_id=escritorio.id)
        for u in (dono, outro):
            await db_session.execute(
                update(type(u)).where(type(u).id == u.id).values(whatsapp_numero="5511900000000")
            )
        cliente = await cliente_factory(escritorio_id=escritorio.id)
        await db_session.execute(
            update(Cliente).where(Cliente.id == cliente.id).values(advogado_responsavel_id=dono.id)
        )
        db_session.add(
            Processo(
                cliente_id=cliente.id,
                escritorio_id=escritorio.id,
                numero_cnj="1111111-11.2026.8.26.0100",
                polo_cliente="autor",
                status="ativo",
                advogado_responsavel_id=outro.id,
            )
        )
        await db_session.commit()
        await db_session.refresh(cliente)

        responsavel = await resolver_responsavel(db_session, cliente)
        assert responsavel is not None
        assert responsavel.id == dono.id

    async def test_herda_responsavel_do_processo_quando_cliente_nao_tem(
        self, db_session, escritorio_factory, usuario_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        advogado = await usuario_factory(escritorio_id=escritorio.id)
        await db_session.execute(
            update(type(advogado))
            .where(type(advogado).id == advogado.id)
            .values(whatsapp_numero="5511911112222")
        )
        cliente = await cliente_factory(escritorio_id=escritorio.id)
        db_session.add(
            Processo(
                cliente_id=cliente.id,
                escritorio_id=escritorio.id,
                numero_cnj="2222222-22.2026.8.26.0100",
                polo_cliente="autor",
                status="ativo",
                advogado_responsavel_id=advogado.id,
            )
        )
        await db_session.commit()
        await db_session.refresh(cliente)

        responsavel = await resolver_responsavel(db_session, cliente)
        assert responsavel is not None
        assert responsavel.id == advogado.id

    async def test_advogado_sem_whatsapp_nao_e_notificavel(
        self, db_session, escritorio_factory, usuario_factory, cliente_factory
    ):
        escritorio = await escritorio_factory()
        advogado = await usuario_factory(escritorio_id=escritorio.id)  # sem whatsapp
        cliente = await cliente_factory(escritorio_id=escritorio.id)
        await db_session.execute(
            update(Cliente)
            .where(Cliente.id == cliente.id)
            .values(advogado_responsavel_id=advogado.id)
        )
        await db_session.commit()
        await db_session.refresh(cliente)

        assert await resolver_responsavel(db_session, cliente) is None
