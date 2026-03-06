# shared/tests/test_validators.py
"""
Testes unitários para shared/utils/validators.py.

Cobre todas as funções públicas:
  - validar_cpf / normalizar_cpf
  - validar_cnpj / normalizar_cnpj
  - validar_numero_processo / normalizar_numero_processo
  - validar_telefone_whatsapp / normalizar_telefone
  - validar_oab
  - validar_telefone_br
"""
from __future__ import annotations

import pytest

from shared.utils.validators import (
    normalizar_cnpj,
    normalizar_cpf,
    normalizar_numero_processo,
    normalizar_telefone,
    validar_cnpj,
    validar_cpf,
    validar_numero_processo,
    validar_oab,
    validar_telefone_br,
    validar_telefone_whatsapp,
)

# ---------------------------------------------------------------------------
# Constantes de teste
# ---------------------------------------------------------------------------

# CPF 529.982.247-25 — dígitos verificadores calculados pelo algoritmo oficial
CPF_VALIDO = "529.982.247-25"
CPF_VALIDO_RAW = "52998224725"
CPF_INVALIDO = "123.456.789-00"  # dígito verificador errado

# CNPJ 11.222.333/0001-81 — dígitos verificadores calculados pelo algoritmo oficial
CNPJ_VALIDO = "11.222.333/0001-81"
CNPJ_VALIDO_RAW = "11222333000181"
CNPJ_INVALIDO = "11.222.333/0001-99"  # dígito verificador errado


def _make_cnj(nnnnnnn="0001234", aaaa="2024", j="8", tt="26", oooo="0100") -> str:
    """Gera número CNJ com dígito verificador correto (ISO 7064 MOD 97-10)."""
    base = nnnnnnn + aaaa + j + tt + oooo
    dd = 98 - (int(base + "00") % 97)
    return f"{nnnnnnn}-{dd:02d}.{aaaa}.{j}.{tt}.{oooo}"


CNJ_VALIDO = _make_cnj()


# ---------------------------------------------------------------------------
# CPF
# ---------------------------------------------------------------------------


class TestValidarCPF:
    def test_valido_com_formatacao(self):
        assert validar_cpf(CPF_VALIDO) is True

    def test_valido_sem_formatacao(self):
        assert validar_cpf(CPF_VALIDO_RAW) is True

    def test_invalido_digito_verificador(self):
        assert validar_cpf(CPF_INVALIDO) is False

    def test_invalido_sequencia_repetida_uns(self):
        assert validar_cpf("111.111.111-11") is False

    def test_invalido_sequencia_repetida_zeros(self):
        assert validar_cpf("000.000.000-00") is False

    def test_invalido_sequencia_repetida_noves(self):
        assert validar_cpf("999.999.999-99") is False

    def test_invalido_tamanho_curto(self):
        assert validar_cpf("123.456.789") is False

    def test_invalido_tamanho_longo(self):
        assert validar_cpf("529.982.247-250") is False

    def test_vazio_retorna_false(self):
        assert validar_cpf("") is False

    def test_apenas_letras_retorna_false(self):
        assert validar_cpf("abcdefghijk") is False


class TestNormalizarCPF:
    def test_remove_pontuacao(self):
        assert normalizar_cpf(CPF_VALIDO) == CPF_VALIDO_RAW

    def test_ja_sem_pontuacao_permanece_igual(self):
        assert normalizar_cpf(CPF_VALIDO_RAW) == CPF_VALIDO_RAW

    def test_mantem_apenas_digitos(self):
        assert normalizar_cpf("abc529.982def.247-25xyz") == CPF_VALIDO_RAW


# ---------------------------------------------------------------------------
# CNPJ
# ---------------------------------------------------------------------------


class TestValidarCNPJ:
    def test_valido_com_formatacao(self):
        assert validar_cnpj(CNPJ_VALIDO) is True

    def test_valido_sem_formatacao(self):
        assert validar_cnpj(CNPJ_VALIDO_RAW) is True

    def test_invalido_digito_verificador(self):
        assert validar_cnpj(CNPJ_INVALIDO) is False

    def test_invalido_sequencia_repetida_zeros(self):
        assert validar_cnpj("00.000.000/0000-00") is False

    def test_invalido_sequencia_repetida_uns(self):
        assert validar_cnpj("11.111.111/1111-11") is False

    def test_invalido_tamanho_curto(self):
        assert validar_cnpj("11.222.333") is False

    def test_invalido_tamanho_longo(self):
        assert validar_cnpj("11.222.333/0001-810") is False

    def test_vazio_retorna_false(self):
        assert validar_cnpj("") is False


