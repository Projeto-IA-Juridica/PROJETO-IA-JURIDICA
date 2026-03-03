"""
shared/utils/validators.py
===========================
Funções de validação para dados brasileiros.

Consolida a lógica que estava inline nos schemas:
  - _validar_cpf / _normalizar_cpf      (antes em shared/schemas/cliente.py)
  - _validar_cnpj                       (antes em shared/schemas/escritorio.py)
  - _validar_formato_cnj / _validar_digito_cnj  (antes em shared/schemas/processo.py)
  - _validar_telefone_whatsapp          (antes em shared/schemas/cliente.py)
  - _validar_oab                        (antes em shared/schemas/escritorio.py e usuario.py)
  - _validar_telefone_br                (antes em shared/schemas/escritorio.py)

Uso:
    from shared.utils.validators import validar_cpf, normalizar_cpf
"""

import re

# ---------------------------------------------------------------------------
# CPF
# ---------------------------------------------------------------------------


def validar_cpf(cpf: str) -> bool:
    """
    Valida CPF com o algoritmo oficial dos dígitos verificadores.

    Aceita qualquer formatação (xxx.xxx.xxx-xx, xxxxxxxxxxx, etc.).
    Rejeita sequências de dígitos iguais (ex: 11111111111).
    """
    digits = re.sub(r"[^0-9]", "", cpf)
    if len(digits) != 11:
        return False
    if digits == digits[0] * 11:
        return False

    def _digito(parcial: str, peso_inicial: int) -> int:
        total = sum(
            int(d) * p
            for d, p in zip(parcial, range(peso_inicial, 1, -1), strict=False)
        )
        resto = total % 11
        return 0 if resto < 2 else 11 - resto

    if int(digits[9]) != _digito(digits[:9], 10):
        return False
    if int(digits[10]) != _digito(digits[:10], 11):
        return False
    return True


def normalizar_cpf(cpf: str) -> str:
    """Remove formatação — retorna apenas os 11 dígitos."""
    return re.sub(r"[^0-9]", "", cpf)


# ---------------------------------------------------------------------------
# CNPJ
# ---------------------------------------------------------------------------


def validar_cnpj(cnpj: str) -> bool:
    """
    Valida CNPJ com o algoritmo oficial dos dígitos verificadores.

    Aceita qualquer formatação (xx.xxx.xxx/xxxx-xx, etc.).
    Rejeita sequências de dígitos iguais (ex: 00000000000000).
    """
    digits = re.sub(r"[^0-9]", "", cnpj)
    if len(digits) != 14:
        return False
    if digits == digits[0] * 14:
        return False

    def _digito(parcial: str, pesos: list[int]) -> int:
        total = sum(int(d) * p for d, p in zip(parcial, pesos, strict=False))
        resto = total % 11
        return 0 if resto < 2 else 11 - resto

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    if int(digits[12]) != _digito(digits[:12], pesos1):
        return False
    if int(digits[13]) != _digito(digits[:13], pesos2):
        return False
    return True


def normalizar_cnpj(cnpj: str) -> str:
    """Remove formatação — retorna apenas os 14 dígitos."""
    return re.sub(r"[^0-9]", "", cnpj)


# ---------------------------------------------------------------------------
# Número de processo CNJ
# ---------------------------------------------------------------------------

# CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO
_CNJ_REGEX = re.compile(r"^\d{7}-\d{2}\.\d{4}\.[1-9]\.\d{2}\.\d{4}$")


def validar_numero_processo(numero: str) -> bool:
    """
    Valida o número de processo no formato CNJ (Resolução CNJ nº 65/2008).

    Verifica:
      1. Formato: NNNNNNN-DD.AAAA.J.TT.OOOO
      2. Dígito verificador DD (ISO 7064 MOD 97-10)

    Algoritmo do dígito:
      base = NNNNNNN + AAAA + J + TT + OOOO
      DD = 98 - (int(base + "00") % 97)
    """
    normalizado = numero.strip()
    if not _CNJ_REGEX.match(normalizado):
        return False

    partes = re.split(r"[-.]", normalizado)
    if len(partes) != 6:
        return False

    nnnnnnn, dd_str, aaaa, j, tt, oooo = partes
    base = nnnnnnn + aaaa + j + tt + oooo
    dd_esperado = 98 - (int(base + "00") % 97)
    return int(dd_str) == dd_esperado


