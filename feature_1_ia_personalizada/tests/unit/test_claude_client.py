# feature_1_ia_personalizada/tests/unit/test_claude_client.py
"""
Testes do ClaudeClient: retry, backoff, extração de blocos, custo e classificação.
asyncio.sleep é patchado globalmente neste módulo para testes sem delay real.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx
import pytest

from feature_1_ia_personalizada.services.ai.claude_client import (
    _MAX_TENTATIVAS,
    ClaudeClient,
    _backoff,
    _calcular_custo,
    _extrair_texto,
)

# ---------------------------------------------------------------------------
# Helpers para criar objetos mock do SDK Anthropic
# ---------------------------------------------------------------------------


def _bloco_texto(texto: str) -> MagicMock:
    b = MagicMock()
    b.type = "text"
    b.text = texto
    return b


def _bloco_tool_use() -> MagicMock:
    b = MagicMock()
    b.type = "tool_use"
    return b


def _mock_resposta(
    texto: str = "resposta ok", input_tokens: int = 100, output_tokens: int = 50
) -> MagicMock:
    r = MagicMock()
    r.content = [_bloco_texto(texto)]
    r.usage = MagicMock()
    r.usage.input_tokens = input_tokens
    r.usage.output_tokens = output_tokens
    return r


def _rate_limit_error() -> anthropic.RateLimitError:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 429
    resp.headers = httpx.Headers({})
    return anthropic.RateLimitError(message="rate limited", response=resp, body=None)


def _timeout_error() -> anthropic.APITimeoutError:
    req = MagicMock(spec=httpx.Request)
    return anthropic.APITimeoutError(request=req)


def _auth_error() -> anthropic.AuthenticationError:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 401
    resp.headers = httpx.Headers({})
    return anthropic.AuthenticationError(message="auth error", response=resp, body=None)


def _server_error() -> anthropic.InternalServerError:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 500
    resp.headers = httpx.Headers({})
    return anthropic.InternalServerError(
        message="server error", response=resp, body=None
    )


# ---------------------------------------------------------------------------
# Fixture: cliente com _client mockado + sleep patchado
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> ClaudeClient:
    with patch("anthropic.AsyncAnthropic"):
        c = ClaudeClient("sk-ant-fake")
    c._client = MagicMock()
    c._client.messages = MagicMock()
    return c


@pytest.fixture(autouse=True)
async def no_sleep():
    """Elimina delays reais do backoff em todos os testes deste módulo."""
    with patch("asyncio.sleep", new_callable=AsyncMock):
        yield


# ---------------------------------------------------------------------------
# Testes de _extrair_texto (helper puro)
# ---------------------------------------------------------------------------


class TestExtrairTexto:
    def test_retorna_texto_do_primeiro_bloco_text(self):
        resp = MagicMock()
        resp.content = [_bloco_texto("olá mundo")]
        assert _extrair_texto(resp) == "olá mundo"

    def test_ignora_bloco_tool_use_e_pega_text(self):
        """Deve pular blocos não-text e retornar o primeiro text."""
        resp = MagicMock()
        resp.content = [_bloco_tool_use(), _bloco_texto("texto real")]
        assert _extrair_texto(resp) == "texto real"

    def test_levanta_runtime_error_sem_bloco_text(self):
        resp = MagicMock()
        resp.content = [_bloco_tool_use()]
        with pytest.raises(RuntimeError, match="bloco de texto"):
            _extrair_texto(resp)

    def test_levanta_runtime_error_content_vazio(self):
        resp = MagicMock()
        resp.content = []
        with pytest.raises(RuntimeError, match="bloco de texto"):
            _extrair_texto(resp)

    def test_mensagem_de_erro_lista_tipos_recebidos(self):
        """A mensagem de erro deve informar os tipos recebidos para debugging."""
        resp = MagicMock()
        resp.content = [_bloco_tool_use()]
        with pytest.raises(RuntimeError) as exc:
            _extrair_texto(resp)
        assert "tool_use" in str(exc.value)


# ---------------------------------------------------------------------------
# Testes de _calcular_custo (helper puro)
# ---------------------------------------------------------------------------


class TestCalcularCusto:
    def test_custo_zero_tokens(self):
        assert _calcular_custo(0, 0) == Decimal("0")

    def test_custo_um_milhao_tokens_input(self):
        custo = _calcular_custo(1_000_000, 0)
        assert custo == Decimal("3.00")

    def test_custo_um_milhao_tokens_output(self):
        custo = _calcular_custo(0, 1_000_000)
        assert custo == Decimal("15.00")

    def test_custo_combinado(self):
        # 500k input (1.50) + 200k output (3.00) = 4.50
        custo = _calcular_custo(500_000, 200_000)
        assert custo == Decimal("4.50")

    def test_retorna_decimal_nao_float(self):
        custo = _calcular_custo(100, 50)
        assert isinstance(custo, Decimal)


# ---------------------------------------------------------------------------
# Testes de _backoff (helper puro)
# ---------------------------------------------------------------------------


class TestBackoff:
    def test_jitter_presente(self):
        """Duas chamadas com mesmo input devem raramente retornar valores iguais."""
        valores = {_backoff(1) for _ in range(20)}
        assert len(valores) > 1, "Backoff sem jitter — thundering herd risk"

    def test_cresce_com_tentativa(self):
        """Base exponencial: tentativa 2 deve ser maior que tentativa 1 em média."""
        media_t1 = sum(_backoff(1) for _ in range(50)) / 50
        media_t2 = sum(_backoff(2) for _ in range(50)) / 50
        assert media_t2 > media_t1

    def test_jitter_dentro_do_range_esperado(self):
        """backoff(1) = 2^1 + rand(0,1) → entre 2.0 e 3.0."""
        for _ in range(50):
            v = _backoff(1)
            assert 2.0 <= v < 3.0


# ---------------------------------------------------------------------------
# Testes de enviar_mensagem (integração com retry)
# ---------------------------------------------------------------------------


class TestEnviarMensagem:
    async def test_sucesso_retorna_estrutura_correta(self, client: ClaudeClient):
        client._client.messages.create = AsyncMock(  # type: ignore[method-assign]
            return_value=_mock_resposta("oi", 100, 50)
        )
        resultado = await client.enviar_mensagem("system", [], "mensagem")
        assert resultado["resposta"] == "oi"
        assert resultado["tokens_input"] == 100
        assert resultado["tokens_output"] == 50
        assert isinstance(resultado["custo"], Decimal)

    async def test_mensagem_usuario_adicionada_ao_historico(self, client: ClaudeClient):
        """A mensagem do usuário deve ser a última no array enviado ao Claude."""
        historico = [{"role": "user", "content": "anterior"}]
        client._client.messages.create = AsyncMock(return_value=_mock_resposta())  # type: ignore[method-assign]

        await client.enviar_mensagem("system", historico, "nova mensagem")

        args = client._client.messages.create.call_args
        messages_enviadas = args.kwargs["messages"]
        assert messages_enviadas[-1] == {"role": "user", "content": "nova mensagem"}
        assert len(messages_enviadas) == 2

    async def test_retry_em_rate_limit_esgota_e_levanta(self, client: ClaudeClient):
        client._client.messages.create = AsyncMock(side_effect=_rate_limit_error())  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="indisponível"):
            await client.enviar_mensagem("system", [], "msg")
        assert client._client.messages.create.call_count == _MAX_TENTATIVAS

    async def test_retry_em_timeout_esgota_e_levanta(self, client: ClaudeClient):
        client._client.messages.create = AsyncMock(side_effect=_timeout_error())  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            await client.enviar_mensagem("system", [], "msg")
        assert client._client.messages.create.call_count == _MAX_TENTATIVAS

    async def test_auth_error_nao_faz_retry(self, client: ClaudeClient):
        """AuthenticationError deve falhar imediatamente — chave inválida não melhora com retry."""
        client._client.messages.create = AsyncMock(side_effect=_auth_error())  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="inválida"):
            await client.enviar_mensagem("system", [], "msg")
        assert client._client.messages.create.call_count == 1  # apenas 1 tentativa

    async def test_sucesso_na_segunda_tentativa(self, client: ClaudeClient):
        """Falha na 1ª tentativa deve ser recuperada na 2ª."""
        client._client.messages.create = AsyncMock(  # type: ignore[method-assign]
            side_effect=[_rate_limit_error(), _mock_resposta("recuperado")]
        )
        resultado = await client.enviar_mensagem("system", [], "msg")
        assert resultado["resposta"] == "recuperado"
        assert client._client.messages.create.call_count == 2

    async def test_api_error_generico_faz_retry(self, client: ClaudeClient):
        """Erros 5xx devem ser retentados."""
        client._client.messages.create = AsyncMock(side_effect=_server_error())  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            await client.enviar_mensagem("system", [], "msg")
        assert client._client.messages.create.call_count == _MAX_TENTATIVAS

    async def test_usa_modelo_correto(self, client: ClaudeClient):
        from shared.config.constants import MODELO_CLAUDE

        client._client.messages.create = AsyncMock(return_value=_mock_resposta())  # type: ignore[method-assign]
        await client.enviar_mensagem("system", [], "msg")
        kwargs = client._client.messages.create.call_args.kwargs
        assert kwargs["model"] == MODELO_CLAUDE


# ---------------------------------------------------------------------------
# Testes de classificar_intencao
# ---------------------------------------------------------------------------


class TestClassificarIntencao:
    async def test_retorna_texto_bruto_do_claude(self, client: ClaudeClient):
        client._client.messages.create = AsyncMock(  # type: ignore[method-assign]
            return_value=_mock_resposta('{"intencao": "status"}')
        )
        resultado = await client.classificar_intencao("system", "qual o status?")
        assert resultado == '{"intencao": "status"}'

    async def test_usa_max_tokens_32(self, client: ClaudeClient):
        client._client.messages.create = AsyncMock(return_value=_mock_resposta("{}"))  # type: ignore[method-assign]
        await client.classificar_intencao("system", "oi")
        kwargs = client._client.messages.create.call_args.kwargs
        assert kwargs["max_tokens"] == 32

    async def test_usa_temperature_zero(self, client: ClaudeClient):
        client._client.messages.create = AsyncMock(return_value=_mock_resposta("{}"))  # type: ignore[method-assign]
        await client.classificar_intencao("system", "oi")
        kwargs = client._client.messages.create.call_args.kwargs
        assert kwargs["temperature"] == 0.0

    async def test_mensagem_como_user_message(self, client: ClaudeClient):
        """A mensagem deve ir como user message, não embutida no system."""
        client._client.messages.create = AsyncMock(return_value=_mock_resposta("{}"))  # type: ignore[method-assign]
        await client.classificar_intencao("system prompt aqui", "mensagem do cliente")
        kwargs = client._client.messages.create.call_args.kwargs
        assert kwargs["messages"] == [
            {"role": "user", "content": "mensagem do cliente"}
        ]

    async def test_retry_em_rate_limit_na_classificacao(self, client: ClaudeClient):
        """Classificação é a porta de entrada — deve ter retry."""
        client._client.messages.create = AsyncMock(  # type: ignore[method-assign]
            side_effect=[_rate_limit_error(), _mock_resposta('{"intencao": "outro"}')]
        )
        resultado = await client.classificar_intencao("system", "msg")
        assert '{"intencao": "outro"}' in resultado
        assert client._client.messages.create.call_count == 2

    async def test_strip_em_resposta(self, client: ClaudeClient):
        """Resposta com espaços/newlines extras deve ser stripped."""
        client._client.messages.create = AsyncMock(  # type: ignore[method-assign]
            return_value=_mock_resposta('  {"intencao": "status"}\n')
        )
        resultado = await client.classificar_intencao("system", "msg")
        assert resultado == '{"intencao": "status"}'