class TestNormalizarCNPJ:
    def test_remove_pontuacao(self):
        assert normalizar_cnpj(CNPJ_VALIDO) == CNPJ_VALIDO_RAW

    def test_ja_sem_pontuacao_permanece_igual(self):
        assert normalizar_cnpj(CNPJ_VALIDO_RAW) == CNPJ_VALIDO_RAW

    def test_mantem_apenas_digitos(self):
        assert normalizar_cnpj("11.222.333/0001-81") == CNPJ_VALIDO_RAW


# ---------------------------------------------------------------------------
# Número de processo CNJ
# ---------------------------------------------------------------------------


class TestValidarNumeroProcesso:
    def test_valido(self):
        assert validar_numero_processo(CNJ_VALIDO) is True

    def test_valido_com_espacos_extras(self):
        assert validar_numero_processo(f"  {CNJ_VALIDO}  ") is True

    def test_formato_errado_sem_separadores(self):
        assert validar_numero_processo("1234567890") is False

    def test_formato_errado_muito_curto(self):
        assert validar_numero_processo("1234567-89") is False

    def test_digito_verificador_errado(self):
        """Formato correto mas DD errado deve ser rejeitado."""
        cnj_dd_errado = CNJ_VALIDO[:8] + "99" + CNJ_VALIDO[10:]
        assert validar_numero_processo(cnj_dd_errado) is False

    def test_j_zero_invalido(self):
        """Campo J (justiça) deve ser 1–9; 0 é inválido pelo regex."""
        cnj_j_zero = _make_cnj(j="0")
        # O regex rejeita J=0 antes mesmo do dígito verificador
        assert validar_numero_processo(cnj_j_zero) is False

    def test_vazio_retorna_false(self):
        assert validar_numero_processo("") is False

    def test_diferentes_tribunais_validos(self):
        """Variações de TT e OOOO devem ser válidas com DD correto."""
        assert validar_numero_processo(_make_cnj(tt="01", oooo="0001")) is True
        assert validar_numero_processo(_make_cnj(j="5", tt="00", oooo="0000")) is True


class TestNormalizarNumeroProcesso:
    def test_ja_formatado_reconstroi_igual(self):
        assert normalizar_numero_processo(CNJ_VALIDO) == CNJ_VALIDO

    def test_formato_com_20_digitos_produz_formato_padrao(self):
        digitos = "".join(c for c in CNJ_VALIDO if c.isdigit())
        resultado = normalizar_numero_processo(digitos)
        assert resultado.count("-") == 1
        assert resultado.count(".") == 4
        # Deve reconstruir o mesmo número
        assert resultado == CNJ_VALIDO

    def test_menos_de_20_digitos_levanta_erro(self):
        with pytest.raises(ValueError, match="20 dígitos"):
            normalizar_numero_processo("123456")

    def test_mais_de_20_digitos_levanta_erro(self):
        with pytest.raises(ValueError, match="20 dígitos"):
            normalizar_numero_processo("0" * 21)

    def test_vazio_levanta_erro(self):
        with pytest.raises(ValueError, match="20 dígitos"):
            normalizar_numero_processo("")


# ---------------------------------------------------------------------------
# Telefone WhatsApp
# ---------------------------------------------------------------------------


class TestValidarTelefoneWhatsapp:
    def test_valido_13_digitos_raw(self):
        assert validar_telefone_whatsapp("5511987654321") is True

    def test_valido_com_formatacao_internacional(self):
        assert validar_telefone_whatsapp("+55 (11) 98765-4321") is True

    def test_fixo_sem_nono_digito(self):
        """Linha fixa (8 dígitos após DDD) não é aceita no WhatsApp."""
        assert validar_telefone_whatsapp("551132345678") is False

    def test_ddd_comecando_com_zero_invalido(self):
        """DDD não pode começar com 0 (regex: [1-9])."""
        assert validar_telefone_whatsapp("5501987654321") is False

    def test_muito_curto(self):
        assert validar_telefone_whatsapp("55119") is False

    def test_mais_de_13_digitos(self):
        assert validar_telefone_whatsapp("55119876543210") is False

    def test_sem_prefixo_55(self):
        # "11987654321" tem 11 dígitos — o regex rejeita por comprimento (espera 13),
        # não especificamente por ausência do prefixo 55.
        assert validar_telefone_whatsapp("11987654321") is False

    def test_vazio_retorna_false(self):
        assert validar_telefone_whatsapp("") is False


