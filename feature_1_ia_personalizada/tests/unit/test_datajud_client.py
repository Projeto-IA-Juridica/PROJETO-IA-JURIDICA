# feature_1_ia_personalizada/tests/unit/test_datajud_client.py
"""
Testes unitários para DataJudClient.
Mocka asyncio.sleep para evitar delay real (2s) na suite de testes.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from feature_1_ia_personalizada.services.legal_data.datajud_client import (
    DataJudClient,
    DataJudClientError,
)


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


class TestConsultarProcesso:
    @pytest.fixture(autouse=True)
    def _patch_sleep(self):
        """Remove o delay de 2s do asyncio.sleep para a suite de testes."""
        with patch(
            "feature_1_ia_personalizada.services.legal_data.datajud_client.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            self._sleep = mock_sleep
            yield

    async def test_retorna_payload_mock(self):
        client = DataJudClient()
        resultado = await client.consultar_processo("0001234-56.2024.8.26.0100")
        assert "hits" in resultado
        assert "hits" in resultado["hits"]

    async def test_payload_contem_numero_cnj(self):
        cnj = "0001234-56.2024.8.26.0100"
        client = DataJudClient()
        resultado = await client.consultar_processo(cnj)
        fonte = resultado["hits"]["hits"][0]["_source"]
        assert fonte["numeroProcesso"] == cnj

    async def test_payload_contem_movimentos(self):
        client = DataJudClient()
        resultado = await client.consultar_processo("1234567-89.2024.8.26.0100")
        fonte = resultado["hits"]["hits"][0]["_source"]
        assert "movimentos" in fonte
        assert len(fonte["movimentos"]) >= 1

    async def test_payload_contem_classe_e_tribunal(self):
        client = DataJudClient()
        resultado = await client.consultar_processo("0001234-56.2024.8.26.0100")
        fonte = resultado["hits"]["hits"][0]["_source"]
        assert "classe" in fonte
        assert "tribunal" in fonte

    async def test_sleep_chamado_uma_vez(self):
        client = DataJudClient()
        await client.consultar_processo("0001234-56.2024.8.26.0100")
        self._sleep.assert_called_once_with(2.0)

    async def test_diferentes_cnjs_retornam_payload_com_cnj_correto(self):
        client = DataJudClient()
        cnj1 = "1111111-11.2024.8.26.0100"
        cnj2 = "2222222-22.2024.8.26.0100"
        res1 = await client.consultar_processo(cnj1)
        res2 = await client.consultar_processo(cnj2)
        assert res1["hits"]["hits"][0]["_source"]["numeroProcesso"] == cnj1
        assert res2["hits"]["hits"][0]["_source"]["numeroProcesso"] == cnj2


class TestDataJudClientError:
    def test_pode_ser_levantada(self):
        with pytest.raises(DataJudClientError):
            raise DataJudClientError("Erro de teste")

    def test_herda_de_exception(self):
        assert issubclass(DataJudClientError, Exception)