def normalizar_numero_processo(numero: str) -> str:
    """
    Garante que o número CNJ está no formato padrão NNNNNNN-DD.AAAA.J.TT.OOOO.

    Aceita entrada com ou sem formatação (apenas dígitos também).
    Levanta ValueError se o número não puder ser normalizado.
    """
    limpo = re.sub(r"[^0-9]", "", numero)
    if len(limpo) != 20:
        raise ValueError(
            f"Número de processo deve ter 20 dígitos, recebeu {len(limpo)}"
        )
    # Reconstrói: NNNNNNN-DD.AAAA.J.TT.OOOO
    return (
        f"{limpo[:7]}-{limpo[7:9]}.{limpo[9:13]}"
        f".{limpo[13]}.{limpo[14:16]}.{limpo[16:20]}"
    )


# ---------------------------------------------------------------------------
# Telefone WhatsApp
# ---------------------------------------------------------------------------

# Formato: 55 + DDD (2 dígitos, começa com 1-9) + 9 obrigatório + 8 dígitos = 13 total
# Fixo (8 dígitos sem o 9) é rejeitado — WhatsApp só funciona em celular
_TEL_WPP_REGEX = re.compile(r"^55[1-9]\d9\d{8}$")


def validar_telefone_whatsapp(telefone: str) -> bool:
    """
    Valida número de telefone para WhatsApp no padrão brasileiro.

    Formato esperado: 5511999999999 (55 + DDD + 9 + 8 dígitos = 13 dígitos).
    Aceita entrada com qualquer formatação — extrai apenas os dígitos.
    Rejeita telefones fixos (sem o dígito 9 após o DDD).
    """
    digits = re.sub(r"[^0-9]", "", telefone)
    return bool(_TEL_WPP_REGEX.match(digits))


def normalizar_telefone(telefone: str) -> str:
    """
    Normaliza telefone para o formato WhatsApp: 55 + DDD + 9 + 8 dígitos.

    Remove toda formatação e garante o prefixo 55.
    Levanta ValueError se o telefone resultante for inválido.
    """
    digits = re.sub(r"[^0-9]", "", telefone)

    # Adiciona 55 se não tiver o código do país
    if len(digits) == 11 and digits[0] != "5":
        digits = "55" + digits
    elif len(digits) == 10:
        digits = "55" + digits

    if not validar_telefone_whatsapp(digits):
        raise ValueError(
            "Telefone inválido — formato esperado: 5511999999999 (55 + DDD + número)"
        )
    return digits


# ---------------------------------------------------------------------------
# OAB
# ---------------------------------------------------------------------------

# Formato: 2 letras maiúsculas (UF) + 4 a 8 dígitos — ex: SP123456
_OAB_REGEX = re.compile(r"^[A-Z]{2}\d{4,8}$")


def validar_oab(oab: str) -> bool:
    """
    Valida número OAB (Ordem dos Advogados do Brasil).

    Formato: 2 letras maiúsculas de UF + 4 a 8 dígitos.
    Exemplos válidos: SP123456, RJ12345, MG1234567

    A comparação é feita em uppercase — a entrada é normalizada internamente.
    """
    return bool(_OAB_REGEX.match(oab.upper().strip()))


# ---------------------------------------------------------------------------
# Telefone BR genérico (fixo ou celular)
# ---------------------------------------------------------------------------

# Aceita: (11) 99999-9999 | 11 99999-9999 | 11999999999 | +5511999999999
_TEL_BR_REGEX = re.compile(
    r"^(\+55\s?)?"  # prefixo internacional opcional
    r"(\(?\d{2}\)?\s?)"  # DDD com ou sem parênteses
    r"9?\d{4}"  # dígito 9 opcional + 4 dígitos
    r"[-]?"  # separador opcional
    r"\d{4}$"  # 4 dígitos finais
)


def validar_telefone_br(telefone: str) -> bool:
    """
    Valida número de telefone brasileiro genérico (fixo ou celular).

    Aceita múltiplos formatos:
      - (11) 99999-9999
      - 11 99999-9999
      - 11999999999
      - +5511999999999

    Nota: aceita tanto celular quanto fixo.
    Para WhatsApp especificamente, use validar_telefone_whatsapp().
    """
    return bool(_TEL_BR_REGEX.match(telefone.strip()))
