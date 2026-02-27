# feature_1_ia_personalizada/tests/unit/test_google_sheets.py
"""
Testes unitários do GoogleSheetsClient.

Estratégia:
  - O construtor requer credenciais reais, então patchamos
    service_account.Credentials.from_service_account_file e googleapiclient.discovery.build.
  - Os métodos públicos são testados mockando _ler_intervalo (método interno)
    para isolar a lógica de parsing sem depender da API.
  - _parse_data e _int_seguro são testados diretamente.
  - Retry é testado com HttpError simulado.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, call

import pytest
from googleapiclient.errors import HttpError

from feature_1_ia_personalizada.services.integrations.google_sheets import (
    GoogleSheetsClient,
    _int_seguro,
    _parse_data,
    _retry_http,
)


# ---------------------------------------------------------------------------
# Fixture: cliente com API mockada
# ---------------------------------------------------------------------------

@pytest.fixture
def cliente() -> GoogleSheetsClient:
    """Retorna um GoogleSheetsClient com o build da API completamente mockado."""
    mock_service = MagicMock()
    with (
        patch(
            "feature_1_ia_personalizada.services.integrations.google_sheets.service_account"
            ".Credentials.from_service_account_file",
            return_value=MagicMock(),
        ),
        patch(
            "feature_1_ia_personalizada.services.integrations.google_sheets.build",
            return_value=mock_service,
        ),
    ):
        c = GoogleSheetsClient("credenciais.json", "SHEET_ID")
    return c


# ---------------------------------------------------------------------------
# _parse_data
# ---------------------------------------------------------------------------

class TestParseData:
    def test_formato_dd_mm_yyyy(self):
        assert _parse_data("25/12/1990") == "1990-12-25"

    def test_formato_yyyy_mm_dd(self):
        assert _parse_data("1990-12-25") == "1990-12-25"

    def test_string_vazia_retorna_none(self):
        assert _parse_data("") is None

    def test_apenas_espacos_retorna_none(self):
        assert _parse_data("   ") is None

    def test_formato_invalido_retorna_none(self):
        assert _parse_data("nao-e-data") is None

    def test_data_parcial_retorna_none(self):
        assert _parse_data("25/12") is None

    def test_data_com_espacos_e_aceita(self):
        assert _parse_data("  25/12/1990  ") == "1990-12-25"


# ---------------------------------------------------------------------------
# _int_seguro
# ---------------------------------------------------------------------------

class TestIntSeguro:
    def test_string_numerica(self):
        assert _int_seguro("42") == 42

    def test_string_com_espacos(self):
        assert _int_seguro("  7  ") == 7

    def test_string_invalida_retorna_zero(self):
        assert _int_seguro("abc") == 0

    def test_string_vazia_retorna_zero(self):
        assert _int_seguro("") == 0


# ---------------------------------------------------------------------------
# _retry_http
# ---------------------------------------------------------------------------

class TestRetryHttp:
    def test_sucesso_na_primeira_tentativa(self):
        fn = MagicMock(return_value="ok")
        resultado = _retry_http(fn, max_tentativas=3)
        assert resultado == "ok"
        fn.assert_called_once()

    def test_retry_em_caso_de_http_error_e_sucesso_depois(self):
        resp_mock = MagicMock()
        resp_mock.status = 503
        erro = HttpError(resp=resp_mock, content=b"error")
        fn = MagicMock(side_effect=[erro, "ok"])

        with patch("feature_1_ia_personalizada.services.integrations.google_sheets.time.sleep"):
            resultado = _retry_http(fn, max_tentativas=3)

        assert resultado == "ok"
        assert fn.call_count == 2

    def test_lanca_excecao_apos_max_tentativas(self):
        resp_mock = MagicMock()
        resp_mock.status = 500
        erro = HttpError(resp=resp_mock, content=b"error")
        fn = MagicMock(side_effect=erro)

        with (
            patch("feature_1_ia_personalizada.services.integrations.google_sheets.time.sleep"),
            pytest.raises(HttpError),
        ):
            _retry_http(fn, max_tentativas=3)

        assert fn.call_count == 3

    def test_sleep_com_backoff_exponencial(self):
        resp_mock = MagicMock()
        resp_mock.status = 429
        erro = HttpError(resp=resp_mock, content=b"error")
        fn = MagicMock(side_effect=[erro, erro, "ok"])

        with patch(
            "feature_1_ia_personalizada.services.integrations.google_sheets.time.sleep"
        ) as mock_sleep:
            _retry_http(fn, max_tentativas=3)

        assert mock_sleep.call_count == 2
        mock_sleep.assert_has_calls([call(1), call(2)])


# ---------------------------------------------------------------------------
# get_clientes
# ---------------------------------------------------------------------------

class TestGetClientes:
    def test_retorna_lista_de_dicts(self, cliente):
        linhas = [
            ["1", "João Silva", "5511999990001", "123.456.789-00", "15/03/1985", "Bancário", "Banco X", "ativo", "2024-01-10"],
            ["2", "Maria Costa", "5511999990002", "987.654.321-00", "22/07/1990", "Professora", "Escola Y", "ativo", ""],
        ]
        with patch.object(cliente, "_ler_intervalo", return_value=linhas):
            resultado = cliente.get_clientes()

        assert len(resultado) == 2
        assert resultado[0]["id"] == 1
        assert resultado[0]["nome"] == "João Silva"
        assert resultado[0]["telefone"] == "5511999990001"
        assert resultado[0]["status"] == "ativo"

    def test_parse_data_nascimento_dd_mm_yyyy(self, cliente):
        linhas = [
            ["1", "João", "5511999990001", "111.222.333-44", "25/12/1980", "Eng.", "Emp.", "ativo", ""],
        ]
        with patch.object(cliente, "_ler_intervalo", return_value=linhas):
            resultado = cliente.get_clientes()

        assert resultado[0]["data_nascimento"] == "1980-12-25"

    def test_pula_linhas_com_menos_de_8_colunas(self, cliente):
        linhas = [
            ["1", "João", "55119"],                          # 3 colunas → ignorada
            ["2", "Ana", "5511999990002", "cpf", "nasc", "prof", "emp", "ativo"],  # 8 colunas → ok
        ]
        with patch.object(cliente, "_ler_intervalo", return_value=linhas):
            resultado = cliente.get_clientes()

        assert len(resultado) == 1
        assert resultado[0]["nome"] == "Ana"

    def test_lista_vazia_retorna_vazia(self, cliente):
        with patch.object(cliente, "_ler_intervalo", return_value=[]):
            resultado = cliente.get_clientes()
        assert resultado == []

    def test_id_invalido_vira_zero(self, cliente):
        linhas = [
            ["abc", "Nome", "5511999", "cpf", "01/01/1990", "prof", "emp", "ativo", ""],
        ]
        with patch.object(cliente, "_ler_intervalo", return_value=linhas):
            resultado = cliente.get_clientes()
        assert resultado[0]["id"] == 0

    def test_data_invalida_retorna_none(self, cliente):
        linhas = [
            ["3", "Carlos", "5511999990003", "cpf", "nao-e-data", "prof", "emp", "ativo", ""],
        ]
        with patch.object(cliente, "_ler_intervalo", return_value=linhas):
            resultado = cliente.get_clientes()
        assert resultado[0]["data_nascimento"] is None


# ---------------------------------------------------------------------------
# get_datas_comemorativas
# ---------------------------------------------------------------------------

class TestGetDatasComemorativas:
    def test_retorna_lista_de_dicts(self, cliente):
        linhas = [
            ["bancario", "5", "3", "Dia do Bancário", "TEMPLATE_DIA_BANCARIO"],
            ["professor", "15", "10", "Dia do Professor", ""],
        ]
        with patch.object(cliente, "_ler_intervalo", return_value=linhas):
            resultado = cliente.get_datas_comemorativas()

        assert len(resultado) == 2
        assert resultado[0]["profissao_alvo"] == "bancario"
        assert resultado[0]["dia"] == 5
        assert resultado[0]["mes"] == 3
        assert resultado[0]["nome"] == "Dia do Bancário"
        assert resultado[0]["template"] == "TEMPLATE_DIA_BANCARIO"

    def test_pula_linhas_com_menos_de_3_colunas(self, cliente):
        linhas = [
            ["bancario", "5"],                               # 2 colunas → ignorada
            ["professor", "15", "10", "Dia do Professor"],  # 4 colunas → ok
        ]
        with patch.object(cliente, "_ler_intervalo", return_value=linhas):
            resultado = cliente.get_datas_comemorativas()

        assert len(resultado) == 1
        assert resultado[0]["profissao_alvo"] == "professor"

    def test_sem_profissao_alvo_retorna_string_vazia(self, cliente):
        linhas = [
            ["", "1", "1", "Ano Novo", ""],
        ]
        with patch.object(cliente, "_ler_intervalo", return_value=linhas):
            resultado = cliente.get_datas_comemorativas()

        assert resultado[0]["profissao_alvo"] == ""

    def test_lista_vazia_retorna_vazia(self, cliente):
        with patch.object(cliente, "_ler_intervalo", return_value=[]):
            resultado = cliente.get_datas_comemorativas()
        assert resultado == []


# ---------------------------------------------------------------------------
# registrar_log_envio
# ---------------------------------------------------------------------------

class TestRegistrarLogEnvio:
    def _mock_sheet(self, cliente):
        """Retorna o mock do objeto sheets.values().append().execute()."""
        mock_append = MagicMock()
        mock_values = MagicMock()
        mock_values.append.return_value = mock_append
        cliente._sheet = MagicMock()
        cliente._sheet.values.return_value = mock_values
        return mock_values

    def test_chama_append_com_5_colunas(self, cliente):
        mock_values = self._mock_sheet(cliente)

        with patch(
            "feature_1_ia_personalizada.services.integrations.google_sheets.time.sleep"
        ):
            cliente.registrar_log_envio(
                tipo="aniversario",
                cliente_id=42,
                detalhe="processo=0001234-56.2023.8.26.0001",
            )

        mock_values.append.assert_called_once()
        kwargs = mock_values.append.call_args.kwargs
        assert kwargs["range"] == "Log!A:E"
        assert kwargs["valueInputOption"] == "RAW"
        linha = kwargs["body"]["values"][0]
        assert linha[0] == "42"
        assert linha[1] == "aniversario"
        assert linha[3] == "Sim"    # sucesso padrão = True

    def test_sucesso_false_registra_nao(self, cliente):
        mock_values = self._mock_sheet(cliente)

        with patch(
            "feature_1_ia_personalizada.services.integrations.google_sheets.time.sleep"
        ):
            cliente.registrar_log_envio(
                tipo="check_in",
                cliente_id=10,
                detalhe="",
                sucesso=False,
                erro="timeout",
            )

        kwargs = mock_values.append.call_args.kwargs
        linha = kwargs["body"]["values"][0]
        assert linha[3] == "Não"
        assert linha[4] == "timeout"

    def test_retry_em_append_com_http_error(self, cliente):
        resp_mock = MagicMock()
        resp_mock.status = 503
        erro = HttpError(resp=resp_mock, content=b"error")

        mock_execute = MagicMock(side_effect=[erro, None])
        mock_append = MagicMock()
        mock_append.execute = mock_execute
        mock_values = MagicMock()
        mock_values.append.return_value = mock_append
        cliente._sheet = MagicMock()
        cliente._sheet.values.return_value = mock_values

        with patch(
            "feature_1_ia_personalizada.services.integrations.google_sheets.time.sleep"
        ):
            cliente.registrar_log_envio(
                tipo="data_comemorativa",
                cliente_id=1,
                detalhe="ok",
            )

        assert mock_execute.call_count == 2
