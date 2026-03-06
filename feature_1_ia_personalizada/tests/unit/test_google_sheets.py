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

from unittest.mock import MagicMock, call, patch

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

    def test_none_retorna_zero(self):
        assert _int_seguro(None) == 0

    def test_inteiro_direto_aceito(self):
        assert _int_seguro(99) == 99


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

        with patch(
            "feature_1_ia_personalizada.services.integrations.google_sheets.time.sleep"
        ):
            resultado = _retry_http(fn, max_tentativas=3)

        assert resultado == "ok"
        assert fn.call_count == 2

    def test_lanca_excecao_apos_max_tentativas(self):
        resp_mock = MagicMock()
        resp_mock.status = 500
        erro = HttpError(resp=resp_mock, content=b"error")
        fn = MagicMock(side_effect=erro)

        with (
            patch(
                "feature_1_ia_personalizada.services.integrations.google_sheets.time.sleep"
            ),
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

    def test_excecao_nao_http_propagada_sem_retry(self):
        """Erros que não são HttpError devem subir imediatamente, sem retry."""
        fn = MagicMock(side_effect=ValueError("erro inesperado"))
        with pytest.raises(ValueError):
            _retry_http(fn, max_tentativas=3)
        fn.assert_called_once()


# ---------------------------------------------------------------------------
# _ler_intervalo  (testado diretamente para cobrir a camada HTTP interna)
# ---------------------------------------------------------------------------


class TestLerIntervalo:
    def _mock_execute(self, cliente, payload: dict):
        """Configura self._sheet para retornar payload no execute()."""
        cliente._sheet.values.return_value.get.return_value.execute.return_value = (
            payload
        )

    def test_retorna_linhas_da_api(self, cliente):
        self._mock_execute(cliente, {"values": [["a", "b"], ["c", "d"]]})
        assert cliente._ler_intervalo("Clientes!A2:I") == [["a", "b"], ["c", "d"]]

    def test_resposta_sem_values_retorna_lista_vazia(self, cliente):
        self._mock_execute(cliente, {})
        assert cliente._ler_intervalo("Datas!A2:E") == []

    def test_chama_api_com_intervalo_correto(self, cliente):
        self._mock_execute(cliente, {"values": []})
        cliente._ler_intervalo("Log!A:E")
        cliente._sheet.values.return_value.get.assert_called_once_with(
            spreadsheetId="SHEET_ID", range="Log!A:E"
        )


# ---------------------------------------------------------------------------
# get_clientes
# ---------------------------------------------------------------------------


class TestGetClientes:
    def test_retorna_lista_de_dicts(self, cliente):
        linhas = [
            [
                "1",
                "João Silva",
                "5511999990001",
                "123.456.789-00",
                "15/03/1985",
                "Bancário",
                "Banco X",
                "ativo",
                "2024-01-10",
            ],
            [
                "2",
                "Maria Costa",
                "5511999990002",
                "987.654.321-00",
                "22/07/1990",
                "Professora",
                "Escola Y",
                "ativo",
                "",
            ],
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
            [
                "1",
                "João",
                "5511999990001",
                "111.222.333-44",
                "25/12/1980",
                "Eng.",
                "Emp.",
                "ativo",
                "",
            ],
        ]
        with patch.object(cliente, "_ler_intervalo", return_value=linhas):
            resultado = cliente.get_clientes()

        assert resultado[0]["data_nascimento"] == "1980-12-25"

    def test_pula_linhas_com_menos_de_8_colunas(self, cliente):
        linhas = [
            ["1", "João", "55119"],  # 3 colunas → ignorada
            [
                "2",
                "Ana",
                "5511999990002",
                "cpf",
                "nasc",
                "prof",
                "emp",
                "ativo",
            ],  # 8 colunas → ok
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
            [
                "3",
                "Carlos",
                "5511999990003",
                "cpf",
                "nao-e-data",
                "prof",
                "emp",
                "ativo",
                "",
            ],
        ]
        with patch.object(cliente, "_ler_intervalo", return_value=linhas):
            resultado = cliente.get_clientes()
        assert resultado[0]["data_nascimento"] is None

    def test_oito_colunas_exatas_sem_ultimo_contato(self, cliente):
        """Linha com 8 colunas: ultimo_contato deve ser string vazia."""
        linhas = [
            ["1", "Nome", "5511999", "cpf", "01/01/1990", "prof", "emp", "ativo"],
        ]
        with patch.object(cliente, "_ler_intervalo", return_value=linhas):
            resultado = cliente.get_clientes()
        assert resultado[0]["ultimo_contato"] == ""

    def test_get_clientes_propaga_excecao_da_api(self, cliente):
        """Erro na API deve ser propagado (não silenciado)."""
        with (
            patch.object(
                cliente, "_ler_intervalo", side_effect=RuntimeError("API down")
            ),
            pytest.raises(RuntimeError),
        ):
            cliente.get_clientes()


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
            ["bancario", "5"],  # 2 colunas → ignorada
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

    def test_dia_mes_invalidos_viram_zero(self, cliente):
        linhas = [
            ["bancario", "xx", "yy", "Dia Sem Data"],
        ]
        with patch.object(cliente, "_ler_intervalo", return_value=linhas):
            resultado = cliente.get_datas_comemorativas()
        assert resultado[0]["dia"] == 0
        assert resultado[0]["mes"] == 0

    def test_get_datas_propaga_excecao_da_api(self, cliente):
        with (
            patch.object(
                cliente, "_ler_intervalo", side_effect=RuntimeError("API down")
            ),
            pytest.raises(RuntimeError),
        ):
            cliente.get_datas_comemorativas()


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
        assert linha[3] == "Sim"  # sucesso padrão = True

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

    def test_detalhe_usado_quando_sem_erro(self, cliente):
        mock_values = self._mock_sheet(cliente)

        cliente.registrar_log_envio(
            tipo="aniversario",
            cliente_id=5,
            detalhe="mensagem enviada com sucesso",
        )

        linha = mock_values.append.call_args.kwargs["body"]["values"][0]
        assert linha[4] == "mensagem enviada com sucesso"

    def test_propaga_excecao_apos_retries_esgotados(self, cliente):
        resp_mock = MagicMock()
        resp_mock.status = 500
        erro = HttpError(resp=resp_mock, content=b"error")

        mock_execute = MagicMock(side_effect=erro)
        mock_append = MagicMock()
        mock_append.execute = mock_execute
        mock_values = MagicMock()
        mock_values.append.return_value = mock_append
        cliente._sheet = MagicMock()
        cliente._sheet.values.return_value = mock_values

        with (
            patch(
                "feature_1_ia_personalizada.services.integrations.google_sheets.time.sleep"
            ),
            pytest.raises(HttpError),
        ):
            cliente.registrar_log_envio(tipo="test", cliente_id=1, detalhe="test")
