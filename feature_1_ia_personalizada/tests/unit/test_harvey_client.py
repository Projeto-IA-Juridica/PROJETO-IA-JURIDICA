# feature_1_ia_personalizada/tests/unit/test_harvey_client.py
"""
Testes unitários do HarveyClient.

Estratégia de mock:
- `_http_post_sync` é substituído por um MagicMock na fixture, pois é o
  único ponto de I/O real do cliente.
- `run_in_executor` é patchado para chamar o lambda de forma síncrona,
  evitando a necessidade de um event loop real com thread pool.
- `asyncio.sleep` é patchado para eliminar delays do backoff.
- O pybreaker real é usado nos testes de circuit breaker — permite validar
  a integração com a lib sem mocks frágeis internos.
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pybreaker
import pytest

from feature_1_ia_personalizada.services.ai.harvey_client import (
    AnaliseHarveyResponse,
    HarveyClient,
    HarveyResponse,
    HarveyUnavailableError,
    Jurisprudencia,
    TipoAnaliseHarvey,
    _calcular_custo,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RESPOSTA_CHAT_OK = {
    "choices": [{"message": {"content": "Resposta jurídica do Harvey."}}],
    "usage": {"prompt_tokens": 200, "completion_tokens": 80},
}

_RESPOSTA_ANALISE_OK = {
    "choices": [
        {
            "message": {
                "content": json.dumps(
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
            }
        }
    ],
    "usage": {"prompt_tokens": 500, "completion_tokens": 300},
}

_RESPOSTA_JURIS_OK = {
    "choices": [
        {
            "message": {
                "content": json.dumps(
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
            }
        }
    ],
    "usage": {"prompt_tokens": 100, "completion_tokens": 200},
}


def _make_sync_response(payload: dict, status_code: int = 200) -> MagicMock:
    """Mock de resposta httpx.Response síncrona."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.text = json.dumps(payload)
    resp.raise_for_status = MagicMock()
    return resp


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://api.harvey.ai/v1/chat/completions")
    resp = httpx.Response(status_code, request=req)
    return httpx.HTTPStatusError(f"HTTP {status_code}", request=req, response=resp)


# ---------------------------------------------------------------------------
# Fixture: cliente com I/O isolado + executor síncrono + sleep patchado
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch) -> HarveyClient:
    """
    HarveyClient com:
    - settings mockados (evita dependência de .env)
    - run_in_executor substituído por chamada síncrona direta
    - asyncio.sleep sem delay real
    """
    with (
        patch("feature_1_ia_personalizada.services.ai.harvey_client.settings") as mock_settings,
        patch("httpx.Client"),
    ):
        mock_settings.HARVEY_API_KEY = "sk-harvey-test"
        mock_settings.HARVEY_API_URL = "https://api.harvey.ai/v1"
        mock_settings.HARVEY_MODELO = "harvey-v3"
        mock_settings.HARVEY_TIMEOUT = 45
        mock_settings.HARVEY_HABILITADO = True

        c = HarveyClient()

    # run_in_executor chama o lambda de forma síncrona — evita thread pool real
    async def fake_executor(executor, fn):
        return fn()

    mock_loop = MagicMock()
    mock_loop.run_in_executor = fake_executor
    monkeypatch.setattr(
        "feature_1_ia_personalizada.services.ai.harvey_client.asyncio.get_event_loop",
        lambda: mock_loop,
    )

    return c


@pytest.fixture(autouse=True)
async def no_sleep():
    with patch("asyncio.sleep", new_callable=AsyncMock):
        yield


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    """
    Reseta o circuit breaker global antes de cada teste.

    _harvey_cb é singleton de módulo — sem reset, falhas de um teste
    acumulam no breaker e contaminam os testes seguintes.
    """
    fresh_cb = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=120, name="harvey_test")
    with patch(
        "feature_1_ia_personalizada.services.ai.harvey_client._harvey_cb",
        fresh_cb,
    ):
        yield


# ---------------------------------------------------------------------------
# _calcular_custo (helper puro)
# ---------------------------------------------------------------------------


class TestCalcularCusto:
    def test_zero_tokens_retorna_zero(self):
        assert _calcular_custo(0, 0) == Decimal("0")

    def test_retorna_decimal(self):
        assert isinstance(_calcular_custo(100, 50), Decimal)

    def test_input_caro(self):
        # 1M tokens input = $15.00
        assert _calcular_custo(1_000_000, 0) == Decimal("15.00")

    def test_output_mais_caro(self):
        # 1M tokens output = $60.00
        assert _calcular_custo(0, 1_000_000) == Decimal("60.00")


