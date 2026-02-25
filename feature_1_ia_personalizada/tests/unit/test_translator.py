# feature_1_ia_personalizada/tests/unit/test_translator.py
"""
Testes do JuridicalTranslator: dicionário, normalização, termos compostos,
falhas de carregamento e edge cases de entrada.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

from feature_1_ia_personalizada.services.ai.translator import JuridicalTranslator


@pytest.fixture
def translator() -> JuridicalTranslator:
    """Translator com o dicionário real (50 termos do JSON em disco)."""
    return JuridicalTranslator()


@pytest.fixture
def translator_custom(tmp_path: Path) -> JuridicalTranslator:
    """Translator apontando para um JSON temporário controlado pelo teste."""
    dados = {
        "sentença": {"traducao": "Decisão final do juiz", "exemplo": "O juiz deu a sentença."},
        "agravo de instrumento": {"traducao": "Recurso contra decisão parcial", "exemplo": ""},
        "agravo": {"traducao": "Recurso genérico", "exemplo": ""},
        "tutela antecipada": {"traducao": "Decisão provisória urgente", "exemplo": ""},
        "tutela de urgência": {"traducao": "Proteção imediata", "exemplo": ""},
        "penhora": {"traducao": "Bloqueio de bens", "exemplo": ""},
    }
    json_path = tmp_path / "traducoes.json"
    json_path.write_text(json.dumps(dados), encoding="utf-8")

    t = JuridicalTranslator.__new__(JuridicalTranslator)
    t._dicionario = {}
    t._original = {}
    t._disponivel = False

    # Força o carregamento do JSON customizado
    import feature_1_ia_personalizada.services.ai.translator as mod
    original = mod._TERMOS_JSON
    mod._TERMOS_JSON = json_path
    t._carregar_dicionario()
    mod._TERMOS_JSON = original
    return t


# ---------------------------------------------------------------------------
# Carregamento do dicionário
# ---------------------------------------------------------------------------

class TestCarregamento:
    def test_dicionario_disponivel_apos_carga(self, translator: JuridicalTranslator):
        assert translator.dicionario_disponivel is True

    def test_total_termos_maior_que_zero(self, translator: JuridicalTranslator):
        assert translator.total_termos > 0

    def test_total_termos_zero_sem_arquivo(self):
        t = JuridicalTranslator.__new__(JuridicalTranslator)
        t._dicionario = {}
        t._original = {}
        t._disponivel = False
        import feature_1_ia_personalizada.services.ai.translator as mod
        original = mod._TERMOS_JSON
        mod._TERMOS_JSON = Path("/caminho/inexistente/traducoes.json")
        t._carregar_dicionario()
        mod._TERMOS_JSON = original
        assert t.dicionario_disponivel is False
        assert t.total_termos == 0

    def test_dicionario_indisponivel_com_json_invalido(self, tmp_path: Path):
        json_ruim = tmp_path / "ruim.json"
        json_ruim.write_text("{ isso nao e json }", encoding="utf-8")

        t = JuridicalTranslator.__new__(JuridicalTranslator)
        t._dicionario = {}
        t._original = {}
        t._disponivel = False
        import feature_1_ia_personalizada.services.ai.translator as mod
        original = mod._TERMOS_JSON
        mod._TERMOS_JSON = json_ruim
        t._carregar_dicionario()
        mod._TERMOS_JSON = original
        assert t.dicionario_disponivel is False


# ---------------------------------------------------------------------------
# traduzir_termo
# ---------------------------------------------------------------------------

class TestTraduzirTermo:
    def test_termo_exato_encontrado(self, translator: JuridicalTranslator):
        resultado = translator.traduzir_termo("sentença")
        assert resultado is not None
        assert "juiz" in resultado.lower() or "decisão" in resultado.lower()

    def test_termo_uppercase_encontrado(self, translator: JuridicalTranslator):
        assert translator.traduzir_termo("SENTENÇA") is not None

    def test_termo_capitalizado_encontrado(self, translator: JuridicalTranslator):
        assert translator.traduzir_termo("Sentença") is not None

    def test_termo_sem_acento_encontrado(self, translator: JuridicalTranslator):
        """'sentenca' (sem acento) deve bater com 'sentença' no dicionário."""
        assert translator.traduzir_termo("sentenca") is not None

    def test_termo_composto_encontrado(self, translator: JuridicalTranslator):
        assert translator.traduzir_termo("agravo de instrumento") is not None

    def test_termo_inexistente_retorna_none(self, translator: JuridicalTranslator):
        assert translator.traduzir_termo("xyzzy_nao_existe_2024") is None

    def test_string_vazia_retorna_none(self, translator: JuridicalTranslator):
        assert translator.traduzir_termo("") is None

    def test_termo_indisponivel_retorna_none_sem_crash(self):
        """Se o dicionário não carregou, traduzir_termo deve retornar None sem exceção."""
        t = JuridicalTranslator.__new__(JuridicalTranslator)
        t._dicionario = {}
        t._original = {}
        t._disponivel = False
        assert t.traduzir_termo("sentença") is None

    def test_retorno_inclui_exemplo_quando_presente(self, translator_custom: JuridicalTranslator):
        resultado = translator_custom.traduzir_termo("sentença")
        assert resultado is not None
        assert "Exemplo:" in resultado
        assert "O juiz deu a sentença." in resultado

    def test_retorno_sem_exemplo_nao_tem_label_exemplo(self, translator_custom: JuridicalTranslator):
        resultado = translator_custom.traduzir_termo("penhora")
        assert resultado is not None
        assert "Exemplo:" not in resultado


# ---------------------------------------------------------------------------
# identificar_termos_tecnicos
# ---------------------------------------------------------------------------

class TestIdentificarTermos:
    def test_identifica_termo_simples(self, translator: JuridicalTranslator):
        termos = translator.identificar_termos_tecnicos("O juiz emitiu uma sentença.")
        assert "sentença" in termos

    def test_texto_vazio_retorna_lista_vazia(self, translator: JuridicalTranslator):
        assert translator.identificar_termos_tecnicos("") == []

    def test_texto_sem_termos_juridicos_retorna_lista_vazia(self, translator: JuridicalTranslator):
        assert translator.identificar_termos_tecnicos("Bom dia, como vai você?") == []

    def test_termo_composto_prioritario_sobre_subtermo(self, translator_custom: JuridicalTranslator):
        """'agravo de instrumento' deve aparecer, 'agravo' separado NÃO deve."""
        termos = translator_custom.identificar_termos_tecnicos(
            "Foi apresentado um agravo de instrumento."
        )
        assert "agravo de instrumento" in termos
        assert "agravo" not in termos

    def test_dois_termos_distintos_encontrados(self, translator_custom: JuridicalTranslator):
        termos = translator_custom.identificar_termos_tecnicos(
            "A penhora e a tutela antecipada foram deferidas."
        )
        assert "penhora" in termos
        assert "tutela antecipada" in termos

    def test_tutela_antecipada_e_tutela_urgencia_sao_distintos(self, translator_custom: JuridicalTranslator):
        termos = translator_custom.identificar_termos_tecnicos(
            "Pediu tutela antecipada e tutela de urgência."
        )
        assert "tutela antecipada" in termos
        assert "tutela de urgência" in termos

    def test_retorna_termos_com_acento_original(self, translator_custom: JuridicalTranslator):
        """Deve retornar 'sentença' (com acento), não 'sentenca' (normalizado)."""
        termos = translator_custom.identificar_termos_tecnicos("O juiz prolatou a sentença.")
        assert "sentença" in termos

    def test_mesmo_termo_nao_aparece_duplicado(self, translator_custom: JuridicalTranslator):
        termos = translator_custom.identificar_termos_tecnicos(
            "A sentença foi proferida. Após a sentença, cabe recurso."
        )
        assert termos.count("sentença") == 1

    def test_termo_uppercase_no_texto_encontrado(self, translator_custom: JuridicalTranslator):
        """Texto com termos em maiúscula deve ser identificado."""
        termos = translator_custom.identificar_termos_tecnicos("A PENHORA foi decretada.")
        assert "penhora" in termos

    def test_regex_chars_no_texto_nao_causam_crash(self, translator: JuridicalTranslator):
        """Texto com caracteres especiais de regex não deve levantar exceção."""
        texto_perigoso = "O prazo é (.*) dias? [urgente!] {imediato}"
        try:
            resultado = translator.identificar_termos_tecnicos(texto_perigoso)
            assert isinstance(resultado, list)
        except Exception as exc:
            pytest.fail(f"identificar_termos_tecnicos levantou exceção inesperada: {exc}")

    def test_texto_muito_longo_nao_causa_crash(self, translator: JuridicalTranslator):
        texto_longo = "palavra " * 10_000 + "sentença " * 5
        resultado = translator.identificar_termos_tecnicos(texto_longo)
        assert "sentença" in resultado

    def test_dicionario_indisponivel_retorna_lista_vazia(self):
        t = JuridicalTranslator.__new__(JuridicalTranslator)
        t._dicionario = {}
        t._original = {}
        t._disponivel = False
        assert t.identificar_termos_tecnicos("O juiz deu a sentença.") == []

    def test_termo_parcial_nao_encontrado(self, translator_custom: JuridicalTranslator):
        """'pen' não deve bater com 'penhora'."""
        termos = translator_custom.identificar_termos_tecnicos("Fiz uma pen drive.")
        assert "penhora" not in termos
