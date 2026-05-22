# feature_1_ia_personalizada/tests/unit/test_processo_state.py
"""
Testes do ProcessoStateManager e da função _classificar_fase:

  - classificar_fase: palavras-chave mapeiam para a fase correta (sem I/O)
  - get_state: retorna estado inicial quando processo não existe ou estado_atual é nulo
  - update_state: persiste fase e estado; mantém rolling window de 5 andamentos
  - gerar_contexto_historico: enumera mensagens em ordem cronológica; fallback quando vazio
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.ai.processo_state import (
    _PROXIMO_PASSO,
    ProcessoStateManager,
    _classificar_fase,
    _estado_inicial,
)

MODULE = "feature_1_ia_personalizada.services.ai.processo_state"


# ---------------------------------------------------------------------------
# Helper: mock de async_session_factory()
# ---------------------------------------------------------------------------


def _make_factory(session_mock):
    """Cria um mock de async_session_factory compatível com 'async with ... as session'."""

    # session.begin() precisa ser async context manager que chama commit() ao sair.
    # MagicMock passa 'self' como 1º argumento ao chamar dunders, por isso _aexit aceita *args.
    async def _begin_aexit(*args):
        # args = (self_mock, exc_type, exc_val, exc_tb) quando chamado via tipo do MagicMock
        exc_type = args[1] if len(args) >= 2 else args[0] if args else None
        if exc_type is None:
            await session_mock.commit()
        return False

    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = _begin_aexit
    session_mock.begin = MagicMock(return_value=begin_cm)

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=session_mock)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_factory


# ---------------------------------------------------------------------------
# _classificar_fase — função pura, sem I/O
# ---------------------------------------------------------------------------


class TestClassificarFase:
    @pytest.mark.parametrize(
        "texto, fase_esperada",
        [
            # encerrado (maior prioridade na lista)
            ("Processo arquivado por desistência do autor", "encerrado"),
            ("Baixa definitiva após pagamento integral", "encerrado"),
            ("Trânsito em julgado confirmado pelo cartório", "encerrado"),
            # execucao
            ("Início da execução do julgado", "execucao"),
            ("Cumprimento de sentença: penhora online realizada", "execucao"),
            ("Hasta pública designada pelo juiz", "execucao"),
            ("Arresto de bens determinado", "execucao"),
            # recurso
            ("Apelação interposta pelo réu", "recurso"),
            ("Agravo regimental apresentado ao tribunal", "recurso"),
            ("Embargos de declaração acolhidos parcialmente", "recurso"),
            ("Recurso especial distribuído ao STJ", "recurso"),
            # julgamento
            ("Sentença proferida pelo juiz", "julgamento"),
            ("Acórdão publicado pelo TJSP", "julgamento"),
            ("Julgamento procedente do pedido", "julgamento"),
            ("Embargos providos pelo relator", "julgamento"),
            # saneamento
            ("Saneamento do processo realizado em audiência", "saneamento"),
            ("Laudo pericial apresentado ao juízo", "saneamento"),
            ("Audiência de instrução designada para março", "saneamento"),
            ("Perícia contábil determinada", "saneamento"),
            # instrucao
            ("Intimação do advogado do réu para se manifestar", "instrucao"),
            ("Depoimento pessoal das partes agendado", "instrucao"),
            ("Testemunhas arroladas pelo autor", "instrucao"),
            ("Designada audiência para oitiva de testemunha", "instrucao"),
            # conhecimento (fallback para qualquer texto não mapeado)
            ("Processo distribuído ao cartório da 3ª Vara", "conhecimento"),
            ("Petição inicial recebida pelo sistema", "conhecimento"),
            ("", "conhecimento"),
        ],
    )
    def test_classificacao_correta(self, texto, fase_esperada):
        assert _classificar_fase(texto) == fase_esperada

    def test_case_insensitive_julgamento(self):
        assert _classificar_fase("SENTENÇA PROFERIDA PELO JUIZ") == "julgamento"

    def test_case_insensitive_recurso(self):
        assert _classificar_fase("APELAÇÃO INTERPOSTA PELO RÉU") == "recurso"

    def test_encerrado_tem_prioridade_sobre_recurso(self):
        # "recurso" ∈ recurso, mas "arquivado" ∈ encerrado — encerrado vence por ordem
        assert _classificar_fase("recurso arquivado definitivamente") == "encerrado"

    def test_execucao_tem_prioridade_sobre_julgamento(self):
        # "sentença" ∈ julgamento, mas "cumprimento de sentença" ∈ execucao
        assert _classificar_fase("cumprimento de sentença determinado") == "execucao"

    def test_saneamento_tem_prioridade_sobre_instrucao(self):
        # "audiência de instrução" ∈ saneamento — mais específico que "audiência"
        assert _classificar_fase("audiência de instrução marcada") == "saneamento"

    def test_classificar_fase_via_manager_delega_a_funcao(self):
        assert ProcessoStateManager.classificar_fase("penhora online") == "execucao"
        assert ProcessoStateManager.classificar_fase("texto sem keywords") == "conhecimento"


# ---------------------------------------------------------------------------
# _estado_inicial — sem I/O
# ---------------------------------------------------------------------------


class TestEstadoInicial:
    def test_fase_conhecimento(self):
        assert _estado_inicial()["fase"] == "conhecimento"

    def test_lista_andamentos_vazia(self):
        assert _estado_inicial()["ultimos_andamentos"] == []

    def test_proximo_passo_preenchido(self):
        estado = _estado_inicial()
        assert estado["proximo_passo_esperado"] == _PROXIMO_PASSO["conhecimento"]
        assert len(estado["proximo_passo_esperado"]) > 0


# ---------------------------------------------------------------------------
# get_state
# ---------------------------------------------------------------------------


class TestGetState:
    def test_processo_nao_encontrado_retorna_estado_inicial(self):
        session = AsyncMock()
        result = MagicMock()
        result.one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.get_state(99)

        assert estado == _estado_inicial()

    def test_estado_atual_nulo_retorna_estado_inicial(self):
        session = AsyncMock()
        result = MagicMock()
        result.one_or_none.return_value = (None, "conhecimento")
        session.execute = AsyncMock(return_value=result)

        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.get_state(1)

        assert estado == _estado_inicial()

    def test_retorna_estado_existente(self):
        estado_salvo = {
            "fase": "recurso",
            "ultimos_andamentos": ["apelação interposta"],
            "proximo_passo_esperado": _PROXIMO_PASSO["recurso"],
        }
        session = AsyncMock()
        result = MagicMock()
        result.one_or_none.return_value = (estado_salvo, "recurso")
        session.execute = AsyncMock(return_value=result)

        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.get_state(1)

        assert estado == estado_salvo
        assert estado["fase"] == "recurso"

    def test_retorna_estado_com_todos_os_campos(self):
        estado_salvo = {
            "fase": "execucao",
            "ultimos_andamentos": ["penhora", "hasta"],
            "proximo_passo_esperado": _PROXIMO_PASSO["execucao"],
        }
        session = AsyncMock()
        result = MagicMock()
        result.one_or_none.return_value = (estado_salvo, "execucao")
        session.execute = AsyncMock(return_value=result)

        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.get_state(1)

        assert "fase" in estado
        assert "ultimos_andamentos" in estado
        assert "proximo_passo_esperado" in estado


# ---------------------------------------------------------------------------
# update_state
# ---------------------------------------------------------------------------


class TestUpdateState:
    def _build_session(self, estado_atual=None):
        """Monta session mock para update_state: SELECT + UPDATE + commit."""
        session = AsyncMock()
        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = estado_atual
        update_result = MagicMock()
        session.execute = AsyncMock(side_effect=[select_result, update_result])
        session.commit = AsyncMock()
        return session

    def test_classifica_fase_julgamento(self):
        session = self._build_session()
        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.update_state(1, "sentença proferida pelo juiz")
        assert estado["fase"] == "julgamento"

    def test_classifica_fase_recurso(self):
        session = self._build_session()
        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.update_state(1, "apelação interposta pelo réu")
        assert estado["fase"] == "recurso"

    def test_classifica_fase_execucao(self):
        session = self._build_session()
        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.update_state(1, "penhora online realizada")
        assert estado["fase"] == "execucao"

    def test_classifica_fase_encerrado(self):
        session = self._build_session()
        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.update_state(1, "processo arquivado definitivamente")
        assert estado["fase"] == "encerrado"

    def test_estado_nulo_no_banco_usa_estado_inicial(self):
        session = self._build_session(estado_atual=None)
        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.update_state(1, "despacho ordinatório")
        assert "despacho ordinatório" in estado["ultimos_andamentos"]

    def test_mantem_andamentos_existentes(self):
        estado_existente = {
            "fase": "instrucao",
            "ultimos_andamentos": ["andamento antigo 1", "andamento antigo 2"],
            "proximo_passo_esperado": "",
        }
        session = self._build_session(estado_atual=estado_existente)
        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.update_state(1, "novo andamento")
        assert "andamento antigo 1" in estado["ultimos_andamentos"]
        assert "andamento antigo 2" in estado["ultimos_andamentos"]
        assert "novo andamento" in estado["ultimos_andamentos"]

    def test_rolling_window_maximo_5(self):
        estado_com_5 = {
            "fase": "instrucao",
            "ultimos_andamentos": ["a1", "a2", "a3", "a4", "a5"],
            "proximo_passo_esperado": "",
        }
        session = self._build_session(estado_atual=estado_com_5)
        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.update_state(1, "a6")
        assert len(estado["ultimos_andamentos"]) == 5
        assert "a1" not in estado["ultimos_andamentos"]
        assert "a6" in estado["ultimos_andamentos"]

    def test_persiste_via_commit(self):
        session = self._build_session()
        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            ProcessoStateManager.update_state(1, "qualquer andamento")
        session.commit.assert_called_once()

    def test_proximo_passo_correspondente_a_fase(self):
        session = self._build_session()
        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.update_state(1, "penhora online realizada")
        assert estado["proximo_passo_esperado"] == _PROXIMO_PASSO["execucao"]

    def test_retorna_dict_com_campos_obrigatorios(self):
        session = self._build_session()
        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.update_state(1, "despacho")
        assert isinstance(estado, dict)
        assert "fase" in estado
        assert "ultimos_andamentos" in estado
        assert "proximo_passo_esperado" in estado

    def test_novo_andamento_adicionado_ao_fim_da_lista(self):
        estado_existente = {
            "fase": "instrucao",
            "ultimos_andamentos": ["primeiro"],
            "proximo_passo_esperado": "",
        }
        session = self._build_session(estado_atual=estado_existente)
        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            estado = ProcessoStateManager.update_state(1, "segundo")
        assert estado["ultimos_andamentos"][-1] == "segundo"


# ---------------------------------------------------------------------------
# gerar_contexto_historico
# ---------------------------------------------------------------------------


class TestGerarContextoHistorico:
    def test_sem_interacoes_retorna_mensagem_padrao(self):
        session = AsyncMock()
        result = MagicMock()
        result.all.return_value = []
        session.execute = AsyncMock(return_value=result)

        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            ctx = ProcessoStateManager.gerar_contexto_historico(1)

        assert ctx == "Nenhum andamento anterior registrado."

    def test_enumera_mensagens_em_ordem_cronologica(self):
        # Query retorna DESC (mais recente primeiro); código reverte com reversed()
        mensagens_desc = ["mais recente", "do meio", "mais antigo"]
        session = AsyncMock()
        result = MagicMock()
        result.all.return_value = [(m,) for m in mensagens_desc]
        session.execute = AsyncMock(return_value=result)

        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            ctx = ProcessoStateManager.gerar_contexto_historico(1)

        linhas = ctx.split("\n")
        assert "mais antigo" in linhas[0]
        assert "mais recente" in linhas[-1]

    def test_formato_enumerado_com_numeros(self):
        session = AsyncMock()
        result = MagicMock()
        result.all.return_value = [("resumo A",), ("resumo B",)]
        session.execute = AsyncMock(return_value=result)

        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            ctx = ProcessoStateManager.gerar_contexto_historico(1)

        assert "1. " in ctx
        assert "2. " in ctx

    def test_conteudo_das_mensagens_preservado(self):
        session = AsyncMock()
        result = MagicMock()
        result.all.return_value = [("Sentença de procedência proferida.",)]
        session.execute = AsyncMock(return_value=result)

        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            ctx = ProcessoStateManager.gerar_contexto_historico(1)

        assert "Sentença de procedência proferida." in ctx

    def test_n_ultimos_padrao_cinco(self):
        """Padrão n_ultimos=5 não lança erro e chama execute uma vez."""
        session = AsyncMock()
        result = MagicMock()
        result.all.return_value = []
        session.execute = AsyncMock(return_value=result)

        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            ProcessoStateManager.gerar_contexto_historico(1)

        session.execute.assert_called_once()

    def test_n_ultimos_customizado(self):
        """n_ultimos customizado não lança erro."""
        session = AsyncMock()
        result = MagicMock()
        result.all.return_value = []
        session.execute = AsyncMock(return_value=result)

        with patch(f"{MODULE}.async_session_factory", _make_factory(session)):
            ctx = ProcessoStateManager.gerar_contexto_historico(1, n_ultimos=3)

        session.execute.assert_called_once()
        assert ctx == "Nenhum andamento anterior registrado."