# ---------------------------------------------------------------------------
# gerar_resposta
# ---------------------------------------------------------------------------


class TestGerarResposta:
    async def test_sucesso_retorna_harvey_response(self, client: HarveyClient):
        client._http_post_sync = MagicMock(return_value=_RESPOSTA_CHAT_OK)

        resultado = await client.gerar_resposta(
            system_prompt="Você é um assistente jurídico.",
            mensagem_usuario="O que é CPC art. 485?",
        )

        assert isinstance(resultado, HarveyResponse)
        assert resultado.conteudo == "Resposta jurídica do Harvey."
        assert resultado.tokens_input == 200
        assert resultado.tokens_output == 80
        assert isinstance(resultado.custo_estimado, Decimal)
        assert resultado.modelo == "harvey-v3"
        assert resultado.latencia_ms >= 0

    async def test_contexto_rag_concatenado_na_mensagem(self, client: HarveyClient):
        client._http_post_sync = MagicMock(return_value=_RESPOSTA_CHAT_OK)

        await client.gerar_resposta(
            system_prompt="system",
            mensagem_usuario="pergunta",
            contexto_rag="contexto legal relevante",
        )

        payload = client._http_post_sync.call_args[0][1]
        user_content = payload["messages"][-1]["content"]
        assert "contexto legal relevante" in user_content
        assert "pergunta" in user_content

    async def test_sem_contexto_rag_usa_mensagem_direta(self, client: HarveyClient):
        client._http_post_sync = MagicMock(return_value=_RESPOSTA_CHAT_OK)

        await client.gerar_resposta(
            system_prompt="system",
            mensagem_usuario="pergunta direta",
        )

        payload = client._http_post_sync.call_args[0][1]
        user_content = payload["messages"][-1]["content"]
        assert user_content == "pergunta direta"

    async def test_levanta_harvey_unavailable_em_erro_4xx(self, client: HarveyClient):
        client._http_post_sync = MagicMock(side_effect=_http_status_error(401))

        with pytest.raises(HarveyUnavailableError, match="401"):
            await client.gerar_resposta("system", "pergunta")

    async def test_retry_em_erro_500_esgota_e_levanta(self, client: HarveyClient):
        client._http_post_sync = MagicMock(side_effect=_http_status_error(500))

        with pytest.raises(HarveyUnavailableError):
            await client.gerar_resposta("system", "pergunta")

        assert client._http_post_sync.call_count == HarveyClient.MAX_RETRIES

    async def test_sucesso_na_segunda_tentativa(self, client: HarveyClient):
        client._http_post_sync = MagicMock(
            side_effect=[_http_status_error(503), _RESPOSTA_CHAT_OK]
        )

        resultado = await client.gerar_resposta("system", "pergunta")

        assert resultado.conteudo == "Resposta jurídica do Harvey."
        assert client._http_post_sync.call_count == 2

    async def test_timeout_faz_retry(self, client: HarveyClient):
        client._http_post_sync = MagicMock(
            side_effect=httpx.TimeoutException("timeout")
        )

        with pytest.raises(HarveyUnavailableError):
            await client.gerar_resposta("system", "pergunta")

        assert client._http_post_sync.call_count == HarveyClient.MAX_RETRIES

    async def test_circuit_breaker_aberto_levanta_sem_retry(self, client: HarveyClient):
        """Quando o circuit breaker abre, deve propagar HarveyUnavailableError imediatamente."""
        # Força abertura do circuit breaker substituindo-o por um mock aberto
        mock_cb = MagicMock()
        mock_cb.call.side_effect = pybreaker.CircuitBreakerError()

        with patch(
            "feature_1_ia_personalizada.services.ai.harvey_client._harvey_cb",
            mock_cb,
        ):
            with pytest.raises(HarveyUnavailableError, match="circuit breaker"):
                await client.gerar_resposta("system", "pergunta")

        # Circuit aberto: não deve tentar chamar _http_post_sync
        assert mock_cb.call.call_count == 1


# ---------------------------------------------------------------------------
# analisar_peticao
# ---------------------------------------------------------------------------


