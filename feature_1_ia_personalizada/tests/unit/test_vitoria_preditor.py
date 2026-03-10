# feature_1_ia_personalizada/tests/unit/test_vitoria_preditor.py
"""
Testes do VitoriaPreditor — contexto histórico de casos similares (DataJud/CNJ).

Cobertura:
  - EstatisticaProcessual dataclass
  - _contar_desfechos  (lógica pura, sem I/O)
  - _calcular_confianca (lógica pura)
  - _montar_fatores    (lógica pura)
  - buscar_estatistica (mocked HTTP — happy path, erros, edge cases)
  - _buscar_casos_similares (HTTP timeout, 4xx/5xx, rede, resposta vazia)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from feature_1_ia_personalizada.services.legal_data.vitoria_preditor import (
    DISCLAIMER_ESTATISTICA,
    MIN_CASOS_COM_DESFECHO,
    EstatisticaProcessual,
    VitoriaPreditor,
)

# ---------------------------------------------------------------------------
# Constantes de teste
# ---------------------------------------------------------------------------

_CNJ_TJSP = "0001234-56.2024.8.26.0100"  # tribunal TJSP → api_publica_tjsp
_CNJ_INVALIDO = "numero-invalido"
_TIPO_ACAO = "Ação de Indenização por Dano Moral"

# ---------------------------------------------------------------------------
# Helpers de mock HTTP
# ---------------------------------------------------------------------------


def _hits_payload(casos: list[dict]) -> dict:
    """Monta o payload DataJud com a lista de casos (_source)."""
    return {"hits": {"hits": [{"_source": c} for c in casos]}}


def _make_httpx_mock(
    payload: dict | None = None,
    status_code: int = 200,
    raise_exc: Exception | None = None,
) -> MagicMock:
    """
    Cria mock do httpx.AsyncClient compatível com context manager assíncrono.

    - payload:    JSON retornado por resp.json()
    - raise_exc:  exceção lançada por client.post() (simula timeout/rede)
    - status_code + raise_exc via raise_for_status: simula erros HTTP
    """
    response_mock = MagicMock()
    response_mock.status_code = status_code
    response_mock.json.return_value = payload or {"hits": {"hits": []}}

    if isinstance(raise_exc, (httpx.TimeoutException, httpx.RequestError)):
        # Exceção lançada pelo próprio client.post() (antes de raise_for_status)
        client_mock = AsyncMock()
        client_mock.post = AsyncMock(side_effect=raise_exc)
        client_mock.__aenter__ = AsyncMock(return_value=client_mock)
        client_mock.__aexit__ = AsyncMock(return_value=None)
        return client_mock

    if isinstance(raise_exc, httpx.HTTPStatusError):
        response_mock.raise_for_status.side_effect = raise_exc
    else:
        response_mock.raise_for_status.return_value = None

    client_mock = AsyncMock()
    client_mock.post = AsyncMock(return_value=response_mock)
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=None)
    return client_mock


def _patch_http(mock: MagicMock):
    """Context manager que substitui httpx.AsyncClient no módulo vitoria_preditor."""
    return patch(
        "feature_1_ia_personalizada.services.legal_data.vitoria_preditor.httpx.AsyncClient",
        return_value=mock,
    )


def _preditor() -> VitoriaPreditor:
    return VitoriaPreditor(api_key="test-key")


# ---------------------------------------------------------------------------
# Casos DataJud
# ---------------------------------------------------------------------------

_CASO_PROCEDENTE = {
    "movimentos": [
        {"nome": "Julgamento procedente", "dataHora": "2024-06-01T10:00:00Z"}
    ]
}
_CASO_IMPROCEDENTE = {
    "movimentos": [
        {"nome": "Julgamento improcedente", "dataHora": "2024-05-01T10:00:00Z"}
    ]
}
_CASO_ACORDO = {
    "movimentos": [
        {"nome": "Homologação de acordo", "dataHora": "2024-04-01T10:00:00Z"}
    ]
}
_CASO_SEM_DESFECHO = {
    "movimentos": [{"nome": "Juntada de petição", "dataHora": "2024-03-01T10:00:00Z"}]
}


def _gerar_casos(procedentes: int, improcedentes: int, neutros: int) -> list[dict]:
    """Gera lista de casos com desfechos controlados."""
    casos = []
    casos += [_CASO_PROCEDENTE] * procedentes
    casos += [_CASO_IMPROCEDENTE] * improcedentes
    casos += [_CASO_ACORDO] * neutros
    return casos


# ---------------------------------------------------------------------------
# 1. EstatisticaProcessual — dataclass
# ---------------------------------------------------------------------------


class TestEstatisticaProcessual:
    def test_campos_obrigatorios(self):
        e = EstatisticaProcessual(
            casos_analisados=50,
            casos_com_desfecho=40,
            pct_favoravel=60.0,
            pct_desfavoravel=30.0,
            pct_neutro=10.0,
            confianca="alta",
            tipo_acao=_TIPO_ACAO,
            polo_cliente="autor",
        )
        assert e.casos_analisados == 50
        assert e.pct_favoravel == 60.0
        assert e.pct_desfavoravel == 30.0
        assert e.pct_neutro == 10.0

    def test_disclaimer_padrao_preenchido(self):
        e = EstatisticaProcessual(
            casos_analisados=10,
            casos_com_desfecho=10,
            pct_favoravel=50.0,
            pct_desfavoravel=50.0,
            pct_neutro=0.0,
            confianca="baixa",
            tipo_acao="Ação",
            polo_cliente="autor",
        )
        assert e.disclaimer == DISCLAIMER_ESTATISTICA
        assert "DataJud" in e.disclaimer

    def test_fatores_default_lista_vazia(self):
        e = EstatisticaProcessual(
            casos_analisados=10,
            casos_com_desfecho=10,
            pct_favoravel=50.0,
            pct_desfavoravel=50.0,
            pct_neutro=0.0,
            confianca="baixa",
            tipo_acao="Ação",
            polo_cliente="autor",
        )
        assert e.fatores == []


# ---------------------------------------------------------------------------
# 2. _contar_desfechos — lógica pura (polo autor)
# ---------------------------------------------------------------------------


class TestContarDesfechosAutor:
    def setup_method(self):
        self.preditor = _preditor()

    def test_procedente_e_favoravel_autor(self):
        fav, desfav, neutros = self.preditor._contar_desfechos(
            [_CASO_PROCEDENTE], polo_cliente="autor"
        )
        assert fav == 1
        assert desfav == 0
        assert neutros == 0

    def test_improcedente_e_desfavoravel_autor(self):
        fav, desfav, neutros = self.preditor._contar_desfechos(
            [_CASO_IMPROCEDENTE], polo_cliente="autor"
        )
        assert fav == 0
        assert desfav == 1
        assert neutros == 0

    def test_acordo_e_neutro(self):
        fav, desfav, neutros = self.preditor._contar_desfechos(
            [_CASO_ACORDO], polo_cliente="autor"
        )
        assert neutros == 1

    def test_caso_sem_desfecho_nao_conta(self):
        fav, desfav, neutros = self.preditor._contar_desfechos(
            [_CASO_SEM_DESFECHO], polo_cliente="autor"
        )
        assert fav == 0
        assert desfav == 0
        assert neutros == 0

    def test_multiplos_casos_mixtos(self):
        casos = _gerar_casos(procedentes=6, improcedentes=3, neutros=1)
        fav, desfav, neutros = self.preditor._contar_desfechos(
            casos, polo_cliente="autor"
        )
        assert fav == 6
        assert desfav == 3
        assert neutros == 1

    def test_apenas_movimentos_sem_nome_ignorados(self):
        caso = {"movimentos": [{"dataHora": "2024-01-01T00:00:00Z"}]}  # sem 'nome'
        fav, desfav, neutros = self.preditor._contar_desfechos(
            [caso], polo_cliente="autor"
        )
        assert fav == desfav == neutros == 0


# ---------------------------------------------------------------------------
# 3. _contar_desfechos — polo réu (inversão)
# ---------------------------------------------------------------------------


class TestContarDesfechosReu:
    def setup_method(self):
        self.preditor = _preditor()

    def test_procedente_e_desfavoravel_reu(self):
        fav, desfav, neutros = self.preditor._contar_desfechos(
            [_CASO_PROCEDENTE], polo_cliente="reu"
        )
        assert fav == 0
        assert desfav == 1

    def test_improcedente_e_favoravel_reu(self):
        fav, desfav, neutros = self.preditor._contar_desfechos(
            [_CASO_IMPROCEDENTE], polo_cliente="reu"
        )
        assert fav == 1
        assert desfav == 0

    def test_neutro_igual_para_reu(self):
        _, _, neutros = self.preditor._contar_desfechos(
            [_CASO_ACORDO], polo_cliente="reu"
        )
        assert neutros == 1


# ---------------------------------------------------------------------------
# 4. Ordenação cronológica — usa desfecho mais recente (não o primeiro do array)
# ---------------------------------------------------------------------------


class TestOrdenacaoCronologica:
    """
    Garante que _contar_desfechos processa o movimento mais recente (maior dataHora),
    não o primeiro da lista que pode ser o mais antigo.
    """

    def setup_method(self):
        self.preditor = _preditor()

    def test_usa_movimento_mais_recente_nao_o_primeiro(self):
        # Array com sentença antiga (procedente) e recurso mais recente (improcedente)
        # O sistema deve capturar o resultado do recurso (mais recente)
        caso_com_recurso = {
            "movimentos": [
                # Sentença de 1ª instância: mais antiga, array[0]
                {"nome": "Julgamento procedente", "dataHora": "2022-03-01T10:00:00Z"},
                # Acórdão do recurso: mais recente, array[1]
                {"nome": "Julgamento improcedente", "dataHora": "2023-11-15T10:00:00Z"},
            ]
        }
        fav, desfav, _ = self.preditor._contar_desfechos(
            [caso_com_recurso], polo_cliente="autor"
        )
        # Deve registrar improcedente (resultado do acórdão mais recente)
        assert desfav == 1
        assert fav == 0

    def test_sem_datahora_ainda_funciona(self):
        # Movimento sem dataHora → sort não quebra, só ordena por string vazia
        caso = {
            "movimentos": [
                {"nome": "Procedente"},  # sem dataHora
                {"nome": "Improcedente", "dataHora": "2024-01-01T00:00:00Z"},
            ]
        }
        # Com dataHora → improcedente é mais recente (não vazio > vazio)
        fav, desfav, _ = self.preditor._contar_desfechos([caso], polo_cliente="autor")
        assert desfav == 1
        assert fav == 0


# ---------------------------------------------------------------------------
# 5. _calcular_confianca
# ---------------------------------------------------------------------------


class TestCalcularConfianca:
    def test_alta_para_50_ou_mais(self):
        assert VitoriaPreditor._calcular_confianca(50) == "alta"
        assert VitoriaPreditor._calcular_confianca(100) == "alta"

    def test_media_para_20_a_49(self):
        assert VitoriaPreditor._calcular_confianca(20) == "media"
        assert VitoriaPreditor._calcular_confianca(49) == "media"

    def test_baixa_para_10_a_19(self):
        assert VitoriaPreditor._calcular_confianca(10) == "baixa"
        assert VitoriaPreditor._calcular_confianca(19) == "baixa"


# ---------------------------------------------------------------------------
# 6. _montar_fatores
# ---------------------------------------------------------------------------


class TestMontarFatores:
    def test_primeira_linha_menciona_contagem_e_percentuais(self):
        fatores = VitoriaPreditor._montar_fatores(
            pct_favoravel=65.0,
            pct_desfavoravel=25.0,
            pct_neutro=10.0,
            total_desfechos=20,
            polo_cliente="autor",
            tipo_acao=_TIPO_ACAO,
        )
        assert len(fatores) >= 1
        assert "65.0%" in fatores[0]
        assert "25.0%" in fatores[0]
        assert "10.0%" in fatores[0]
        assert "20" in fatores[0]

    def test_polo_reu_adiciona_nota_perspectiva(self):
        fatores = VitoriaPreditor._montar_fatores(
            pct_favoravel=40.0,
            pct_desfavoravel=50.0,
            pct_neutro=10.0,
            total_desfechos=15,
            polo_cliente="reu",
            tipo_acao="Ação de Cobrança",
        )
        # Deve existir linha mencionando perspectiva para polo réu
        texto_completo = " ".join(fatores).lower()
        assert "réu" in texto_completo or "reu" in texto_completo

    def test_polo_autor_nao_adiciona_nota_perspectiva(self):
        fatores = VitoriaPreditor._montar_fatores(
            pct_favoravel=70.0,
            pct_desfavoravel=20.0,
            pct_neutro=10.0,
            total_desfechos=30,
            polo_cliente="autor",
            tipo_acao="Ação",
        )
        assert len(fatores) == 1  # apenas a linha de percentuais

    def test_tipo_acao_longo_e_truncado(self):
        tipo_longo = "A" * 100
        fatores = VitoriaPreditor._montar_fatores(
            pct_favoravel=50.0,
            pct_desfavoravel=50.0,
            pct_neutro=0.0,
            total_desfechos=10,
            polo_cliente="autor",
            tipo_acao=tipo_longo,
        )
        # fatores[0] não deve conter os 100 caracteres completos
        assert tipo_longo not in fatores[0]


# ---------------------------------------------------------------------------
# 7. buscar_estatistica — happy path
# ---------------------------------------------------------------------------


class TestBuscarEstatisticaHappyPath:
    async def test_retorna_estatistica_com_amostra_suficiente(self):
        casos = _gerar_casos(procedentes=7, improcedentes=2, neutros=1)  # 10 total
        mock = _make_httpx_mock(payload=_hits_payload(casos))

        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_TJSP,
                tipo_acao=_TIPO_ACAO,
                polo_cliente="autor",
            )

        assert resultado is not None
        assert isinstance(resultado, EstatisticaProcessual)
        assert resultado.casos_com_desfecho == 10
        assert resultado.pct_favoravel == 70.0
        assert resultado.pct_desfavoravel == 20.0
        assert resultado.pct_neutro == 10.0

    async def test_percentuais_somam_100(self):
        casos = _gerar_casos(procedentes=5, improcedentes=3, neutros=2)
        mock = _make_httpx_mock(payload=_hits_payload(casos))

        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_TJSP, tipo_acao=_TIPO_ACAO
            )

        assert resultado is not None
        total = (
            resultado.pct_favoravel + resultado.pct_desfavoravel + resultado.pct_neutro
        )
        assert abs(total - 100.0) < 0.2  # tolerância para arredondamento

    async def test_confianca_alta_com_50_desfechos(self):
        casos = _gerar_casos(procedentes=30, improcedentes=15, neutros=5)
        mock = _make_httpx_mock(payload=_hits_payload(casos))

        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_TJSP, tipo_acao=_TIPO_ACAO
            )

        assert resultado is not None
        assert resultado.confianca == "alta"

    async def test_confianca_media_com_20_desfechos(self):
        casos = _gerar_casos(procedentes=12, improcedentes=6, neutros=2)
        mock = _make_httpx_mock(payload=_hits_payload(casos))

        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_TJSP, tipo_acao=_TIPO_ACAO
            )

        assert resultado is not None
        assert resultado.confianca == "media"

    async def test_disclaimer_presente_na_estatistica(self):
        casos = _gerar_casos(procedentes=7, improcedentes=2, neutros=1)
        mock = _make_httpx_mock(payload=_hits_payload(casos))

        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_TJSP, tipo_acao=_TIPO_ACAO
            )

        assert resultado is not None
        assert resultado.disclaimer == DISCLAIMER_ESTATISTICA

    async def test_polo_cliente_preservado_no_resultado(self):
        casos = _gerar_casos(procedentes=7, improcedentes=2, neutros=1)
        mock = _make_httpx_mock(payload=_hits_payload(casos))

        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_TJSP, tipo_acao=_TIPO_ACAO, polo_cliente="reu"
            )

        assert resultado is not None
        assert resultado.polo_cliente == "reu"

    async def test_polo_reu_inverte_percentuais(self):
        # 7 procedentes → desfavoráveis para o réu
        # 3 improcedentes → favoráveis para o réu
        casos = _gerar_casos(procedentes=7, improcedentes=3, neutros=0)
        mock = _make_httpx_mock(payload=_hits_payload(casos))

        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_TJSP, tipo_acao=_TIPO_ACAO, polo_cliente="reu"
            )

        assert resultado is not None
        assert resultado.pct_favoravel == 30.0  # improcedentes → favorável ao réu
        assert resultado.pct_desfavoravel == 70.0  # procedentes → desfavorável ao réu


# ---------------------------------------------------------------------------
# 8. buscar_estatistica — retorna None (amostra insuficiente / sem dados)
# ---------------------------------------------------------------------------


class TestBuscarEstatisticaRetornaNone:
    async def test_tipo_acao_vazio_retorna_none(self):
        mock = _make_httpx_mock()
        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_TJSP, tipo_acao=""
            )
        assert resultado is None
        mock.post.assert_not_called()  # não fez chamada HTTP

    async def test_tipo_acao_none_retorna_none(self):
        mock = _make_httpx_mock()
        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_TJSP, tipo_acao=None
            )
        assert resultado is None

    async def test_cnj_invalido_retorna_none(self):
        mock = _make_httpx_mock()
        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_INVALIDO, tipo_acao=_TIPO_ACAO
            )
        assert resultado is None

    async def test_api_sem_hits_retorna_none(self):
        mock = _make_httpx_mock(payload={"hits": {"hits": []}})
        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_TJSP, tipo_acao=_TIPO_ACAO
            )
        assert resultado is None

    async def test_amostra_insuficiente_retorna_none(self):
        # 9 casos com desfecho → abaixo do MIN_CASOS_COM_DESFECHO (10)
        casos = _gerar_casos(procedentes=6, improcedentes=3, neutros=0)
        assert len(casos) == 9 < MIN_CASOS_COM_DESFECHO

        mock = _make_httpx_mock(payload=_hits_payload(casos))
        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_TJSP, tipo_acao=_TIPO_ACAO
            )
        assert resultado is None

    async def test_casos_sem_desfecho_claro_nao_contam_para_amostra(self):
        # 15 casos mas todos sem desfecho claro (só movimentos neutros como juntadas)
        casos = [_CASO_SEM_DESFECHO] * 15
        mock = _make_httpx_mock(payload=_hits_payload(casos))
        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_TJSP, tipo_acao=_TIPO_ACAO
            )
        assert resultado is None

    async def test_exatamente_no_minimo_retorna_estatistica(self):
        # Exatamente MIN_CASOS_COM_DESFECHO deve passar o gate
        casos = _gerar_casos(
            procedentes=MIN_CASOS_COM_DESFECHO - 2,
            improcedentes=1,
            neutros=1,
        )
        mock = _make_httpx_mock(payload=_hits_payload(casos))
        with _patch_http(mock):
            resultado = await _preditor().buscar_estatistica(
                numero_cnj=_CNJ_TJSP, tipo_acao=_TIPO_ACAO
            )
        assert resultado is not None


# ---------------------------------------------------------------------------
# 9. _buscar_casos_similares — erros de rede / HTTP
# ---------------------------------------------------------------------------


class TestBuscarCasosSimilaresErros:
    """
    Erros de rede/HTTP devem retornar [] silenciosamente,
    sem propagrar exceção para o fluxo principal.
    """

    async def test_timeout_retorna_lista_vazia(self):
        exc = httpx.TimeoutException("timeout")
        mock = _make_httpx_mock(raise_exc=exc)
        with _patch_http(mock):
            resultado = await _preditor()._buscar_casos_similares(
                "api_publica_tjsp", _TIPO_ACAO
            )
        assert resultado == []

    async def test_http_status_error_retorna_lista_vazia(self):
        request_mock = MagicMock()
        response_mock = MagicMock()
        response_mock.status_code = 503
        exc = httpx.HTTPStatusError("503", request=request_mock, response=response_mock)
        mock = _make_httpx_mock(raise_exc=exc)
        with _patch_http(mock):
            resultado = await _preditor()._buscar_casos_similares(
                "api_publica_tjsp", _TIPO_ACAO
            )
        assert resultado == []

    async def test_request_error_rede_retorna_lista_vazia(self):
        exc = httpx.ConnectError("connection refused")
        mock = _make_httpx_mock(raise_exc=exc)
        with _patch_http(mock):
            resultado = await _preditor()._buscar_casos_similares(
                "api_publica_tjsp", _TIPO_ACAO
            )
        assert resultado == []

    async def test_resposta_sem_hits_key_retorna_lista_vazia(self):
        mock = _make_httpx_mock(payload={"total": 0})  # sem chave "hits"
        with _patch_http(mock):
            resultado = await _preditor()._buscar_casos_similares(
                "api_publica_tjsp", _TIPO_ACAO
            )
        assert resultado == []

    async def test_chama_url_correta_com_indice(self):
        mock = _make_httpx_mock()
        with _patch_http(mock):
            await _preditor()._buscar_casos_similares("api_publica_tjsp", _TIPO_ACAO)

        url_chamada = mock.post.call_args[0][0]
        assert "api_publica_tjsp" in url_chamada
        assert "_search" in url_chamada

    async def test_envia_api_key_no_header(self):
        mock = _make_httpx_mock()
        with _patch_http(mock):
            await _preditor()._buscar_casos_similares("api_publica_tjsp", _TIPO_ACAO)

        headers = mock.post.call_args[1]["headers"]
        assert headers.get("Authorization") == "ApiKey test-key"

    async def test_sem_api_key_nao_envia_authorization(self):
        preditor_sem_key = VitoriaPreditor(api_key=None)
        mock = _make_httpx_mock()
        with _patch_http(mock):
            await preditor_sem_key._buscar_casos_similares(
                "api_publica_tjsp", _TIPO_ACAO
            )

        headers = mock.post.call_args[1]["headers"]
        assert "Authorization" not in headers

    async def test_query_usa_fuzzy_no_tipo_acao(self):
        mock = _make_httpx_mock()
        with _patch_http(mock):
            await _preditor()._buscar_casos_similares("api_publica_tjsp", _TIPO_ACAO)

        body = mock.post.call_args[1]["json"]
        # Verifica que a query tem bool/should com match fuzzy
        should_clauses = body["query"]["bool"]["should"]
        campos = [list(c["match"].keys())[0] for c in should_clauses]
        assert "classe.nome" in campos
        assert "assuntos.nome" in campos
