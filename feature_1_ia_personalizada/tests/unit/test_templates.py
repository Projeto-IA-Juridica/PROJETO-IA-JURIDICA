# feature_1_ia_personalizada/tests/unit/test_templates.py
"""
Testes dos templates de mensagens (services/messaging/templates.py).

Estratégia:
  - Verificar que cada template é uma string não-vazia com chaves balanceadas.
  - Verificar que templates com placeholders formatam corretamente sem KeyError.
  - Verificar conteúdo mínimo esperado após a formatação.
  - Verificar que KeyError é levantado quando placeholder obrigatório está ausente.
"""

from __future__ import annotations

import pytest

from feature_1_ia_personalizada.services.messaging.templates import (
    TEMPLATE_AGENDAMENTO_CONFIRMADO,
    TEMPLATE_ANIVERSARIO,
    TEMPLATE_BOAS_VINDAS,
    TEMPLATE_CLIENTE_NAO_ENCONTRADO,
    TEMPLATE_CLIENTE_SEM_PROCESSO,
    TEMPLATE_DIA_BANCARIO,
    TEMPLATE_DIA_PROFESSOR,
    TEMPLATE_ERRO_GENERICO,
    TEMPLATE_MENSAGEM_TRIMESTRAL,
    TEMPLATE_NOVO_ANDAMENTO,
    TEMPLATE_SEM_MOVIMENTACAO,
)

_TODOS_OS_TEMPLATES = [
    ("BOAS_VINDAS", TEMPLATE_BOAS_VINDAS),
    ("NOVO_ANDAMENTO", TEMPLATE_NOVO_ANDAMENTO),
    ("SEM_MOVIMENTACAO", TEMPLATE_SEM_MOVIMENTACAO),
    ("CLIENTE_SEM_PROCESSO", TEMPLATE_CLIENTE_SEM_PROCESSO),
    ("CLIENTE_NAO_ENCONTRADO", TEMPLATE_CLIENTE_NAO_ENCONTRADO),
    ("AGENDAMENTO_CONFIRMADO", TEMPLATE_AGENDAMENTO_CONFIRMADO),
    ("MENSAGEM_TRIMESTRAL", TEMPLATE_MENSAGEM_TRIMESTRAL),
    ("ANIVERSARIO", TEMPLATE_ANIVERSARIO),
    ("DIA_BANCARIO", TEMPLATE_DIA_BANCARIO),
    ("DIA_PROFESSOR", TEMPLATE_DIA_PROFESSOR),
    ("ERRO_GENERICO", TEMPLATE_ERRO_GENERICO),
]


class TestEstrutura:
    @pytest.mark.parametrize("nome,template", _TODOS_OS_TEMPLATES)
    def test_e_string_nao_vazia(self, nome: str, template: str):
        assert isinstance(template, str), f"{nome} não é str"
        assert len(template.strip()) > 10, f"{nome} é muito curto"

    @pytest.mark.parametrize("nome,template", _TODOS_OS_TEMPLATES)
    def test_chaves_balanceadas(self, nome: str, template: str):
        """Toda { deve ter seu } — garante que .format() não quebra por sintaxe."""
        assert template.count("{") == template.count("}"), f"{nome} tem chaves desbalanceadas"


class TestBoasVindas:
    def test_formata_com_escritorio(self):
        resultado = TEMPLATE_BOAS_VINDAS.format(escritorio="Silva & Associados")
        assert "Silva & Associados" in resultado

    def test_menciona_processo(self):
        resultado = TEMPLATE_BOAS_VINDAS.format(escritorio="X")
        assert "processo" in resultado.lower()

    def test_contem_aviso_oab(self):
        resultado = TEMPLATE_BOAS_VINDAS.format(escritorio="X")
        assert "OAB" in resultado or "advogado" in resultado.lower()

    def test_falta_placeholder_levanta_key_error(self):
        with pytest.raises(KeyError):
            TEMPLATE_BOAS_VINDAS.format()


