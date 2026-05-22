"""
PIJ-195 — Testes unitários de WhatsAppService._obter_contexto_processo.

O método `_obter_contexto_processo` em whatsapp.py resolve
`processo_id → (escritorio_id, cliente_id)` via query assíncrona no banco.
Testa:
- Retorna tupla (escritorio_id, cliente_id) quando processo existe
- Retorna None quando processo não existe (e loga warning)
- Chamada usada por `enviar_notificacao_andamento` e `enviar_sem_movimentacao`
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.messaging.whatsapp import WhatsAppService

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def service() -> WhatsAppService:
    """WhatsAppService com dependências completamente mockadas."""
    mock_client = AsyncMock()
    mock_repo = AsyncMock()
    return WhatsAppService(evolution_client=mock_client, repositorio=mock_repo)


def _mock_session_ctx(row=None):
    """Cria contexto de sessão async com resultado de one_or_none configurável."""
    execute_result = MagicMock()
    execute_result.one_or_none.return_value = row

    session = AsyncMock()
    session.execute.return_value = execute_result

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# --------------------------------------------------------------------------- #
# 1. _obter_contexto_processo — processo existe
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_obter_contexto_processo_retorna_tupla(service: WhatsAppService):
    """Quando processo existe, retorna (escritorio_id, cliente_id)."""
    row = MagicMock()
    row.escritorio_id = 5
    row.cliente_id = 42

    ctx = _mock_session_ctx(row=row)

    with patch(
        "feature_1_ia_personalizada.services.messaging.whatsapp.async_session_factory",
        return_value=ctx,
    ):
        resultado = await service._obter_contexto_processo(processo_id=1)

    assert resultado == (5, 42)


@pytest.mark.asyncio
async def test_obter_contexto_processo_ids_corretos(service: WhatsAppService):
    """Confirma que os IDs são atribuídos na ordem certa (escritorio_id, cliente_id)."""
    row = MagicMock()
    row.escritorio_id = 99
    row.cliente_id = 7

    ctx = _mock_session_ctx(row=row)

    with patch(
        "feature_1_ia_personalizada.services.messaging.whatsapp.async_session_factory",
        return_value=ctx,
    ):
        resultado = await service._obter_contexto_processo(10)
        assert resultado is not None
        escritorio_id, cliente_id = resultado

    assert escritorio_id == 99
    assert cliente_id == 7


# --------------------------------------------------------------------------- #
# 2. _obter_contexto_processo — processo NÃO existe
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_obter_contexto_processo_retorna_none_quando_nao_existe(
    service: WhatsAppService, caplog
):
    """Quando o processo não existe no banco, deve retornar None."""
    ctx = _mock_session_ctx(row=None)

    with patch(
        "feature_1_ia_personalizada.services.messaging.whatsapp.async_session_factory",
        return_value=ctx,
    ):
        resultado = await service._obter_contexto_processo(processo_id=999)

    assert resultado is None


# --------------------------------------------------------------------------- #
# 3. enviar_notificacao_andamento usa _obter_contexto_processo
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_enviar_notificacao_andamento_retorna_erro_processo_nao_encontrado(
    service: WhatsAppService,
):
    """Se processo não existe, enviar_notificacao_andamento retorna erro sem lançar execão."""
    ctx = _mock_session_ctx(row=None)

    with patch(
        "feature_1_ia_personalizada.services.messaging.whatsapp.async_session_factory",
        return_value=ctx,
    ):
        resultado = await service.enviar_notificacao_andamento(
            processo_id=404, andamento="Audiência adiada."
        )

    assert resultado["ok"] is False
    assert resultado["erro"] == "processo_nao_encontrado"


@pytest.mark.asyncio
async def test_enviar_notificacao_andamento_delega_para_enviar_mensagem(
    service: WhatsAppService,
):
    """Com processo válido, enviar_notificacao_andamento deve chamar enviar_mensagem."""
    row = MagicMock()
    row.escritorio_id = 1
    row.cliente_id = 2

    ctx = _mock_session_ctx(row=row)

    with (
        patch(
            "feature_1_ia_personalizada.services.messaging.whatsapp.async_session_factory",
            return_value=ctx,
        ),
        patch.object(
            service,
            "enviar_mensagem",
            new_callable=AsyncMock,
            return_value={"ok": True},
        ) as mock_enviar,
    ):
        resultado = await service.enviar_notificacao_andamento(
            processo_id=1, andamento="Despacho publicado."
        )

    mock_enviar.assert_called_once()
    args, kwargs = mock_enviar.call_args
    # primeiro arg = escritorio_id, segundo = cliente_id
    assert args[0] == 1  # escritorio_id
    assert args[1] == 2  # cliente_id
    assert "Despacho publicado." in args[2]  # texto contém o andamento
    assert kwargs.get("processo_id") == 1
    assert resultado == {"ok": True}


# --------------------------------------------------------------------------- #
# 4. enviar_sem_movimentacao usa _obter_contexto_processo
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_enviar_sem_movimentacao_retorna_erro_processo_nao_encontrado(
    service: WhatsAppService,
):
    ctx = _mock_session_ctx(row=None)

    with patch(
        "feature_1_ia_personalizada.services.messaging.whatsapp.async_session_factory",
        return_value=ctx,
    ):
        resultado = await service.enviar_sem_movimentacao(processo_id=404)

    assert resultado["ok"] is False
    assert resultado["erro"] == "processo_nao_encontrado"


@pytest.mark.asyncio
async def test_enviar_sem_movimentacao_texto_correto(service: WhatsAppService):
    """Texto enviado deve mencionar ausência de movimentação."""
    row = MagicMock()
    row.escritorio_id = 3
    row.cliente_id = 9
    # Forçar None para que carregar_templates use o template padrão (string real, não MagicMock)
    row.template_boas_vindas = None
    row.template_atualizacao = None
    row.template_sem_novidade = None

    ctx = _mock_session_ctx(row=row)

    with (
        patch(
            "feature_1_ia_personalizada.services.messaging.whatsapp.async_session_factory",
            return_value=ctx,
        ),
        patch.object(
            service,
            "enviar_mensagem",
            new_callable=AsyncMock,
            return_value={"ok": True},
        ) as mock_enviar,
    ):
        await service.enviar_sem_movimentacao(processo_id=5)

    _, kwargs = mock_enviar.call_args
    texto = mock_enviar.call_args[0][2]
    assert "sem movimentação" in texto.lower() or "30 dias" in texto
