# feature_1_ia_personalizada/tests/unit/test_prompts.py
"""
Testes estruturais dos prompts.
Verificam contratos de segurança, placeholders, tags XML e ausência de bugs de formatação.
"""

import pytest

from feature_1_ia_personalizada.services.ai.prompts import (
    _FORMATO_WHATSAPP,
    SYSTEM_PROMPT_BASE,
    SYSTEM_PROMPT_BOAS_VINDAS,
    SYSTEM_PROMPT_CLASSIFICAR_INTENCAO,
    SYSTEM_PROMPT_SEM_MOVIMENTACAO,
    SYSTEM_PROMPT_STATUS_PROCESSO,
    SYSTEM_PROMPT_TRADUZIR_TERMO,
)
from shared.config.constants import DISCLAIMER_OAB

# Todos os prompts que geram texto para o usuário final
_PROMPTS_GERACAO = [
    SYSTEM_PROMPT_BASE,
    SYSTEM_PROMPT_STATUS_PROCESSO,
    SYSTEM_PROMPT_TRADUZIR_TERMO,
    SYSTEM_PROMPT_BOAS_VINDAS,
    SYSTEM_PROMPT_SEM_MOVIMENTACAO,
]


class TestSeguranca:
    def test_classificar_intencao_nao_contem_placeholder_mensagem(self):
        """Prompt injection: a mensagem do cliente NÃO pode estar no system prompt."""
        assert "{mensagem}" not in SYSTEM_PROMPT_CLASSIFICAR_INTENCAO

    def test_classificar_intencao_exige_json(self):
        """Saída JSON é obrigatória para parsing robusto no LangGraph."""
        assert '{"intencao"' in SYSTEM_PROMPT_CLASSIFICAR_INTENCAO
        assert "JSON" in SYSTEM_PROMPT_CLASSIFICAR_INTENCAO

    def test_base_contem_regras_oab(self):
        """Regras OAB são a proteção mais crítica do sistema."""
        assert "NUNCA" in SYSTEM_PROMPT_BASE
        assert "advogado" in SYSTEM_PROMPT_BASE.lower()
        assert "estratégi" in SYSTEM_PROMPT_BASE.lower()

    def test_disclaimer_oab_embutido_em_base(self):
        assert DISCLAIMER_OAB in SYSTEM_PROMPT_BASE

    def test_disclaimer_oab_embutido_em_boas_vindas(self):
        assert DISCLAIMER_OAB in SYSTEM_PROMPT_BOAS_VINDAS

    def test_disclaimer_oab_embutido_em_sem_movimentacao(self):
        """Mensagem proativa sobre processo deve incluir disclaimer."""
        assert DISCLAIMER_OAB in SYSTEM_PROMPT_SEM_MOVIMENTACAO

    def test_base_sem_format_parcial_aplicado(self):
        """SYSTEM_PROMPT_BASE não deve ter {disclaimer} literal — deve estar resolvido."""
        assert "{disclaimer}" not in SYSTEM_PROMPT_BASE

    def test_boas_vindas_sem_format_parcial_aplicado(self):
        assert "{disclaimer}" not in SYSTEM_PROMPT_BOAS_VINDAS


class TestPlaceholders:
    def test_status_contem_todos_placeholders_processo(self):
        for placeholder in [
            "{numero_cnj}",
            "{tribunal}",
            "{vara}",
            "{ultimo_andamento}",
            "{data_ultimo_andamento}",
            "{polo_cliente}",
        ]:
            assert (
                placeholder in SYSTEM_PROMPT_STATUS_PROCESSO
            ), f"Placeholder {placeholder} ausente no STATUS"

    def test_boas_vindas_contem_placeholder_nome_cliente(self):
        assert "{nome_cliente}" in SYSTEM_PROMPT_BOAS_VINDAS

    def test_sem_movimentacao_contem_placeholders_processo(self):
        for placeholder in [
            "{numero_cnj}",
            "{ultimo_andamento}",
            "{dias_sem_movimentacao}",
        ]:
            assert (
                placeholder in SYSTEM_PROMPT_SEM_MOVIMENTACAO
            ), f"Placeholder {placeholder} ausente em SEM_MOVIMENTACAO"

    def test_nome_escritorio_nao_resolvido_em_geracao(self):
        """
        {nome_escritorio} deve permanecer como placeholder em todos os prompts —
        é resolvido em runtime pelo orchestrator.
        """
        for prompt in _PROMPTS_GERACAO:
            assert "{nome_escritorio}" in prompt, f"{prompt[:60]}... não tem {{nome_escritorio}}"