class TestNormalizarTelefone:
    def test_13_digitos_completo_retorna_igual(self):
        assert normalizar_telefone("5511987654321") == "5511987654321"

    def test_11_digitos_sem_55_adiciona_prefixo(self):
        assert normalizar_telefone("11987654321") == "5511987654321"

    def test_com_formatacao_internacional_normaliza(self):
        assert normalizar_telefone("+55 (11) 98765-4321") == "5511987654321"

    def test_com_formatacao_nacional_normaliza(self):
        assert normalizar_telefone("(11) 98765-4321") == "5511987654321"

    def test_fixo_levanta_erro(self):
        with pytest.raises(ValueError, match="Telefone inválido"):
            normalizar_telefone("551132345678")

    def test_muito_curto_levanta_erro(self):
        with pytest.raises(ValueError, match="Telefone inválido"):
            normalizar_telefone("123")

    def test_10_digitos_fixo_adiciona_prefixo_mas_ainda_invalido(self):
        """10 dígitos → 'elif len == 10' adiciona '55' → 12 dígitos → falha validação WhatsApp."""
        with pytest.raises(ValueError, match="Telefone inválido"):
            normalizar_telefone("1132345678")  # DDD + 8 dígitos fixo

    def test_11_digitos_comecando_com_5_nao_adiciona_prefixo(self):
        """11 dígitos começando com '5' não entram no branch de adição de prefixo
        (condição digits[0] != '5' é False) — resultado continua com 11 dígitos e falha.
        """
        with pytest.raises(ValueError, match="Telefone inválido"):
            normalizar_telefone("55987654321")

    def test_vazio_levanta_erro(self):
        with pytest.raises(ValueError, match="Telefone inválido"):
            normalizar_telefone("")


# ---------------------------------------------------------------------------
# OAB
# ---------------------------------------------------------------------------


class TestValidarOAB:
    def test_valido_sp_6_digitos(self):
        assert validar_oab("SP123456") is True

    def test_valido_rj_minimo_4_digitos(self):
        assert validar_oab("RJ1234") is True

    def test_valido_mg_maximo_8_digitos(self):
        assert validar_oab("MG12345678") is True

    def test_lowercase_normalizado(self):
        """Entrada em minúsculas deve ser aceita após normalização para uppercase."""
        assert validar_oab("sp123456") is True

    def test_lowercase_com_espacos_normalizado(self):
        assert validar_oab("  rj12345  ") is True

    def test_uma_letra_invalido(self):
        assert validar_oab("S1234567") is False

    def test_tres_letras_invalido(self):
        assert validar_oab("SPX12345") is False

    def test_menos_de_4_digitos_invalido(self):
        assert validar_oab("SP123") is False

    def test_mais_de_8_digitos_invalido(self):
        assert validar_oab("SP123456789") is False

    def test_sem_letras_invalido(self):
        assert validar_oab("12345678") is False

    def test_letras_onde_devem_ser_digitos_invalido(self):
        """Letras no campo de dígitos devem ser rejeitadas."""
        assert validar_oab("SPABC123") is False

    def test_vazio_invalido(self):
        assert validar_oab("") is False


# ---------------------------------------------------------------------------
# Telefone BR genérico
# ---------------------------------------------------------------------------


class TestValidarTelefoneBr:
    def test_celular_com_parenteses_e_hifen(self):
        assert validar_telefone_br("(11) 99999-9999") is True

    def test_celular_com_espaco_sem_parenteses(self):
        assert validar_telefone_br("11 99999-9999") is True

    def test_celular_sem_formatacao(self):
        assert validar_telefone_br("11999999999") is True

    def test_celular_com_prefixo_internacional(self):
        assert validar_telefone_br("+5511999999999") is True

    def test_fixo_com_parenteses_e_hifen(self):
        """Linha fixa (sem o 9) é válida para validar_telefone_br."""
        assert validar_telefone_br("(11) 3234-5678") is True

    def test_fixo_sem_formatacao(self):
        assert validar_telefone_br("1132345678") is True

    def test_com_espacos_no_inicio_ou_fim(self):
        """strip() deve ser aplicado antes da validação."""
        assert validar_telefone_br("  (11) 99999-9999  ") is True

    def test_vazio_invalido(self):
        assert validar_telefone_br("") is False

    def test_muito_curto_invalido(self):
        assert validar_telefone_br("119") is False

    def test_apenas_letras_invalido(self):
        assert validar_telefone_br("abcdefghij") is False

    def test_ddd_ausente_invalido(self):
        """Número sem DDD (menos de 10 dígitos no corpo) deve falhar."""
        assert validar_telefone_br("99999-9999") is False

    def test_ddd_zero_aceito_sem_validacao_semantica(self):
        # Limitação conhecida: o regex valida estrutura mas não o valor do DDD.
        # "(00) 99999-9999" passa porque o grupo de DDD aceita qualquer 2 dígitos.
        assert validar_telefone_br("(00) 99999-9999") is True
