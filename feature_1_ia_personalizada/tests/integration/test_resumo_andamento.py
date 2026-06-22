# feature_1_ia_personalizada/tests/integration/test_resumo_andamento.py
"""
Testes de integração — fluxo completo de resumo contextualizado de andamento (Feature 3).

Cobre o caminho end-to-end dentro de processar_processo_individual():
  andamento detectado
    → DataCleaner.limpar_andamento()
    → ProcessoStateManager.update_state()      (classifica fase, persiste estado)
    → ProcessoStateManager.gerar_contexto_historico()
    → JuridicalTranslator.traduzir_com_contexto()  (não traduzir_andamento)
    → celery_app.send_task("enviar_notificacao_andamento", queue="notificacoes")

Todos os I/Os externos são mockados (DataJud, Claude, banco, Celery/Evolution).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from feature_1_ia_personalizada.workers.monitor_processos import (
    processar_processo_individual,
)

MODULE = "feature_1_ia_personalizada.workers.monitor_processos"


# ---------------------------------------------------------------------------
# Dados de teste
# ---------------------------------------------------------------------------

PROCESSO_COBRANCA = {
    "id": 42,
    "numero": "0001234-12.2023.8.26.0100",
    "data_ultimo_andamento": "2024-01-10",
    "tipo_acao": "Ação de Cobrança",
    "polo_cliente": "autor",
    "tribunal": "TJSP",
}

ANDAMENTO_INSTRUCAO = {
    "texto": "Intimação das partes para audiência de instrução designada para 15/03/2024.",
    "data": "2024-02-01",
}

ANDAMENTO_SENTENCA = {
    "texto": "Sentença proferida pelo juiz julgando procedente o pedido do autor.",
    "data": "2024-03-20",
}


# ---------------------------------------------------------------------------
# Fixture: infraestrutura mockada (cache, banco, Celery)
# ---------------------------------------------------------------------------


@pytest.fixture
def infra():
    """
    Mocks dos I/Os externos que não fazem parte do fluxo Feature 3:
    cache Redis, DataJud, banco (update_ultimo_andamento) e Celery.
    DataCleaner usa passthrough para preservar o texto original.
    """
    mock_cleaner = MagicMock()
    mock_cleaner.limpar_andamento.side_effect = lambda t: t.strip()

    with (
        patch(f"{MODULE}.get_andamentos_sync", return_value=None),
        patch(f"{MODULE}.set_andamentos_sync"),
        patch(f"{MODULE}.DataCleaner", new=mock_cleaner),
        patch(f"{MODULE}.update_ultimo_andamento") as mock_atualizar,
        patch(f"{MODULE}.celery_app") as mock_celery,
    ):
        yield {
            "cleaner": mock_cleaner,
            "atualizar": mock_atualizar,
            "celery": mock_celery,
        }


# ---------------------------------------------------------------------------
# Helpers de setup do fluxo Feature 3
# ---------------------------------------------------------------------------


def _make_state_mock(fase: str = "instrucao", historico: str = "historico") -> MagicMock:
    estado = {
        "fase": fase,
        "ultimos_andamentos": [],
        "proximo_passo_esperado": "Prazo típico: 30 a 90 dias.",
    }
    mock = MagicMock()
    mock.update_state.return_value = estado
    mock.gerar_contexto_historico.return_value = historico
    return mock


def _make_translator_mock(resumo: str = "Resumo contextualizado gerado.") -> MagicMock:
    mock = MagicMock()
    mock.traduzir_com_contexto.return_value = resumo
    return mock


# ---------------------------------------------------------------------------
# Fluxo Feature 3: chamadas obrigatórias por andamento
# ---------------------------------------------------------------------------


class TestFluxoFeature3Chamadas:
    def test_update_state_chamado_com_texto_limpo(self, infra):
        """update_state() recebe o texto limpo pelo DataCleaner."""
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_INSTRUCAO]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        mock_state.update_state.assert_called_once_with(42, ANDAMENTO_INSTRUCAO["texto"].strip())

    def test_gerar_contexto_historico_chamado_apos_update_state(self, infra):
        """gerar_contexto_historico() é chamado com o id do processo."""
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_INSTRUCAO]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        mock_state.gerar_contexto_historico.assert_called_once_with(42)

    def test_traduzir_com_contexto_chamado_nao_traduzir_andamento(self, infra):
        """Usa traduzir_com_contexto(), não traduzir_andamento()."""
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_INSTRUCAO]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        mock_translator.traduzir_com_contexto.assert_called_once()
        mock_translator.traduzir_andamento.assert_not_called()


# ---------------------------------------------------------------------------
# Fluxo Feature 3: dados passados ao tradutor
# ---------------------------------------------------------------------------


class TestFluxoFeature3DadosPassados:
    def test_fase_do_estado_passada_ao_tradutor(self, infra):
        """A fase retornada por update_state é repassada ao traduzir_com_contexto."""
        mock_state = _make_state_mock(fase="julgamento")
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_SENTENCA]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        call_kwargs = mock_translator.traduzir_com_contexto.call_args.kwargs
        assert call_kwargs["fase_atual"] == "julgamento"

    def test_tipo_acao_do_processo_passado_ao_tradutor(self, infra):
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_INSTRUCAO]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        call_kwargs = mock_translator.traduzir_com_contexto.call_args.kwargs
        assert call_kwargs["tipo_acao"] == "Ação de Cobrança"

    def test_polo_cliente_do_processo_passado_ao_tradutor(self, infra):
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_INSTRUCAO]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        call_kwargs = mock_translator.traduzir_com_contexto.call_args.kwargs
        assert call_kwargs["polo_cliente"] == "autor"

    def test_historico_do_state_manager_passado_ao_tradutor(self, infra):
        """O histórico de gerar_contexto_historico() vai para o tradutor."""
        historico_esperado = "1. Petição inicial distribuída\n2. Citação realizada"
        mock_state = _make_state_mock(historico=historico_esperado)
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_INSTRUCAO]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        call_kwargs = mock_translator.traduzir_com_contexto.call_args.kwargs
        assert call_kwargs["historico"] == historico_esperado

    def test_texto_limpo_passado_como_andamento_ao_tradutor(self, infra):
        """O andamento enviado ao tradutor é o texto limpo pelo DataCleaner."""
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_INSTRUCAO]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        call_kwargs = mock_translator.traduzir_com_contexto.call_args.kwargs
        assert call_kwargs["andamento"] == ANDAMENTO_INSTRUCAO["texto"].strip()

    def test_processo_sem_tipo_acao_passa_nao_informado(self, infra):
        """Quando tipo_acao é None, o worker usa 'não informado'."""
        processo_sem_tipo = {**PROCESSO_COBRANCA, "tipo_acao": None}
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_INSTRUCAO]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(processo_sem_tipo)

        call_kwargs = mock_translator.traduzir_com_contexto.call_args.kwargs
        assert call_kwargs["tipo_acao"] == "não informado"

    def test_processo_sem_polo_cliente_usa_autor_como_padrao(self, infra):
        """Quando polo_cliente é None, o worker usa 'autor' como padrão."""
        processo_sem_polo = {**PROCESSO_COBRANCA, "polo_cliente": None}
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_INSTRUCAO]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(processo_sem_polo)

        call_kwargs = mock_translator.traduzir_com_contexto.call_args.kwargs
        assert call_kwargs["polo_cliente"] == "autor"


# ---------------------------------------------------------------------------
# Fluxo Feature 3: envio via Celery (→ Evolution/WhatsApp)
# ---------------------------------------------------------------------------


class TestFluxoFeature3Celery:
    def test_resumo_enviado_via_celery(self, infra):
        """O texto retornado por traduzir_com_contexto() vai nos args da task Celery."""
        resumo_final = "Houve uma intimação. Tudo normal. Seu advogado acompanha."
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock(resumo=resumo_final)

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_INSTRUCAO]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        infra["celery"].send_task.assert_called_once()
        call_kwargs = infra["celery"].send_task.call_args.kwargs
        assert call_kwargs["args"] == [42, resumo_final]

    def test_task_enviada_para_fila_notificacoes(self, infra):
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_INSTRUCAO]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        call_kwargs = infra["celery"].send_task.call_args.kwargs
        assert call_kwargs["queue"] == "notificacoes"

    def test_nome_da_task_celery_correto(self, infra):
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_INSTRUCAO]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        task_name = infra["celery"].send_task.call_args.args[0]
        assert "enviar_notificacao_andamento" in task_name


# ---------------------------------------------------------------------------
# Fluxo Feature 3: múltiplos andamentos
# ---------------------------------------------------------------------------


class TestFluxoFeature3MultiplosAndamentos:
    def test_update_state_chamado_uma_vez_por_andamento(self, infra):
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(
                f"{MODULE}.buscar_andamentos_datajud",
                return_value=[ANDAMENTO_INSTRUCAO, ANDAMENTO_SENTENCA],
            ),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            r = processar_processo_individual(PROCESSO_COBRANCA)

        assert r["novos_andamentos"] == 2
        assert mock_state.update_state.call_count == 2

    def test_gerar_historico_chamado_uma_vez_por_andamento(self, infra):
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(
                f"{MODULE}.buscar_andamentos_datajud",
                return_value=[ANDAMENTO_INSTRUCAO, ANDAMENTO_SENTENCA],
            ),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        assert mock_state.gerar_contexto_historico.call_count == 2

    def test_traduzir_com_contexto_chamado_uma_vez_por_andamento(self, infra):
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(
                f"{MODULE}.buscar_andamentos_datajud",
                return_value=[ANDAMENTO_INSTRUCAO, ANDAMENTO_SENTENCA],
            ),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        assert mock_translator.traduzir_com_contexto.call_count == 2

    def test_celery_send_task_chamado_uma_vez_por_andamento(self, infra):
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(
                f"{MODULE}.buscar_andamentos_datajud",
                return_value=[ANDAMENTO_INSTRUCAO, ANDAMENTO_SENTENCA],
            ),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        assert infra["celery"].send_task.call_count == 2

    def test_cada_andamento_envia_resumo_proprio(self, infra):
        """Cada andamento tem seu resumo independente (diferentes retornos do tradutor)."""
        resumos = ["Resumo da intimação.", "Resumo da sentença."]
        mock_state = _make_state_mock()
        mock_translator = MagicMock()
        mock_translator.traduzir_com_contexto.side_effect = resumos

        with (
            patch(
                f"{MODULE}.buscar_andamentos_datajud",
                return_value=[ANDAMENTO_INSTRUCAO, ANDAMENTO_SENTENCA],
            ),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            processar_processo_individual(PROCESSO_COBRANCA)

        calls = infra["celery"].send_task.call_args_list
        assert calls[0].kwargs["args"][1] == "Resumo da intimação."
        assert calls[1].kwargs["args"][1] == "Resumo da sentença."


# ---------------------------------------------------------------------------
# Resultado da função
# ---------------------------------------------------------------------------


class TestFluxoFeature3Resultado:
    def test_resultado_sucesso_com_novos_andamentos(self, infra):
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_INSTRUCAO]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            r = processar_processo_individual(PROCESSO_COBRANCA)

        assert r["sucesso"] is True
        assert r["novos_andamentos"] == 1
        assert r["id_processo"] == 42
        assert r.get("data_atualizada_para") == ANDAMENTO_INSTRUCAO["data"]

    def test_sem_andamentos_nao_chama_feature_3(self, infra):
        """Quando não há andamentos, os serviços da Feature 3 não devem ser chamados."""
        mock_state = _make_state_mock()
        mock_translator = _make_translator_mock()

        with (
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[]),
            patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state),
            patch(f"{MODULE}.JuridicalTranslator", new=mock_translator),
        ):
            r = processar_processo_individual(PROCESSO_COBRANCA)

        assert r["novos_andamentos"] == 0
        mock_state.update_state.assert_not_called()
        mock_translator.traduzir_com_contexto.assert_not_called()
        infra["celery"].send_task.assert_not_called()
