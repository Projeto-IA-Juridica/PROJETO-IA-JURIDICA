"""
PIJ-172 — Testes unitários do EvolutionClient.

Cobre:
- Envio de texto (payload correto, mock HTTP)
- Retry com backoff em caso de timeout
- Tratamento de erro 4xx / 5xx
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from feature_1_ia_personalizada.services.messaging.evolution_client import (
    EvolutionClient,
    EvolutionOfflineError,
    EvolutionRequestError,
    EvolutionTimeoutError,
)

# ──────────────────────────────────────────────
# Fixture
# ──────────────────────────────────────────────


@pytest.fixture
def client() -> EvolutionClient:
    """Cliente com timeout curto para testes rodarem rápido."""
    return EvolutionClient(
        base_url="http://localhost:8080",
        api_key="TEST-KEY-123",
        timeout_seconds=5.0,
    )


def _mock_response(status_code: int, json_data: dict | None = None) -> MagicMock:
    """Gera um httpx.Response mockado."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.content = b'{"key": "value"}' if json_data is not None else b'{"key": "value"}'
    resp.json.return_value = json_data or {"key": "value"}
    resp.text = str(json_data or {"key": "value"})
    return resp


# ──────────────────────────────────────────────────────────────────────────────
# 1. Envio de texto — payload correto (PIJ-172 item 1)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enviar_texto_payload_correto(client: EvolutionClient):
    """Garante que enviar_texto manda POST com number e text corretos."""
    resposta_esperada = {"key": "value", "messageId": "abc123"}
    mock_resp = _mock_response(200, resposta_esperada)

    with patch.object(
        client._client, "request", new_callable=AsyncMock
    ) as mock_request:
        mock_request.return_value = mock_resp

        resultado = await client.enviar_texto(
            instance="teste-juridica",
            numero="5511999999999",
            texto="Olá, seu processo foi atualizado!",
        )

    # verifica que a chamada HTTP foi feita corretamente
    mock_request.assert_called_once_with(
        "POST",
        "/message/sendText/teste-juridica",
        json={
            "number": "5511999999999",
            "text": "Olá, seu processo foi atualizado!",
        },
        params=None,
    )
    assert resultado == resposta_esperada


