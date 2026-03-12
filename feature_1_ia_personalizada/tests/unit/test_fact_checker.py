# feature_1_ia_personalizada/tests/unit/test_fact_checker.py
"""
Testes do FactChecker: verificação de status, prazo, filtro de linguagem e log em metadata_json.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from feature_1_ia_personalizada.services.ai.fact_checker import FactChecker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIMESTAMP_FIXO = datetime(2025, 6, 1, 12, 0, 0)


def _utcnow_fixo() -> datetime:
    return _TIMESTAMP_FIXO


def _make_checker(dados_retornados: dict[str, Any]) -> FactChecker:
    async def buscar(processo_id: str) -> dict[str, Any]:
        return dados_retornados

    return FactChecker(buscar_dados_processo=buscar, utcnow=_utcnow_fixo)


def _interacao(metadata_json=None) -> SimpleNamespace:
    return SimpleNamespace(metadata_json=metadata_json)


# ---------------------------------------------------------------------------
# verificar_status_processo
# ---------------------------------------------------------------------------


class TestVerificarStatusProcesso:
    async def test_tudo_correto_verificado_true(self):
        checker = _make_checker(
            {
                "numero_cnj": "1234567-89.2023.8.26.0100",
                "tribunal": "TJSP",
                "ultimo_andamento": "Sentença prolatada",
            }
        )
        interacao = _interacao()
        resultado = await checker.verificar_status_processo(
            "proc-1",
            "O processo 1234567-89.2023.8.26.0100 está no TJSP. Sentença prolatada foi o último andamento.",
            interacao,
        )

        assert resultado["verificado"] is True
        assert resultado["correcoes"] == []
        # Sem correção → metadata_json não deve ser alterado
        assert interacao.metadata_json is None

    async def test_numero_cnj_errado_gera_correcao(self):
        checker = _make_checker({"numero_cnj": "1234567-89.2023.8.26.0100"})
        interacao = _interacao()
        resultado = await checker.verificar_status_processo(
            "proc-1",
            "O processo está em andamento.",  # número CNJ ausente
            interacao,
        )

        assert resultado["verificado"] is False
        assert any("CNJ" in c for c in resultado["correcoes"])

    async def test_tribunal_errado_gera_correcao(self):
        checker = _make_checker({"tribunal": "TJSP"})
        interacao = _interacao()
        resultado = await checker.verificar_status_processo(
            "proc-1",
            "O processo está no TJRJ.",  # tribunal diferente
            interacao,
        )

        assert resultado["verificado"] is False
        assert any("Tribunal" in c for c in resultado["correcoes"])

    async def test_ultimo_andamento_errado_gera_correcao(self):
        checker = _make_checker({"ultimo_andamento": "Audiência agendada"})
        interacao = _interacao()
        resultado = await checker.verificar_status_processo(
            "proc-1",
            "Não há novidades no processo.",
            interacao,
        )

        assert resultado["verificado"] is False
        assert any("andamento" in c.lower() for c in resultado["correcoes"])

    async def test_multiplos_campos_errados_multiplas_correcoes(self):
        checker = _make_checker(
            {
                "numero_cnj": "0001-XX",
                "tribunal": "TJMG",
                "ultimo_andamento": "Recurso interposto",
            }
        )
        interacao = _interacao()
        resultado = await checker.verificar_status_processo("proc-1", "Nada confere.", interacao)

        assert resultado["verificado"] is False
        assert len(resultado["correcoes"]) == 3

    async def test_dados_reais_vazios_nao_geram_correcao(self):
        """Se o banco não tem dados, não há o que verificar — não pode reprovar."""
        checker = _make_checker({})
        interacao = _interacao()
        resultado = await checker.verificar_status_processo("proc-1", "qualquer coisa", interacao)

        assert resultado["verificado"] is True
        assert resultado["correcoes"] == []

    async def test_correcao_loga_metadata_json(self):
        checker = _make_checker({"numero_cnj": "0001-XX"})
        interacao = _interacao()
        await checker.verificar_status_processo("proc-1", "afirmação errada", interacao)

        meta = interacao.metadata_json
        assert meta is not None
        assert meta["fact_check_corrigido"] is True
        assert len(meta["auditoria_fact_checker"]) == 1
        assert meta["auditoria_fact_checker"][0]["evento"] == "fact_checker_status_processo"

    async def test_dados_reais_resumo_retornado(self):
        checker = _make_checker(
            {
                "numero_cnj": "0001-XX",
                "tribunal": "TJSP",
                "ultimo_andamento": "Despacho",
            }
        )
        interacao = _interacao()
        resultado = await checker.verificar_status_processo("proc-1", "nada aqui", interacao)

        resumo = resultado["dados_reais_resumo"]
        assert resumo["numero_cnj"] == "0001-XX"
        assert resumo["tribunal"] == "TJSP"
        assert resumo["ultimo_andamento"] == "Despacho"

    async def test_campo_none_nos_dados_reais_ignorado(self):
        """Campo None no banco não gera correção — não há valor para comparar."""
        checker = _make_checker({"numero_cnj": None, "tribunal": None})
        interacao = _interacao()
        resultado = await checker.verificar_status_processo("proc-1", "sem info", interacao)

        assert resultado["verificado"] is True

    async def test_campo_string_vazia_ou_espacos_nos_dados_reais_ignorado(self):
        """String vazia ou só espaços no banco também não geram correção após strip."""
        checker = _make_checker({"numero_cnj": "", "tribunal": "   "})
        interacao = _interacao()
        resultado = await checker.verificar_status_processo("proc-1", "sem info", interacao)

        assert resultado["verificado"] is True
        assert resultado["correcoes"] == []


# ---------------------------------------------------------------------------
# verificar_prazo
# ---------------------------------------------------------------------------


class TestVerificarPrazo:
    async def test_prazo_correto_verificado_true(self):
        checker = _make_checker({"prazo": "30/06/2025"})
        interacao = _interacao()
        resultado = await checker.verificar_prazo("proc-1", "30/06/2025", interacao)

        assert resultado["verificado"] is True
        assert resultado["correcoes"] == []
        assert interacao.metadata_json is None

    async def test_prazo_errado_gera_correcao(self):
        checker = _make_checker({"prazo": "30/06/2025"})
        interacao = _interacao()
        resultado = await checker.verificar_prazo("proc-1", "31/12/2025", interacao)

        assert resultado["verificado"] is False
        assert len(resultado["correcoes"]) == 1

    async def test_sem_prazo_real_sempre_verificado(self):
        """Se não há prazo no banco, não é possível verificar — passa."""
        checker = _make_checker({})
        interacao = _interacao()
        resultado = await checker.verificar_prazo("proc-1", "qualquer data", interacao)

        assert resultado["verificado"] is True
        assert resultado["prazo_real"] is None

    async def test_prazo_errado_loga_metadata_json(self):
        checker = _make_checker({"prazo": "30/06/2025"})
        interacao = _interacao()
        await checker.verificar_prazo("proc-1", "01/01/2099", interacao)

        meta = interacao.metadata_json
        assert meta["fact_check_corrigido"] is True
        assert meta["auditoria_fact_checker"][0]["evento"] == "fact_checker_prazo"

    async def test_prazo_real_retornado_no_resultado(self):
        checker = _make_checker({"prazo": "30/06/2025"})
        interacao = _interacao()
        resultado = await checker.verificar_prazo("proc-1", "data errada", interacao)

        assert resultado["prazo_real"] == "30/06/2025"

    async def test_prazo_mencionado_com_espacos_extras_tratado(self):
        """prazo_mencionado.strip() deve bater com o prazo real — espaços são ignorados."""
        checker = _make_checker({"prazo": "30/06/2025"})
        interacao = _interacao()
        resultado = await checker.verificar_prazo("proc-1", "  30/06/2025  ", interacao)

        assert resultado["verificado"] is True
        assert resultado["correcoes"] == []


# ---------------------------------------------------------------------------
# filtrar_resposta
# ---------------------------------------------------------------------------


class TestFiltrarResposta:
    def _checker(self) -> FactChecker:
        async def buscar(pid):
            return {}

        return FactChecker(buscar_dados_processo=buscar, utcnow=_utcnow_fixo)

    def test_texto_limpo_sem_disclaimer_nao_alterado(self):
        checker = self._checker()
        interacao = _interacao()
        resultado = checker.filtrar_resposta(
            "Seu processo está em andamento.", interacao, adicionar_disclaimer=False
        )

        assert resultado == "Seu processo está em andamento."
        assert interacao.metadata_json is None

    def test_voce_deve_substituido(self):
        checker = self._checker()
        interacao = _interacao()
        resultado = checker.filtrar_resposta(
            "Você deve entrar com recurso.", interacao, adicionar_disclaimer=False
        )

        assert "Você deve" not in resultado
        assert "você deve" not in resultado
        assert "é recomendado considerar" in resultado

    def test_recomendo_que_substituido(self):
        checker = self._checker()
        interacao = _interacao()
        resultado = checker.filtrar_resposta(
            "Recomendo que você aguarde.", interacao, adicionar_disclaimer=False
        )

        assert "recomendo que" not in resultado.lower()

    def test_a_estrategia_e_substituida(self):
        checker = self._checker()
        interacao = _interacao()
        resultado = checker.filtrar_resposta(
            "A estratégia é apelar.", interacao, adicionar_disclaimer=False
        )

        assert "a estratégia é" not in resultado.lower()

    def test_voce_vai_ganhar_substituido(self):
        checker = self._checker()
        interacao = _interacao()
        resultado = checker.filtrar_resposta(
            "Você vai ganhar o processo.", interacao, adicionar_disclaimer=False
        )

        assert "vai ganhar" not in resultado.lower()

    def test_multiplos_padroes_todos_substituidos(self):
        checker = self._checker()
        interacao = _interacao()
        texto = "Você deve agir. Recomendo que espere. A estratégia é recursar."
        resultado = checker.filtrar_resposta(texto, interacao, adicionar_disclaimer=False)

        assert "Você deve" not in resultado
        assert "Recomendo que" not in resultado
        assert "A estratégia é" not in resultado

    def test_disclaimer_adicionado_quando_corrige(self):
        checker = self._checker()
        interacao = _interacao()
        resultado = checker.filtrar_resposta(
            "Você deve agir.", interacao, adicionar_disclaimer=True
        )

        assert checker._disclaimer in resultado

    def test_disclaimer_nao_duplicado(self):
        checker = self._checker()
        interacao = _interacao()
        texto_ja_com_disclaimer = f"Você deve agir.\n\n{checker._disclaimer}"
        resultado = checker.filtrar_resposta(texto_ja_com_disclaimer, interacao)

        assert resultado.count(checker._disclaimer) == 1

    def test_disclaimer_nao_adicionado_sem_padroes_proibidos(self):
        """adicionar_disclaimer=True só inclui o disclaimer quando há padrão proibido.
        Texto neutro não deve ser alterado mesmo com adicionar_disclaimer=True."""
        checker = self._checker()
        interacao = _interacao()
        resultado = checker.filtrar_resposta(
            "Texto informativo neutro.", interacao, adicionar_disclaimer=True
        )

        assert checker._disclaimer not in resultado
        assert resultado == "Texto informativo neutro."

    def test_sem_padrao_proibido_nao_loga_auditoria(self):
        """Texto limpo com adicionar_disclaimer=True NÃO gera log de auditoria
        pois nenhuma alteração é feita (texto neutro = sem padrão proibido)."""
        checker = self._checker()
        interacao = _interacao()
        checker.filtrar_resposta("Texto neutro.", interacao, adicionar_disclaimer=True)

        assert interacao.metadata_json is None

    def test_correcao_loga_metadata_json(self):
        checker = self._checker()
        interacao = _interacao()
        checker.filtrar_resposta("Você deve agir.", interacao, adicionar_disclaimer=False)

        meta = interacao.metadata_json
        assert meta["fact_check_corrigido"] is True
        assert meta["auditoria_fact_checker"][0]["evento"] == "fact_checker_filtrar_resposta"

    def test_log_registra_antes_e_depois(self):
        checker = self._checker()
        interacao = _interacao()
        original = "Você deve agir."
        checker.filtrar_resposta(original, interacao, adicionar_disclaimer=False)

        payload = interacao.metadata_json["auditoria_fact_checker"][0]["payload"]
        assert payload["antes"] == original
        assert "Você deve" not in payload["depois"]

    def test_case_insensitive_padrao_maiuscula(self):
        checker = self._checker()
        interacao = _interacao()
        resultado = checker.filtrar_resposta(
            "VOCÊ DEVE fazer isso.", interacao, adicionar_disclaimer=False
        )
        assert "VOCÊ DEVE" not in resultado


# ---------------------------------------------------------------------------
# _logar_metadata_json (comportamento interno)
# ---------------------------------------------------------------------------


class TestLogarMetadataJson:
    def _checker(self) -> FactChecker:
        async def buscar(pid):
            return {}

        return FactChecker(buscar_dados_processo=buscar, utcnow=_utcnow_fixo)

    def test_metadata_none_inicializa_dict(self):
        checker = self._checker()
        interacao = _interacao(metadata_json=None)
        checker._logar_metadata_json(interacao, "evento_teste", {"k": "v"})

        assert isinstance(interacao.metadata_json, dict)

    def test_fact_check_corrigido_setado(self):
        checker = self._checker()
        interacao = _interacao()
        checker._logar_metadata_json(interacao, "evento_teste", {})

        assert interacao.metadata_json["fact_check_corrigido"] is True

    def test_auditoria_acumula_multiplos_eventos(self):
        checker = self._checker()
        interacao = _interacao()
        checker._logar_metadata_json(interacao, "evento_1", {"a": 1})
        checker._logar_metadata_json(interacao, "evento_2", {"b": 2})

        auditoria = interacao.metadata_json["auditoria_fact_checker"]
        assert len(auditoria) == 2
        assert auditoria[0]["evento"] == "evento_1"
        assert auditoria[1]["evento"] == "evento_2"

    def test_timestamp_formato_iso_com_z(self):
        checker = self._checker()
        interacao = _interacao()
        checker._logar_metadata_json(interacao, "evt", {})

        ts = interacao.metadata_json["auditoria_fact_checker"][0]["timestamp_utc"]
        assert ts == "2025-06-01T12:00:00Z"

    def test_metadata_existente_preservado(self):
        checker = self._checker()
        interacao = _interacao(metadata_json={"whatsapp_message_id": "msg-123"})
        checker._logar_metadata_json(interacao, "evt", {})

        assert interacao.metadata_json["whatsapp_message_id"] == "msg-123"
        assert "auditoria_fact_checker" in interacao.metadata_json

    def test_metadata_nao_dict_reinicializado(self):
        """Se metadata_json vier com tipo errado (ex: string), deve ser reinicializado."""
        checker = self._checker()
        interacao = _interacao(metadata_json="valor_invalido")
        checker._logar_metadata_json(interacao, "evt", {})

        assert isinstance(interacao.metadata_json, dict)
        assert "auditoria_fact_checker" in interacao.metadata_json

    def test_payload_salvo_corretamente(self):
        checker = self._checker()
        interacao = _interacao()
        checker._logar_metadata_json(interacao, "evt", {"chave": "valor", "numero": 42})

        payload = interacao.metadata_json["auditoria_fact_checker"][0]["payload"]
        assert payload == {"chave": "valor", "numero": 42}

    def test_interacao_sem_atributo_metadata_json_nao_causa_erro(self):
        """getattr com default=None deve absorver ausência do atributo sem crash."""
        checker = self._checker()
        interacao = SimpleNamespace()  # sem metadata_json
        checker._logar_metadata_json(interacao, "evt", {})

        assert hasattr(interacao, "metadata_json")
        assert isinstance(interacao.metadata_json, dict)
        assert "auditoria_fact_checker" in interacao.metadata_json