class TestFormatoWhatsApp:
    def test_formato_whatsapp_presente_em_todos_prompts_geracao(self):
        """_FORMATO_WHATSAPP deve estar embutido em todos os prompts que geram texto."""
        for prompt in _PROMPTS_GERACAO:
            assert (
                _FORMATO_WHATSAPP in prompt or "formato_saida" in prompt
            ), f"Formato WhatsApp ausente em: {prompt[:60]}..."

    def test_formato_instrui_negrito_whatsapp(self):
        """WhatsApp usa *negrito*, não **markdown**."""
        assert "*negrito*" in _FORMATO_WHATSAPP

    def test_formato_proibe_markdown_html(self):
        assert "markdown" in _FORMATO_WHATSAPP.lower()

    def test_formato_tem_tag_xml(self):
        assert "<formato_saida>" in _FORMATO_WHATSAPP
        assert "</formato_saida>" in _FORMATO_WHATSAPP


class TestTagsXML:
    def test_tags_xml_abertas_e_fechadas_no_base(self):
        for tag in [
            "tom_e_estilo",
            "regras_oab",
            "disclaimer_obrigatorio",
            "acoes_permitidas",
        ]:
            assert f"<{tag}>" in SYSTEM_PROMPT_BASE, f"Tag <{tag}> ausente no BASE"
            assert f"</{tag}>" in SYSTEM_PROMPT_BASE, f"Tag </{tag}> não fechada no BASE"

    def test_tags_xml_no_status(self):
        assert "<dados_processo>" in SYSTEM_PROMPT_STATUS_PROCESSO
        assert "</dados_processo>" in SYSTEM_PROMPT_STATUS_PROCESSO
        assert "<instrucoes>" in SYSTEM_PROMPT_STATUS_PROCESSO
        assert "</instrucoes>" in SYSTEM_PROMPT_STATUS_PROCESSO

    def test_tags_xml_em_sem_movimentacao(self):
        assert "<dados_processo>" in SYSTEM_PROMPT_SEM_MOVIMENTACAO
        assert "</dados_processo>" in SYSTEM_PROMPT_SEM_MOVIMENTACAO

    def test_categorias_xml_em_classificar(self):
        assert "<categorias>" in SYSTEM_PROMPT_CLASSIFICAR_INTENCAO
        assert "</categorias>" in SYSTEM_PROMPT_CLASSIFICAR_INTENCAO


class TestClassificador:
    def test_todas_cinco_categorias_presentes(self):
        for categoria in [
            "status",
            "duvida_termo",
            "saudacao",
            "reclamacao",
            "outro",
        ]:
            assert (
                categoria in SYSTEM_PROMPT_CLASSIFICAR_INTENCAO
            ), f"Categoria '{categoria}' ausente no classificador"

    def test_instrucao_resposta_exclusiva(self):
        assert "EXCLUSIVAMENTE" in SYSTEM_PROMPT_CLASSIFICAR_INTENCAO

    def test_exemplo_formato_correto(self):
        """O prompt deve mostrar o exemplo exato esperado."""
        assert '{"intencao": "perspectivas"}' in SYSTEM_PROMPT_CLASSIFICAR_INTENCAO


class TestConteudoMinimo:
    @pytest.mark.parametrize(
        "nome,prompt",
        [
            ("BASE", SYSTEM_PROMPT_BASE),
            ("STATUS", SYSTEM_PROMPT_STATUS_PROCESSO),
            ("TRADUZIR_TERMO", SYSTEM_PROMPT_TRADUZIR_TERMO),
            ("BOAS_VINDAS", SYSTEM_PROMPT_BOAS_VINDAS),
            ("SEM_MOVIMENTACAO", SYSTEM_PROMPT_SEM_MOVIMENTACAO),
            ("CLASSIFICAR_INTENCAO", SYSTEM_PROMPT_CLASSIFICAR_INTENCAO),
        ],
    )
    def test_prompt_nao_vazio(self, nome: str, prompt: str):
        assert isinstance(prompt, str)
        assert len(prompt) > 50, f"Prompt {nome} muito curto ({len(prompt)} chars)"

    def test_status_menciona_nunca_inventar(self):
        assert "NUNCA" in SYSTEM_PROMPT_STATUS_PROCESSO

    def test_traduzir_menciona_sem_formacao_juridica(self):
        assert "formação jurídica" in SYSTEM_PROMPT_TRADUZIR_TERMO.lower()
