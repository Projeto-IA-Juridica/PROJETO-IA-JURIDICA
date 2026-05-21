# feature_1_ia_personalizada/tests/unit/test_escalation_client.py
"""
Testes unitários do EscalacaoClient.

Usa o mesmo SDK Anthropic do projeto — AsyncAnthropic é mockado via
patch do método `messages.create` para evitar chamadas reais.
asyncio.sleep patchado globalmente para eliminar delays de backoff.
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx
import pytest

from feature_1_ia_personalizada.services.ai.escalation_client import (
    AnalisePecaResponse,
    EscalacaoClient,
    EscalacaoIndisponivelError,
    EscalacaoResponse,
    Jurisprudencia,
    TipoAnalise,
    _calcular_custo,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bloco_texto(texto: str) -> MagicMock:
    b = MagicMock()
    b.type = "text"
    b.text = texto
    return b


def _mock_resposta(
    texto: str = "Resposta Opus.", tokens_in: int = 200, tokens_out: int = 80
) -> MagicMock:
    r = MagicMock(spec=anthropic.types.Message)
    r.content = [_bloco_texto(texto)]
    r.usage = MagicMock()
    r.usage.input_tokens = tokens_in
    r.usage.output_tokens = tokens_out
    return r


def _rate_limit_error() -> anthropic.RateLimitError:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 429
    resp.headers = httpx.Headers({})
    return anthropic.RateLimitError(message="rate limited", response=resp, body=None)


def _timeout_error() -> anthropic.APITimeoutError:
    return anthropic.APITimeoutError(request=MagicMock(spec=httpx.Request))


def _auth_error() -> anthropic.AuthenticationError:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 401
    resp.headers = httpx.Headers({})
    return anthropic.AuthenticationError(message="auth error", response=resp, body=None)


_ANALISE_JSON = json.dumps(
    {
        "tipo_peca": "Petição Inicial",
        "pontos_fortes": ["Fundamentação sólida"],
        "vulnerabilidades": ["Ausência de precedentes"],
        "argumentos_ausentes": ["Dano moral"],
        "precedentes_relevantes": ["REsp 1.234.567/SP"],
        "score_geral": 75,
        "sugestoes": ["Juntar jurisprudência do STJ"],
    }
)

_JURIS_JSON = json.dumps(
    {
        "resultados": [
            {
                "ementa": "Ementa do acórdão",
                "tribunal": "STJ",
                "numero_processo": "REsp 1.000.000/SP",
                "data_julgamento": "2025-03-15",
                "aplicabilidade": "FAVORAVEL",
                "relevancia_score": 0.95,
            }
        ]
    }
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> EscalacaoClient:
    with patch("anthropic.AsyncAnthropic"):
        c = EscalacaoClient()
    c._client = MagicMock()
    c._client.messages = MagicMock()
    return c


@pytest.fixture(autouse=True)
async def no_sleep():
    with patch("asyncio.sleep", new_callable=AsyncMock):
        yield


# ---------------------------------------------------------------------------
# _calcular_custo
# ---------------------------------------------------------------------------


class TestCalcularCusto:
    def test_zero_tokens(self):
        assert _calcular_custo(0, 0) == Decimal("0")

    def test_retorna_decimal(self):
        assert isinstance(_calcular_custo(100, 50), Decimal)

    def test_input_opus(self):
        assert _calcular_custo(1_000_000, 0) == Decimal("15.00")

    def test_output_opus(self):
        assert _calcular_custo(0, 1_000_000) == Decimal("75.00")


# ---------------------------------------------------------------------------
# gerar_resposta
# ---------------------------------------------------------------------------


class TestGerarResposta:
    async def test_sucesso_retorna_escalacao_response(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(return_value=_mock_resposta())

        resultado = await client.gerar_resposta(
            system_prompt="Você é jurídico.",
            mensagem_usuario="O que é CPC art. 485?",
        )

        assert isinstance(resultado, EscalacaoResponse)
        assert resultado.conteudo == "Resposta Opus."
        assert resultado.tokens_input == 200
        assert resultado.tokens_output == 80
        assert isinstance(resultado.custo_estimado, Decimal)
        assert resultado.latencia_ms >= 0

    async def test_contexto_rag_concatenado(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(return_value=_mock_resposta())

        await client.gerar_resposta(
            system_prompt="system",
            mensagem_usuario="pergunta",
            contexto_rag="contexto relevante",
        )

        kwargs = client._client.messages.create.call_args.kwargs
        user_content = kwargs["messages"][-1]["content"]
        assert "contexto relevante" in user_content
        assert "pergunta" in user_content

    async def test_sem_rag_usa_mensagem_direta(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(return_value=_mock_resposta())

        await client.gerar_resposta(system_prompt="system", mensagem_usuario="pergunta direta")

        kwargs = client._client.messages.create.call_args.kwargs
        assert kwargs["messages"][-1]["content"] == "pergunta direta"

    async def test_auth_error_falha_imediato(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(side_effect=_auth_error())

        with pytest.raises(EscalacaoIndisponivelError, match="Chave Anthropic"):
            await client.gerar_resposta("system", "pergunta")

        assert client._client.messages.create.call_count == 1

    async def test_rate_limit_faz_retry_e_levanta(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(side_effect=_rate_limit_error())

        with pytest.raises(EscalacaoIndisponivelError, match="indisponível"):
            await client.gerar_resposta("system", "pergunta")

        assert client._client.messages.create.call_count == EscalacaoClient.MAX_RETRIES

    async def test_timeout_faz_retry_e_levanta(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(side_effect=_timeout_error())

        with pytest.raises(EscalacaoIndisponivelError):
            await client.gerar_resposta("system", "pergunta")

        assert client._client.messages.create.call_count == EscalacaoClient.MAX_RETRIES

    async def test_sucesso_na_segunda_tentativa(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(
            side_effect=[_rate_limit_error(), _mock_resposta("recuperado")]
        )

        resultado = await client.gerar_resposta("system", "pergunta")

        assert resultado.conteudo == "recuperado"
        assert client._client.messages.create.call_count == 2

    async def test_usa_modelo_de_escalacao(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(return_value=_mock_resposta())

        await client.gerar_resposta("system", "pergunta")

        kwargs = client._client.messages.create.call_args.kwargs
        assert kwargs["model"] == client._modelo


# ---------------------------------------------------------------------------
# analisar_peca
# ---------------------------------------------------------------------------


class TestAnalisarPeca:
    async def test_sucesso_retorna_analise_response(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(return_value=_mock_resposta(_ANALISE_JSON))

        resultado = await client.analisar_peca(
            conteudo_peca="Texto da petição...",
            tipo_analise=TipoAnalise.ANALISE_COMPLETA,
        )

        assert isinstance(resultado, AnalisePecaResponse)
        assert resultado.tipo_peca == "Petição Inicial"
        assert "Fundamentação sólida" in resultado.pontos_fortes
        assert resultado.score_geral == 75

    async def test_tipo_analise_no_payload(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(return_value=_mock_resposta(_ANALISE_JSON))

        await client.analisar_peca("texto", tipo_analise=TipoAnalise.PONTOS_FRACOS)

        kwargs = client._client.messages.create.call_args.kwargs
        assert "pontos_fracos" in kwargs["messages"][-1]["content"]

    async def test_json_invalido_levanta_erro(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(return_value=_mock_resposta("não é JSON {"))

        with pytest.raises(EscalacaoIndisponivelError, match="JSON inválido"):
            await client.analisar_peca("texto")

    async def test_campos_ausentes_usam_defaults(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(
            return_value=_mock_resposta(json.dumps({"tipo_peca": "Contestação"}))
        )

        resultado = await client.analisar_peca("texto")

        assert resultado.pontos_fortes == []
        assert resultado.score_geral == 0


# ---------------------------------------------------------------------------
# pesquisar_jurisprudencia
# ---------------------------------------------------------------------------


class TestPesquisarJurisprudencia:
    async def test_sucesso_retorna_lista(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(return_value=_mock_resposta(_JURIS_JSON))

        resultado = await client.pesquisar_jurisprudencia("dano moral", tribunal="STJ")

        assert len(resultado) == 1
        assert isinstance(resultado[0], Jurisprudencia)
        assert resultado[0].aplicabilidade == "FAVORAVEL"

    async def test_filtros_na_mensagem(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(return_value=_mock_resposta(_JURIS_JSON))

        await client.pesquisar_jurisprudencia("query", tribunal="TJSP", periodo="2024")

        kwargs = client._client.messages.create.call_args.kwargs
        conteudo = kwargs["messages"][-1]["content"]
        assert "TJSP" in conteudo
        assert "2024" in conteudo

    async def test_lista_vazia_sem_resultados(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(
            return_value=_mock_resposta(json.dumps({"resultados": []}))
        )

        assert await client.pesquisar_jurisprudencia("query") == []

    async def test_json_invalido_levanta_erro(self, client: EscalacaoClient):
        client._client.messages.create = AsyncMock(return_value=_mock_resposta("sem json"))

        with pytest.raises(EscalacaoIndisponivelError, match="JSON inválido"):
            await client.pesquisar_jurisprudencia("query")
