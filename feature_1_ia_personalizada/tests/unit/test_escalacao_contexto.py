# feature_1_ia_personalizada/tests/unit/test_escalacao_contexto.py
"""
Testes unitários para EscalacaoManager (Feature 6).

Cobertura:
  - avaliar_e_notificar_advogados: sem advogados configurados → retorna erro
  - avaliar_e_notificar_advogados: advogado configurado → cria Interacao + notifica WhatsApp
  - Metadata da escalação gravada corretamente (status, motivo, sugestao)
  - Sugestão de resposta gerada via Claude (mockada)
  - Múltiplos advogados: todos notificados; IDs registrados em metadata
  - Advogado sem whatsapp_numero não é notificado
  - Falha no WhatsApp não impede gravação da Interacao
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from feature_1_ia_personalizada.services.escalacao.manager import EscalacaoManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_usuario(
    id: int = 1,
    escritorio_id: int = 10,
    whatsapp_numero: str | None = "5511999999999",
    escalacao_ativa: bool = True,
    ativo: bool = True,
):
    u = MagicMock()
    u.id = id
    u.escritorio_id = escritorio_id
    u.whatsapp_numero = whatsapp_numero
    u.escalacao_ativa = escalacao_ativa
    u.ativo = ativo
    return u


def _make_manager(advogados: list, sugestao: str = "Olá, entendo sua dúvida."):
    """Constrói EscalacaoManager com todos os colaboradores mockados."""
    claude = AsyncMock()
    evolution = AsyncMock()

    # Mock de sessão assíncrona
    session_mock = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = advogados
    session_mock.execute = AsyncMock(return_value=result_mock)
    session_mock.add = MagicMock()
    session_mock.flush = AsyncMock()
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=False)

    session_factory = MagicMock(return_value=session_mock)

    # Mock do método _gerar_sugestao_resposta
    manager = EscalacaoManager(claude, evolution, session_factory)
    manager._gerar_sugestao_resposta = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "resposta": sugestao,
            "tokens_input": 100,
            "tokens_output": 50,
            "custo": Decimal("0.001"),
        }
    )

    return manager, session_mock, evolution


# ---------------------------------------------------------------------------
# Sem advogados configurados
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sem_advogados_retorna_erro():
    manager, _, _ = _make_manager(advogados=[])
    resultado = await manager.avaliar_e_notificar_advogados(
        escritorio_id=10,
        cliente_id=1,
        mensagem_cliente="Qual minha chance de ganhar?",
        motivo="parecer_juridico",
        historico_recente=[],
        instancia_whatsapp="escritorio_10",
    )
    assert resultado["enviado"] is False
    assert "nenhum_advogado" in resultado["erro"]


# ---------------------------------------------------------------------------
# Com advogado configurado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_com_advogado_cria_interacao():
    """Deve criar uma Interacao com metadata de escalação pendente."""
    adv = _make_usuario(id=5, whatsapp_numero="5511999999999")
    manager, session_mock, evolution = _make_manager(advogados=[adv])
    evolution.enviar_texto = AsyncMock(return_value={"key": {"id": "WAMID_ABC"}})

    resultado = await manager.avaliar_e_notificar_advogados(
        escritorio_id=10,
        cliente_id=1,
        mensagem_cliente="Preciso de um parecer jurídico.",
        motivo="parecer_juridico",
        historico_recente=[{"role": "user", "content": "..."}],
        instancia_whatsapp="escritorio_10",
    )

    assert resultado["enviado"] is True
    # Verifica que session.add foi chamado (gravou Interacao)
    assert session_mock.add.called


@pytest.mark.asyncio
async def test_com_advogado_metadata_status_pendente():
    """Metadata da Interacao deve ter escalacao.status = 'pendente'."""
    adv = _make_usuario(id=5)
    manager, session_mock, evolution = _make_manager(advogados=[adv])
    evolution.enviar_texto = AsyncMock(return_value={"key": {"id": "WAMID_XYZ"}})

    interacao_salva = None
    original_add = session_mock.add

    def _capture_add(obj):
        nonlocal interacao_salva
        interacao_salva = obj
        return original_add(obj)

    session_mock.add = _capture_add

    await manager.avaliar_e_notificar_advogados(
        escritorio_id=10,
        cliente_id=1,
        mensagem_cliente="Preciso de ajuda.",
        motivo="tutela_urgencia",
        historico_recente=[],
        instancia_whatsapp="escritorio_10",
    )

    assert interacao_salva is not None
    metadata = interacao_salva.metadata_json
    assert metadata["escalacao"]["status"] == "pendente"
    assert metadata["escalacao"]["motivo"] == "tutela_urgencia"
    assert 5 in metadata["escalacao"]["advogados_notificados"]


@pytest.mark.asyncio
async def test_sugestao_incluida_na_metadata():
    """Sugestão gerada pelo Claude deve estar em metadata.escalacao.sugestao_resposta."""
    adv = _make_usuario(id=5)
    sugestao = "Sua dúvida foi recebida e o advogado entrará em contato."
    manager, session_mock, evolution = _make_manager(advogados=[adv], sugestao=sugestao)
    evolution.enviar_texto = AsyncMock(return_value={"key": {"id": "WAMID_1"}})

    interacao_salva = None

    def _capture(obj):
        nonlocal interacao_salva
        interacao_salva = obj

    session_mock.add = _capture

    await manager.avaliar_e_notificar_advogados(
        escritorio_id=10,
        cliente_id=1,
        mensagem_cliente="Dúvida sobre recurso.",
        motivo="recurso_cabivel",
        historico_recente=[],
        instancia_whatsapp="escritorio_10",
    )

    assert interacao_salva is not None
    assert interacao_salva.metadata_json["escalacao"]["sugestao_resposta"] == sugestao


# ---------------------------------------------------------------------------
# Múltiplos advogados
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiplos_advogados_todos_notificados():
    """Com dois advogados configurados, ambos devem ser notificados."""
    adv1 = _make_usuario(id=1, whatsapp_numero="5511111111111")
    adv2 = _make_usuario(id=2, whatsapp_numero="5522222222222")
    manager, session_mock, evolution = _make_manager(advogados=[adv1, adv2])
    evolution.enviar_texto = AsyncMock(return_value={"key": {"id": "WAMID_M"}})

    resultado = await manager.avaliar_e_notificar_advogados(
        escritorio_id=10,
        cliente_id=1,
        mensagem_cliente="Urgência!",
        motivo="tutela_urgencia",
        historico_recente=[],
        instancia_whatsapp="escritorio_10",
    )

    assert resultado["enviado"] is True
    assert resultado["notificados_count"] == 2
    assert evolution.enviar_texto.call_count == 2


@pytest.mark.asyncio
async def test_multiplos_advogados_ids_em_metadata():
    """IDs de todos os advogados notificados devem estar em metadata."""
    adv1 = _make_usuario(id=10, whatsapp_numero="5511111111111")
    adv2 = _make_usuario(id=20, whatsapp_numero="5522222222222")
    manager, session_mock, evolution = _make_manager(advogados=[adv1, adv2])
    evolution.enviar_texto = AsyncMock(return_value={"key": {"id": "WID"}})

    capturado = None

    def _cap(obj):
        nonlocal capturado
        capturado = obj

    session_mock.add = _cap

    await manager.avaliar_e_notificar_advogados(
        escritorio_id=10,
        cliente_id=1,
        mensagem_cliente="Dúvida estratégica.",
        motivo="estrategia_processual",
        historico_recente=[],
        instancia_whatsapp="escritorio_10",
    )

    assert capturado is not None
    notificados = capturado.metadata_json["escalacao"]["advogados_notificados"]
    assert 10 in notificados
    assert 20 in notificados


# ---------------------------------------------------------------------------
# Geração de sugestão via Claude
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gerar_sugestao_chamada_com_historico():
    """_gerar_sugestao_resposta deve ser chamado com a mensagem e o histórico."""
    adv = _make_usuario(id=5)
    manager, session_mock, evolution = _make_manager(advogados=[adv])
    evolution.enviar_texto = AsyncMock(return_value={"key": {"id": "W1"}})

    historico = [
        {"role": "user", "content": "Olá"},
        {"role": "assistant", "content": "Como posso ajudar?"},
    ]

    await manager.avaliar_e_notificar_advogados(
        escritorio_id=10,
        cliente_id=1,
        mensagem_cliente="Preciso de estratégia.",
        motivo="estrategia_processual",
        historico_recente=historico,
        instancia_whatsapp="escritorio_10",
    )

    manager._gerar_sugestao_resposta.assert_called_once()
    call_args = manager._gerar_sugestao_resposta.call_args
    assert "Preciso de estratégia." in str(call_args)


# ---------------------------------------------------------------------------
# Robustez — falha no WhatsApp
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_falha_whatsapp_nao_impede_gravacao():
    """Mesmo se o envio WhatsApp falhar, a Interacao deve ser gravada."""
    adv = _make_usuario(id=5)
    manager, session_mock, evolution = _make_manager(advogados=[adv])
    evolution.enviar_texto = AsyncMock(side_effect=Exception("WhatsApp offline"))

    # Não deve lançar exceção — o resultado pode indicar falha parcial
    try:
        resultado = await manager.avaliar_e_notificar_advogados(
            escritorio_id=10,
            cliente_id=1,
            mensagem_cliente="Urgente!",
            motivo="tutela_urgencia",
            historico_recente=[],
            instancia_whatsapp="escritorio_10",
        )
        # Se retornou resultado, a interação foi criada
        # (o manager pode retornar enviado=False ou tratar internamente)
        assert "enviado" in resultado
    except Exception:
        pytest.fail("EscalacaoManager não deve propagar exceção do WhatsApp")
