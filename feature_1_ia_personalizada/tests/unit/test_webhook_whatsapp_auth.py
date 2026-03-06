"""
PIJ-197 — Validação da assinatura (API Key) do webhook WhatsApp.

A rota POST /webhook/whatsapp agora exige que o header 'apikey'
seja enviado com o valor idêntico ao settings.EVOLUTION_API_KEY.
Estes testes verificam se requisições inválidas recebem HTTP 401 e
se as requisições válidas passam para processamento.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from feature_1_ia_personalizada.api.routes.webhook_whatsapp import receive_message
from shared.config.settings import settings


@pytest.mark.asyncio
async def test_webhook_auth_missing_apikey():
    """Deve retornar 401 Unauthorized se o header 'apikey' não for enviado."""
    request = MagicMock()
    db = AsyncMock()

    with pytest.raises(HTTPException) as excinfo:
        # Passando apikey=None simulando a ausência do header
        await receive_message(request=request, apikey=None, db=db)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Unauthorized"


@pytest.mark.asyncio
async def test_webhook_auth_invalid_apikey():
    """Deve retornar 401 Unauthorized se a 'apikey' estiver incorreta."""
    request = MagicMock()
    db = AsyncMock()

    with pytest.raises(HTTPException) as excinfo:
        # Passando apikey errada
        await receive_message(request=request, apikey="senha_incorreta_123", db=db)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Unauthorized"


@pytest.mark.asyncio
async def test_webhook_auth_valid_apikey():
    """Não deve barrar a requisição se a 'apikey' for igual ao settings.EVOLUTION_API_KEY."""
    request = AsyncMock()
    # Mock do body para cair no if event != "messages.upsert" e retornar rápido
    request.json.return_value = {"event": "status.ignored"}
    db = AsyncMock()

    try:
        resultado = await receive_message(
            request=request, apikey=settings.EVOLUTION_API_KEY, db=db
        )
        assert resultado["status"] == "ignored"
    except HTTPException as e:
        pytest.fail(f"Não deveria levantar HTTPException para apikey válida: {e}")