class TestNovoAndamento:
    def test_formata_com_numero_e_resumo(self):
        numero = "0001234-56.2023.8.26.0001"
        resumo = "Audiência marcada para 10/03/2024."
        resultado = TEMPLATE_NOVO_ANDAMENTO.format(numero=numero, resumo_traduzido=resumo)
        assert numero in resultado
        assert resumo in resultado

    def test_falta_numero_levanta_key_error(self):
        with pytest.raises(KeyError):
            TEMPLATE_NOVO_ANDAMENTO.format(resumo_traduzido="algo")

    def test_falta_resumo_levanta_key_error(self):
        with pytest.raises(KeyError):
            TEMPLATE_NOVO_ANDAMENTO.format(numero="0001")


class TestSemMovimentacao:
    def test_formata_com_numero(self):
        numero = "0009999-11.2022.5.01.0001"
        resultado = TEMPLATE_SEM_MOVIMENTACAO.format(numero=numero)
        assert numero in resultado

    def test_menciona_aviso_ou_atualizacao(self):
        resultado = TEMPLATE_SEM_MOVIMENTACAO.format(numero="X")
        texto = resultado.lower()
        assert "atualização" in texto or "avisar" in texto or "moviment" in texto

    def test_falta_numero_levanta_key_error(self):
        with pytest.raises(KeyError):
            TEMPLATE_SEM_MOVIMENTACAO.format()


class TestSemPlaceholders:
    def test_cliente_sem_processo_menciona_processo(self):
        assert "processo" in TEMPLATE_CLIENTE_SEM_PROCESSO.lower()

    def test_cliente_nao_encontrado_menciona_cadastro(self):
        assert "cadastro" in TEMPLATE_CLIENTE_NAO_ENCONTRADO.lower()

    def test_erro_generico_menciona_escritorio(self):
        assert "escritório" in TEMPLATE_ERRO_GENERICO.lower()

    def test_templates_sem_placeholder_nao_levantam_excecao(self):
        """Templates sem {} devem funcionar com .format() vazio."""
        for template in [
            TEMPLATE_CLIENTE_SEM_PROCESSO,
            TEMPLATE_CLIENTE_NAO_ENCONTRADO,
            TEMPLATE_ERRO_GENERICO,
        ]:
            resultado = template.format()
            assert isinstance(resultado, str)


class TestAgendamento:
    def test_formata_com_todos_campos(self):
        resultado = TEMPLATE_AGENDAMENTO_CONFIRMADO.format(
            nome="Dra. Ana Costa",
            data="15/03/2024",
            horario="14h00",
        )
        assert "Dra. Ana Costa" in resultado
        assert "15/03/2024" in resultado
        assert "14h00" in resultado

    def test_contem_confirmacao(self):
        resultado = TEMPLATE_AGENDAMENTO_CONFIRMADO.format(nome="X", data="X", horario="X")
        assert "✅" in resultado or "confirm" in resultado.lower()

    def test_falta_qualquer_campo_levanta_key_error(self):
        with pytest.raises(KeyError):
            TEMPLATE_AGENDAMENTO_CONFIRMADO.format(nome="X", data="X")


class TestRelacionamento:
    def test_mensagem_trimestral_formata_nome_e_dias(self):
        resultado = TEMPLATE_MENSAGEM_TRIMESTRAL.format(nome="João", dias=95)
        assert "João" in resultado
        assert "95" in resultado

    def test_mensagem_trimestral_falta_dias_levanta_key_error(self):
        with pytest.raises(KeyError):
            TEMPLATE_MENSAGEM_TRIMESTRAL.format(nome="João")

    def test_aniversario_formata_nome_e_escritorio(self):
        resultado = TEMPLATE_ANIVERSARIO.format(nome="Maria", escritorio="Costa Adv.")
        assert "Maria" in resultado
        assert "Costa Adv." in resultado

    def test_aniversario_contem_felicitacao(self):
        resultado = TEMPLATE_ANIVERSARIO.format(nome="X", escritorio="Y")
        assert "aniversário" in resultado.lower() or "🎉" in resultado

    def test_dia_bancario_formata_todos_campos(self):
        resultado = TEMPLATE_DIA_BANCARIO.format(
            nome="Carlos",
            numero="0001-X",
            status_processo="Em andamento",
        )
        assert "0001-X" in resultado
        assert "Em andamento" in resultado

    def test_dia_professor_formata_escritorio(self):
        resultado = TEMPLATE_DIA_PROFESSOR.format(escritorio="Pires & Filhos")
        assert "Pires & Filhos" in resultado