class TestAnalisarPeticao:
    async def test_sucesso_retorna_analise_harvey_response(self, client: HarveyClient):
        client._http_post_sync = MagicMock(return_value=_RESPOSTA_ANALISE_OK)

        resultado = await client.analisar_peticao(
            conteudo_peticao="Texto da petição inicial...",
            tipo_analise=TipoAnaliseHarvey.ANALISE_COMPLETA,
        )

        assert isinstance(resultado, AnaliseHarveyResponse)
        assert resultado.tipo_peca == "Petição Inicial"
        assert "Fundamentação sólida" in resultado.pontos_fortes
        assert "Ausência de precedentes" in resultado.vulnerabilidades
        assert resultado.score_geral == 75

    async def test_tipo_analise_incluido_no_payload(self, client: HarveyClient):
        client._http_post_sync = MagicMock(return_value=_RESPOSTA_ANALISE_OK)

        await client.analisar_peticao(
            conteudo_peticao="texto",
            tipo_analise=TipoAnaliseHarvey.PONTOS_FRACOS,
        )

        payload = client._http_post_sync.call_args[0][1]
        user_content = payload["messages"][-1]["content"]
        assert "pontos_fracos" in user_content

    async def test_json_invalido_levanta_harvey_unavailable(self, client: HarveyClient):
        resposta_invalida = {
            "choices": [{"message": {"content": "não é JSON válido {"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        client._http_post_sync = MagicMock(return_value=resposta_invalida)

        with pytest.raises(HarveyUnavailableError, match="JSON inválido"):
            await client.analisar_peticao("texto da petição")

    async def test_campos_ausentes_usam_defaults(self, client: HarveyClient):
        resposta_parcial = {
            "choices": [{"message": {"content": json.dumps({"tipo_peca": "Contestação"})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        client._http_post_sync = MagicMock(return_value=resposta_parcial)

        resultado = await client.analisar_peticao("texto")

        assert resultado.pontos_fortes == []
        assert resultado.score_geral == 0


# ---------------------------------------------------------------------------
# pesquisar_jurisprudencia
# ---------------------------------------------------------------------------


class TestPesquisarJurisprudencia:
    async def test_sucesso_retorna_lista_jurisprudencia(self, client: HarveyClient):
        client._http_post_sync = MagicMock(return_value=_RESPOSTA_JURIS_OK)

        resultado = await client.pesquisar_jurisprudencia(
            query="dano moral contrato de seguro",
            tribunal="STJ",
            periodo="2023-2025",
        )

        assert len(resultado) == 1
        assert isinstance(resultado[0], Jurisprudencia)
        assert resultado[0].tribunal == "STJ"
        assert resultado[0].aplicabilidade == "FAVORAVEL"
        assert resultado[0].relevancia_score == 0.95

    async def test_filtros_incluidos_na_mensagem(self, client: HarveyClient):
        client._http_post_sync = MagicMock(return_value=_RESPOSTA_JURIS_OK)

        await client.pesquisar_jurisprudencia(
            query="responsabilidade civil",
            tribunal="TJSP",
            periodo="2024",
        )

        payload = client._http_post_sync.call_args[0][1]
        user_content = payload["messages"][-1]["content"]
        assert "TJSP" in user_content
        assert "2024" in user_content

    async def test_lista_vazia_quando_sem_resultados(self, client: HarveyClient):
        resposta_vazia = {
            "choices": [{"message": {"content": json.dumps({"resultados": []})}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        }
        client._http_post_sync = MagicMock(return_value=resposta_vazia)

        resultado = await client.pesquisar_jurisprudencia("query sem resultado")

        assert resultado == []

    async def test_json_invalido_levanta_harvey_unavailable(self, client: HarveyClient):
        resposta_invalida = {
            "choices": [{"message": {"content": "texto livre sem JSON"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        client._http_post_sync = MagicMock(return_value=resposta_invalida)

        with pytest.raises(HarveyUnavailableError, match="JSON inválido"):
            await client.pesquisar_jurisprudencia("query")


# ---------------------------------------------------------------------------
# _extrair_resposta (helper estático)
# ---------------------------------------------------------------------------


class TestExtrairResposta:
    def test_extrai_conteudo_e_tokens(self):
        conteudo, tokens_in, tokens_out = HarveyClient._extrair_resposta(_RESPOSTA_CHAT_OK)
        assert conteudo == "Resposta jurídica do Harvey."
        assert tokens_in == 200
        assert tokens_out == 80

    def test_uso_ausente_retorna_zeros(self):
        dados = {"choices": [{"message": {"content": "texto"}}]}
        _, tokens_in, tokens_out = HarveyClient._extrair_resposta(dados)
        assert tokens_in == 0
        assert tokens_out == 0

    def test_formato_inesperado_levanta_harvey_unavailable(self):
        with pytest.raises(HarveyUnavailableError, match="formato inesperado"):
            HarveyClient._extrair_resposta({"erro": "bad gateway"})