@pytest.mark.asyncio
async def test_enviar_texto_retorna_dict_vazio_sem_corpo(client: EvolutionClient):
    """Quando a resposta 2xx não tem corpo, retorna dict vazio sem erro."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.content = b""  # sem corpo
    resp.json.return_value = {}
    resp.text = ""

    with patch.object(
        client._client, "request", new_callable=AsyncMock
    ) as mock_request:
        mock_request.return_value = resp
        resultado = await client.enviar_texto("inst", "5511999999999", "teste")

    assert resultado == {}


@pytest.mark.asyncio
async def test_enviar_texto_headers_contem_apikey(client: EvolutionClient):
    """O client deve ter o header apikey configurado."""
    assert client._headers["apikey"] == "TEST-KEY-123"
    assert client._headers["Content-Type"] == "application/json"


# ──────────────────────────────────────────────────────────────────────────────
# 2. Retry com backoff em timeout (PIJ-172 item 2)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_em_timeout_3_tentativas(client: EvolutionClient):
    """
    Quando a Evolution lança ReadTimeout em todas as tentativas,
    deve tentar 3 vezes e lançar EvolutionTimeoutError.
    """
    with (
        patch.object(client._client, "request", new_callable=AsyncMock) as mock_req,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):

        mock_req.side_effect = httpx.ReadTimeout("timeout")

        with pytest.raises(EvolutionTimeoutError):
            await client.enviar_texto("inst", "5511999999999", "teste")

    # deve ter tentado exatamente 3 vezes (max_tentativas default)
    assert mock_req.call_count == 3
    # backoff é chamado ENTRE tentativas, não após a última → 3-1 = 2 sleeps
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_retry_backoff_valores_crescentes(client: EvolutionClient):
    """Backoff deve crescer exponencialmente: 0.7, 1.4, 2.8 (limitado a 4.0)."""
    backoffs = [client._calcular_backoff(t) for t in [1, 2, 3]]
    assert backoffs[0] == pytest.approx(0.7)
    assert backoffs[1] == pytest.approx(1.4)
    assert backoffs[2] == pytest.approx(2.8)


@pytest.mark.asyncio
async def test_retry_backoff_nao_ultrapassa_maximo(client: EvolutionClient):
    """Backoff nunca deve ultrapassar backoff_max_seconds (4.0)."""
    # tentativa 10 geraria 0.7 * 512 = 358.4, mas deve ser limitado a 4.0
    assert client._calcular_backoff(10) == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_retry_sucesso_na_segunda_tentativa(client: EvolutionClient):
    """Falha na 1ª tentativa (timeout) mas sucesso na 2ª — não deve lançar exceção."""
    sucesso = _mock_response(200, {"messageId": "ok"})

    with (
        patch.object(client._client, "request", new_callable=AsyncMock) as mock_req,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):

        mock_req.side_effect = [httpx.ReadTimeout("t"), sucesso]

        resultado = await client.enviar_texto("inst", "5511999999999", "teste")

    assert resultado == {"messageId": "ok"}
    assert mock_req.call_count == 2


# ──────────────────────────────────────────────────────────────────────────────
# 3. Tratamento de erros 4xx / 5xx (PIJ-172 item 3)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_erro_400_levanta_evolution_request_error(client: EvolutionClient):
    """HTTP 400 deve lançar EvolutionRequestError na 1ª tentativa (sem retry)."""
    mock_resp = _mock_response(400, {"error": "Bad Request"})

    with (
        patch.object(client._client, "request", new_callable=AsyncMock) as mock_req,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):

        mock_req.return_value = mock_resp

        with pytest.raises(EvolutionRequestError):
            await client.enviar_texto("inst", "5511999999999", "teste")

    # 400 não é retryable — deve ter chamado apenas 1x (o loop continua mas o
    # EvolutionRequestError não é capturado, então sobe imediatamente)
    assert mock_req.call_count == 1


@pytest.mark.asyncio
async def test_erro_500_levanta_evolution_request_error(client: EvolutionClient):
    """HTTP 500 deve lançar EvolutionRequestError."""
    mock_resp = _mock_response(500, {"error": "Internal Server Error"})

    with (
        patch.object(client._client, "request", new_callable=AsyncMock) as mock_req,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):

        mock_req.return_value = mock_resp

        with pytest.raises(EvolutionRequestError) as exc_info:
            await client.enviar_texto("inst", "5511999999999", "teste")

    assert "500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_erro_503_levanta_evolution_offline_error(client: EvolutionClient):
    """HTTP 503 indica instância offline → deve lançar EvolutionOfflineError após retries."""
    mock_resp = _mock_response(503, {"error": "Service Unavailable"})

    with (
        patch.object(client._client, "request", new_callable=AsyncMock) as mock_req,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):

        mock_req.return_value = mock_resp

        with pytest.raises(EvolutionOfflineError):
            await client.enviar_texto("inst", "5511999999999", "teste")

    # 503 é tratado como EvolutionOfflineError e sofre retry
    assert mock_req.call_count == 3


@pytest.mark.asyncio
async def test_erro_conexao_levanta_evolution_request_error(client: EvolutionClient):
    """Falha de conexão (ConnectError) após 3 tentativas → EvolutionRequestError."""
    with (
        patch.object(client._client, "request", new_callable=AsyncMock) as mock_req,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):

        mock_req.side_effect = httpx.ConnectError("connection refused")

        with pytest.raises(EvolutionRequestError, match="Falha de conexão"):
            await client.enviar_texto("inst", "5511999999999", "teste")

    assert mock_req.call_count == 3
