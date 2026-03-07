# feature_1_ia_personalizada/tests/unit/test_datajud_client.py
"""
Testes unitários para DataJudClient.
Mocka httpx.AsyncClient para evitar chamadas HTTP reais na suite.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.legal_data.datajud_client import (
    DataJudClient,
    DataJudClientError,
    _indice_para_cnj,
)

_CNJ_TJSP = "0001234-56.2024.8.26.0100"
_CNJ_STJ = "0001234-56.2024.3.00.0000"
_CNJ_TRF3 = "0001234-56.2024.5.03.0000"


def _make_httpx_mock(status_code: int = 200, payload: dict | None = None) -> MagicMock:
    """Cria mock do httpx.AsyncClient que retorna status e JSON controlados."""
    if payload is None:
        payload = {"hits": {"hits": [], "total": {"value": 0}}}

    response_mock = MagicMock()
    response_mock.status_code = status_code
    response_mock.json.return_value = payload
    response_mock.text = ""

    client_mock = AsyncMock()
    client_mock.post = AsyncMock(return_value=response_mock)
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=None)
    return client_mock


class TestIndiceParaCnj:
    def test_tjsp_retorna_indice_correto(self):
        assert _indice_para_cnj(_CNJ_TJSP) == "api_publica_tjsp"

    def test_stj_retorna_indice_correto(self):
        assert _indice_para_cnj(_CNJ_STJ) == "api_publica_stj"

    def test_trf3_retorna_indice_correto(self):
        assert _indice_para_cnj(_CNJ_TRF3) == "api_publica_trf3"

    def test_tjrj_retorna_indice_correto(self):
        assert _indice_para_cnj("0001234-56.2024.8.19.0001") == "api_publica_tjrj"

    def test_cnj_invalido_levanta_erro(self):
        with pytest.raises(DataJudClientError, match="inválido"):
            _indice_para_cnj("numero-invalido")

    def test_tribunal_nao_mapeado_levanta_erro(self):
        with pytest.raises(DataJudClientError):
            _indice_para_cnj("0001234-56.2024.8.99.0000")  # TT=99 não existe


class TestDataJudClientInit:
    def test_instancia_sem_api_key(self):
        client = DataJudClient()
        assert client.api_key is None
        assert "datajud.cnj.jus.br" in client._base_url

    def test_instancia_com_api_key(self):
        client = DataJudClient(api_key="minha-chave-123")
        assert client.api_key == "minha-chave-123"

    def test_base_url_configurada(self):
        client = DataJudClient()
        assert client._base_url == "https://api-publica.datajud.cnj.jus.br"

    def test_headers_sem_key_nao_tem_authorization(self):
        client = DataJudClient()
        assert "Authorization" not in client._headers()

    def test_headers_com_key_tem_authorization(self):
        client = DataJudClient(api_key="abc123")
        assert client._headers()["Authorization"] == "ApiKey abc123"


class TestConsultarProcesso:
    @pytest.fixture(autouse=True)
    def _patch_httpx(self):
        """Substitui httpx.AsyncClient por mock para todos os testes da classe."""
        self._payload = {"hits": {"hits": [], "total": {"value": 0}}}
        self._http_mock = _make_httpx_mock(payload=self._payload)
        with patch(
            "feature_1_ia_personalizada.services.legal_data.datajud_client.httpx.AsyncClient",
            return_value=self._http_mock,
        ):
            yield

    async def test_retorna_payload_com_hits(self):
        client = DataJudClient()
        resultado = await client.consultar_processo(_CNJ_TJSP)
        assert "hits" in resultado
        assert "hits" in resultado["hits"]

    async def test_chama_url_correta_tjsp(self):
        client = DataJudClient()
        await client.consultar_processo(_CNJ_TJSP)
        url_chamada = self._http_mock.post.call_args[0][0]
        assert "api_publica_tjsp" in url_chamada
        assert "_search" in url_chamada

    async def test_query_contem_numero_cnj(self):
        client = DataJudClient()
        await client.consultar_processo(_CNJ_TJSP)
        body = self._http_mock.post.call_args[1]["json"]
        assert body["query"]["match"]["numeroProcesso"] == _CNJ_TJSP

    async def test_sem_api_key_nao_envia_authorization(self):
        client = DataJudClient()
        await client.consultar_processo(_CNJ_TJSP)
        headers = self._http_mock.post.call_args[1]["headers"]
        assert "Authorization" not in headers

    async def test_com_api_key_envia_authorization(self):
        client = DataJudClient(api_key="chave-test")
        await client.consultar_processo(_CNJ_TJSP)
        headers = self._http_mock.post.call_args[1]["headers"]
        assert headers["Authorization"] == "ApiKey chave-test"

    async def test_http_401_levanta_erro_autenticacao(self):
        self._http_mock.post.return_value.status_code = 401
        client = DataJudClient()
        with pytest.raises(DataJudClientError, match="autenticação"):
            await client.consultar_processo(_CNJ_TJSP)

    async def test_http_404_levanta_erro_indice(self):
        self._http_mock.post.return_value.status_code = 404
        client = DataJudClient()
        with pytest.raises(DataJudClientError, match="índice"):
            await client.consultar_processo(_CNJ_TJSP)

    async def test_http_500_levanta_erro_generico(self):
        self._http_mock.post.return_value.status_code = 500
        client = DataJudClient()
        with pytest.raises(DataJudClientError, match="HTTP 500"):
            await client.consultar_processo(_CNJ_TJSP)

    async def test_cnj_invalido_levanta_erro_antes_de_chamar_http(self):
        client = DataJudClient()
        with pytest.raises(DataJudClientError):
            await client.consultar_processo("cnj-invalido")
        self._http_mock.post.assert_not_called()


class TestDataJudClientError:
    def test_pode_ser_levantada(self):
        with pytest.raises(DataJudClientError):
            raise DataJudClientError("Erro de teste")

    def test_herda_de_exception(self):
        assert issubclass(DataJudClientError, Exception)
