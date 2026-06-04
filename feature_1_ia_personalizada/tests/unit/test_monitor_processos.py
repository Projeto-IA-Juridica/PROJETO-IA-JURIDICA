# feature_1_ia_personalizada/tests/unit/test_monitor_processos.py
"""
Testes do monitor de processos: funções puras (extrair_valor, converter_para_iso,
extrair_texto_e_data), wrappers de API, processamento individual e tasks Celery.

NOTA sobre imports comentados:
  DataCleaner, DataJudClient, JusbrasilClient e JuridicalTranslator estão com
  imports comentados no módulo (aguardando Fase 3). Os testes injetam mocks no
  namespace via patch(..., create=True) para exercitar o fluxo sem alteração
  no código-fonte.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from feature_1_ia_personalizada.workers.monitor_processos import (
    INTERVALO_ENTRE_REQUISICOES_SEGUNDOS,
    TAMANHO_LOTE,
    TEMPO_MAXIMO_PROCESSO_SEGUNDOS,
    buscar_andamentos_datajud,
    converter_para_iso,
    extrair_texto_e_data_do_andamento,
    extrair_valor,
    monitorar_processo_individual,
    monitorar_processos,
    processar_processo_individual,
)

MODULE = "feature_1_ia_personalizada.workers.monitor_processos"

# ---------------------------------------------------------------------------
# Dados de teste
# ---------------------------------------------------------------------------

PROCESSO = {
    "id": 1,
    "numero": "0001234-12.2023.8.26.0100",
    "data_ultimo_andamento": "2024-01-10",
}

ANDAMENTO_A = {"texto": "Despacho ordinatório", "data": "2024-01-20"}
ANDAMENTO_B = {"texto": "Conclusão ao juiz", "data": "2024-01-25"}


# ---------------------------------------------------------------------------
# Fixture: dependências de Fase 3
#
# Injeta no namespace do módulo os imports comentados:
#   JusbrasilClient, DataJudClient, DataCleaner, JuridicalTranslator
# usando patch(..., create=True) — sem alterar o código de produção.
# ---------------------------------------------------------------------------


@pytest.fixture
def fase3():
    mock_cleaner = MagicMock()
    mock_cleaner.limpar_andamento.side_effect = lambda t: f"[limpo] {t}"

    mock_translator = MagicMock()
    mock_translator.traduzir_andamento.side_effect = lambda t: f"[tr] {t}"
    mock_translator.traduzir_com_contexto = MagicMock(
        side_effect=lambda **kw: f"[tr] {kw.get('andamento', '')}"
    )

    mock_state_manager = MagicMock()
    mock_state_manager.update_state.return_value = {"fase": "conhecimento", "andamentos": []}
    mock_state_manager.gerar_contexto_historico.return_value = ""

    with (
        patch(f"{MODULE}.DataJudClient", create=True),
        patch(f"{MODULE}.DataCleaner", new=mock_cleaner, create=True),
        patch(f"{MODULE}.JuridicalTranslator", new=mock_translator, create=True),
        patch(f"{MODULE}.ProcessoStateManager", return_value=mock_state_manager),
        # Nome correto da função importada de worker_queries
        patch(f"{MODULE}.update_ultimo_andamento") as mock_atualizar,
        # Cache mockado como miss por padrão — isola testes do Redis real
        patch(f"{MODULE}.get_andamentos_sync", return_value=None) as mock_get_cache,
        patch(f"{MODULE}.set_andamentos_sync") as mock_set_cache,
        patch(f"{MODULE}.celery_app") as mock_celery,
    ):
        yield {
            "cleaner": mock_cleaner,
            "translator": mock_translator,
            "state_manager": mock_state_manager,
            "atualizar": mock_atualizar,
            "get_cache": mock_get_cache,
            "set_cache": mock_set_cache,
            "celery": mock_celery,
        }


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------


class TestConstantes:
    def test_tamanho_lote(self):
        assert TAMANHO_LOTE == 10

    def test_intervalo_entre_requisicoes(self):
        assert INTERVALO_ENTRE_REQUISICOES_SEGUNDOS == 0.4

    def test_tempo_maximo_processo(self):
        assert TEMPO_MAXIMO_PROCESSO_SEGUNDOS == 30


# ---------------------------------------------------------------------------
# extrair_valor
# ---------------------------------------------------------------------------


class TestExtrairValor:
    def test_dict_chave_presente(self):
        assert extrair_valor({"a": 1}, "a") == 1

    def test_dict_chave_ausente_retorna_none_padrao(self):
        assert extrair_valor({"a": 1}, "b") is None

    def test_dict_chave_ausente_retorna_padrao_customizado(self):
        assert extrair_valor({}, "x", "fallback") == "fallback"

    def test_objeto_attr_presente(self):
        class Obj:
            texto = "conteudo"

        assert extrair_valor(Obj(), "texto") == "conteudo"

    def test_objeto_attr_ausente_retorna_none(self):
        class Obj:
            pass

        assert extrair_valor(Obj(), "inexistente") is None

    def test_objeto_attr_ausente_retorna_padrao_customizado(self):
        class Obj:
            pass

        assert extrair_valor(Obj(), "inexistente", "default") == "default"


# ---------------------------------------------------------------------------
# converter_para_iso
# ---------------------------------------------------------------------------


class TestConverterParaIso:
    def test_none_retorna_none(self):
        assert converter_para_iso(None) is None

    def test_datetime_retorna_isoformat(self):
        dt = datetime(2024, 3, 15, 10, 30, 0)
        assert converter_para_iso(dt) == dt.isoformat()

    def test_string_retorna_string(self):
        assert converter_para_iso("2024-03-15") == "2024-03-15"

    def test_outro_tipo_retorna_str_do_valor(self):
        assert converter_para_iso(20240315) == "20240315"


# ---------------------------------------------------------------------------
# extrair_texto_e_data_do_andamento
# ---------------------------------------------------------------------------


class TestExtrairTextoEData:
    def test_dict_com_texto_e_data_string(self):
        texto, data = extrair_texto_e_data_do_andamento({"texto": "Despacho", "data": "2024-01-20"})
        assert texto == "Despacho"
        assert data == "2024-01-20"

    def test_dict_com_data_datetime(self):
        dt = datetime(2024, 1, 20, 12, 0, 0)
        _, data = extrair_texto_e_data_do_andamento({"texto": "x", "data": dt})
        assert data == dt.isoformat()

    def test_dict_sem_texto_retorna_string_vazia(self):
        texto, _ = extrair_texto_e_data_do_andamento({"data": "2024-01-01"})
        assert texto == ""

    def test_dict_sem_data_retorna_none(self):
        _, data = extrair_texto_e_data_do_andamento({"texto": "x"})
        assert data is None

    def test_objeto_com_attrs(self):
        class Andamento:
            texto = "Sentença"
            data = "2024-06-01"

        texto, data = extrair_texto_e_data_do_andamento(Andamento())
        assert texto == "Sentença"
        assert data == "2024-06-01"


# ---------------------------------------------------------------------------
# buscar_andamentos_jusbrasil / buscar_andamentos_datajud
# ---------------------------------------------------------------------------


class TestBuscarAndamentos:
    def test_datajud_delega_ao_cliente(self):
        mock = MagicMock()
        mock.buscar_novos_andamentos.return_value = [ANDAMENTO_B]
        resultado = buscar_andamentos_datajud("0001234", "2024-01-01", mock)
        mock.buscar_novos_andamentos.assert_called_once_with("0001234", "2024-01-01")
        assert resultado == [ANDAMENTO_B]

    def test_datajud_propaga_excecao(self):
        mock = MagicMock()
        mock.buscar_novos_andamentos.side_effect = TimeoutError("datajud down")
        with pytest.raises(TimeoutError):
            buscar_andamentos_datajud("0001234", None, mock)


# ---------------------------------------------------------------------------
# processar_processo_individual
# ---------------------------------------------------------------------------


class TestProcessarProcessoIndividual:
    def test_sem_andamentos_retorna_sucesso_com_zero(self, fase3):
        with patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[]):
            r = processar_processo_individual(PROCESSO)
        assert r["sucesso"] is True
        assert r["novos_andamentos"] == 0
        assert r["id_processo"] == 1
        assert r["fonte"] == "datajud"

    def test_com_andamentos_conta_corretamente(self, fase3):
        with patch(
            f"{MODULE}.buscar_andamentos_datajud",
            return_value=[ANDAMENTO_A, ANDAMENTO_B],
        ):
            r = processar_processo_individual(PROCESSO)
        assert r["novos_andamentos"] == 2
        assert r["sucesso"] is True

    def test_envia_task_celery_por_andamento(self, fase3):
        with patch(
            f"{MODULE}.buscar_andamentos_datajud",
            return_value=[ANDAMENTO_A, ANDAMENTO_B],
        ):
            processar_processo_individual(PROCESSO)
        assert fase3["celery"].send_task.call_count == 2

    def test_task_celery_enviada_para_fila_correta(self, fase3):
        with patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_A]):
            processar_processo_individual(PROCESSO)
        call_kwargs = fase3["celery"].send_task.call_args
        assert call_kwargs.kwargs["queue"] == "notificacoes"

    def test_atualiza_banco_com_ultimo_andamento(self, fase3):
        with patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_A]):
            processar_processo_individual(PROCESSO)
        fase3["atualizar"].assert_called_once()
        args = fase3["atualizar"].call_args.args
        assert args[0] == 1  # id_processo
        assert args[2] == "2024-01-20"  # data do andamento

    def test_andamento_sem_data_nao_atualiza_banco(self, fase3):
        andamento_sem_data = {"texto": "Decisão sem data"}
        with patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[andamento_sem_data]):
            processar_processo_individual(PROCESSO)
        fase3["atualizar"].assert_not_called()

    def test_data_atualizada_presente_no_resultado(self, fase3):
        with patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_A]):
            r = processar_processo_individual(PROCESSO)
        assert r.get("data_atualizada_para") == "2024-01-20"

    def test_datajud_falha_propaga_excecao(self, fase3):
        with (
            patch(
                f"{MODULE}.buscar_andamentos_datajud",
                side_effect=ConnectionError("down"),
            ),
            pytest.raises(ConnectionError),
        ):
            processar_processo_individual(PROCESSO)


# ---------------------------------------------------------------------------
# monitorar_processos  (Celery task)
# ---------------------------------------------------------------------------


class TestMonitorarProcessos:
    def test_lista_vazia_retorna_sucesso(self):
        with (
            patch(f"{MODULE}.query_processos_monitorados", return_value=[]),
            patch(f"{MODULE}.time.sleep"),
        ):
            r = monitorar_processos()
        assert r["sucesso"] is True
        assert r["total_processados"] == 0
        assert r["total_erros"] == 0
        assert r["resumo_primeiros_20"] == []

    def test_erro_no_banco_retorna_sucesso_false(self):
        with patch(f"{MODULE}.query_processos_monitorados", side_effect=RuntimeError("DB down")):
            r = monitorar_processos()
        assert r["sucesso"] is False
        assert "DB down" in r["erro"]

    def test_processa_todos_com_sucesso(self, fase3):
        processos = [PROCESSO, {**PROCESSO, "id": 2}]
        mock_ok = {
            "id_processo": 1,
            "sucesso": True,
            "novos_andamentos": 0,
            "fonte": "datajud",
        }
        with (
            patch(f"{MODULE}.query_processos_monitorados", return_value=processos),
            patch(f"{MODULE}.processar_processo_individual", return_value=mock_ok),
            patch(f"{MODULE}.time.sleep"),
        ):
            r = monitorar_processos()
        assert r["total_processados"] == 2
        assert r["total_erros"] == 0
        assert r["sucesso"] is True

    def test_soft_time_limit_contado_como_erro(self, fase3):
        with (
            patch(f"{MODULE}.query_processos_monitorados", return_value=[PROCESSO]),
            patch(
                f"{MODULE}.processar_processo_individual",
                side_effect=SoftTimeLimitExceeded(),
            ),
            patch(f"{MODULE}.time.sleep"),
        ):
            r = monitorar_processos()
        assert r["total_erros"] == 1
        assert r["total_processados"] == 0
        entry = r["resumo_primeiros_20"][0]
        assert entry["sucesso"] is False
        assert entry["erro"] == "tempo_maximo_excedido_30s"

    def test_excecao_generica_contada_como_erro(self, fase3):
        with (
            patch(f"{MODULE}.query_processos_monitorados", return_value=[PROCESSO]),
            patch(
                f"{MODULE}.processar_processo_individual",
                side_effect=ValueError("bad data"),
            ),
            patch(f"{MODULE}.time.sleep"),
        ):
            r = monitorar_processos()
        assert r["total_erros"] == 1
        entry = r["resumo_primeiros_20"][0]
        assert entry["sucesso"] is False
        assert "bad data" in entry["erro"]

    def test_resumo_truncado_em_20(self, fase3):
        processos = [{**PROCESSO, "id": i} for i in range(25)]
        mock_ok = {
            "id_processo": 0,
            "sucesso": True,
            "novos_andamentos": 0,
            "fonte": "datajud",
        }
        with (
            patch(f"{MODULE}.query_processos_monitorados", return_value=processos),
            patch(f"{MODULE}.processar_processo_individual", return_value=mock_ok),
            patch(f"{MODULE}.time.sleep"),
        ):
            r = monitorar_processos()
        assert r["total_processados"] == 25
        assert len(r["resumo_primeiros_20"]) == 20

    def test_sleep_chamado_uma_vez_por_processo(self, fase3):
        processos = [PROCESSO, {**PROCESSO, "id": 2}]
        mock_ok = {
            "id_processo": 1,
            "sucesso": True,
            "novos_andamentos": 0,
            "fonte": "datajud",
        }
        with (
            patch(f"{MODULE}.query_processos_monitorados", return_value=processos),
            patch(f"{MODULE}.processar_processo_individual", return_value=mock_ok),
            patch(f"{MODULE}.time.sleep") as mock_sleep,
        ):
            monitorar_processos()
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(INTERVALO_ENTRE_REQUISICOES_SEGUNDOS)

    def test_mixed_success_and_errors(self, fase3):
        """2 processos OK + 1 SoftTimeLimitExceeded + 1 ValueError."""
        mock_ok = {
            "id_processo": 0,
            "sucesso": True,
            "novos_andamentos": 0,
            "fonte": "datajud",
        }
        processos = [{**PROCESSO, "id": i} for i in range(4)]
        side_effects = [mock_ok, SoftTimeLimitExceeded(), mock_ok, ValueError("err")]
        with (
            patch(f"{MODULE}.query_processos_monitorados", return_value=processos),
            patch(f"{MODULE}.processar_processo_individual", side_effect=side_effects),
            patch(f"{MODULE}.time.sleep"),
        ):
            r = monitorar_processos()
        assert r["total_processados"] == 2
        assert r["total_erros"] == 2


# ---------------------------------------------------------------------------
# monitorar_processo_individual  (Celery task)
# ---------------------------------------------------------------------------


class TestMonitorarProcessoIndividual:
    def test_processo_nao_encontrado(self):
        with patch(f"{MODULE}.query_processo_por_id", return_value=None):
            r = monitorar_processo_individual(99)
        assert r["sucesso"] is False
        assert r["erro"] == "processo_nao_encontrado"
        assert r["id_processo"] == 99

    def test_processo_encontrado_retorna_sucesso(self, fase3):
        mock_ok = {
            "id_processo": 1,
            "sucesso": True,
            "novos_andamentos": 0,
            "fonte": "datajud",
        }
        with (
            patch(f"{MODULE}.query_processo_por_id", return_value=PROCESSO),
            patch(f"{MODULE}.processar_processo_individual", return_value=mock_ok),
        ):
            r = monitorar_processo_individual(1)
        assert r["sucesso"] is True

    def test_soft_time_limit_retorna_erro_estruturado(self):
        with (
            patch(f"{MODULE}.query_processo_por_id", return_value=PROCESSO),
            patch(
                f"{MODULE}.processar_processo_individual",
                side_effect=SoftTimeLimitExceeded(),
            ),
        ):
            r = monitorar_processo_individual(1)
        assert r["sucesso"] is False
        assert r["erro"] == "tempo_maximo_excedido_30s"
        assert r["id_processo"] == 1

    def test_excecao_generica_retorna_erro_estruturado(self):
        with (
            patch(f"{MODULE}.query_processo_por_id", return_value=PROCESSO),
            patch(
                f"{MODULE}.processar_processo_individual",
                side_effect=RuntimeError("falha inesperada"),
            ),
        ):
            r = monitorar_processo_individual(1)
        assert r["sucesso"] is False
        assert "falha inesperada" in r["erro"]
        assert r["id_processo"] == 1


# ---------------------------------------------------------------------------
# processar_processo_individual — fluxo cache-aside
# ---------------------------------------------------------------------------


class TestCacheAside:
    def test_cache_hit_nao_chama_api(self, fase3):
        """Quando cache tem dados, não deve chamar Datajud."""
        with (
            patch(f"{MODULE}.get_andamentos_sync", return_value=[ANDAMENTO_A]),
            patch(f"{MODULE}.buscar_andamentos_datajud") as mock_jb,
        ):
            r = processar_processo_individual(PROCESSO)
        mock_jb.assert_not_called()
        assert r["fonte"] == "cache"
        assert r["novos_andamentos"] == 1

    def test_cache_miss_chama_api_e_salva(self, fase3):
        """Quando cache miss, deve chamar Datajud e salvar resultado no Redis."""
        with (
            patch(f"{MODULE}.get_andamentos_sync", return_value=None),
            patch(f"{MODULE}.set_andamentos_sync") as mock_set,
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[ANDAMENTO_A]),
        ):
            processar_processo_individual(PROCESSO)
        mock_set.assert_called_once()

    def test_cache_hit_lista_vazia_nao_chama_api(self, fase3):
        """Cache hit com lista vazia é um hit válido — não deve chamar a API."""
        with (
            patch(f"{MODULE}.get_andamentos_sync", return_value=[]),
            patch(f"{MODULE}.buscar_andamentos_datajud") as mock_jb,
        ):
            r = processar_processo_individual(PROCESSO)
        mock_jb.assert_not_called()
        assert r["novos_andamentos"] == 0
        assert r["fonte"] == "cache"

    def test_cache_miss_api_vazia_salva_lista_vazia(self, fase3):
        """Cache miss + API retorna [] → cacheia a lista vazia para evitar nova chamada."""
        with (
            patch(f"{MODULE}.get_andamentos_sync", return_value=None),
            patch(f"{MODULE}.set_andamentos_sync") as mock_set,
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=[]),
        ):
            r = processar_processo_individual(PROCESSO)
        # Lista vazia também é cacheada (is not None)
        mock_set.assert_called_once()
        assert r["novos_andamentos"] == 0

    def test_cache_hit_filtra_andamentos_ja_vistos(self, fase3):
        """Cache do orchestrator salva TODOS os movimentos sem filtro.

        O worker deve aplicar filtro de data ao ler do cache para não re-notificar
        andamentos anteriores à data_ultimo_andamento do banco (falso positivo).
        """
        # Cache contém 3 movimentos: 2 antigos (já vistos) + 1 novo
        processo = {**PROCESSO, "data_ultimo_andamento": "2024-01-20T00:00:00+00:00"}
        cache_com_todos = [
            {"texto": "Antigo 1", "data": "2023-06-01T08:00:00.000Z"},
            {"texto": "Antigo 2", "data": "2024-01-20T00:00:00.000Z"},  # igual à ref → excluído
            {"texto": "Novo", "data": "2024-03-15T10:00:00.000Z"},
        ]
        with (
            patch(f"{MODULE}.get_andamentos_sync", return_value=cache_com_todos),
            patch(f"{MODULE}.set_andamentos_sync"),
            patch(f"{MODULE}.buscar_andamentos_datajud") as mock_api,
            patch(f"{MODULE}.celery_app") as mock_celery,
            patch(f"{MODULE}.update_ultimo_andamento"),
        ):
            r = processar_processo_individual(processo)

        # API DataJud NÃO deve ser chamada (cache hit)
        mock_api.assert_not_called()
        # Apenas 1 andamento novo deve gerar notificação
        assert r["novos_andamentos"] == 1
        assert mock_celery.send_task.call_count == 1

    def test_ultima_data_salva_e_a_mais_recente(self, fase3):
        """data_ultimo_andamento no banco deve ser a data MAIS RECENTE dos andamentos
        processados, mesmo que a ordem no array não seja a cronológica.

        Bug anterior: sobrescrevia a cada iteração → salvava a data do ÚLTIMO elemento
        (mais antigo), causando re-processamento no próximo ciclo.
        """
        andamentos_fora_de_ordem = [
            {"texto": "Conclusão", "data": "2024-01-25T12:00:00.000Z"},  # mais novo
            {"texto": "Distribuído", "data": "2024-01-10T09:00:00.000Z"},  # mais antigo
            {"texto": "Despacho", "data": "2024-01-20T08:00:00.000Z"},  # intermediário
        ]
        with (
            patch(f"{MODULE}.get_andamentos_sync", return_value=None),
            patch(f"{MODULE}.set_andamentos_sync"),
            patch(f"{MODULE}.buscar_andamentos_datajud", return_value=andamentos_fora_de_ordem),
            patch(f"{MODULE}.celery_app"),
            patch(f"{MODULE}.update_ultimo_andamento") as mock_update,
        ):
            processar_processo_individual(PROCESSO)

        mock_update.assert_called_once()
        _id, _texto, data_salva = mock_update.call_args.args
        assert (
            data_salva == "2024-01-25T12:00:00.000Z"
        ), f"Esperado data mais recente, recebido: {data_salva}"
