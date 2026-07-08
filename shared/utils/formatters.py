"""
shared/utils/formatters.py
===========================
Funções de formatação para locale brasileiro.

- formatar_data_br          → "16/02/2026 às 14:30"
- formatar_data_relativa    → "hoje", "ontem", "há 3 dias", "há 2 meses"
- formatar_moeda_brl        → "R$ 1.500,00"
- formatar_numero_processo  → "0001234-56.2024.8.26.0100"

Uso:
    from shared.utils.formatters import formatar_data_br, formatar_moeda_brl
"""

import re
from datetime import UTC, datetime
from decimal import Decimal

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def formatar_data_br(dt: datetime) -> str:
    """
    Formata datetime para o padrão brasileiro com hora.

    Exemplo: datetime(2026, 2, 16, 14, 30) → "16/02/2026 às 14:30"

    Nota: imprime a hora exatamente como vier no objeto. Se o datetime
    estiver em UTC e o usuário esperar horário de Brasília (UTC-3),
    converta antes de chamar esta função.
    """
    return dt.strftime("%d/%m/%Y às %H:%M")


def formatar_data_relativa(dt: datetime) -> str:
    """
    Retorna uma representação relativa legível do datetime em português.

    Regras:
      - Mesmo dia (UTC)        → "hoje"
      - 1 dia atrás            → "ontem"
      - 2–6 dias atrás         → "há X dias"
      - 7–29 dias atrás        → "há X semanas"
      - 30–364 dias atrás      → "há X meses"
      - 365+ dias atrás        → "há X anos"
      - No futuro              → "em breve"

    O datetime de entrada pode ser naive (assume UTC) ou aware.
    """
    agora = datetime.now(tz=UTC)

    # Normaliza para aware UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    if agora < dt:
        return "em breve"

    # Compara datas calendário (não janela de 24h)
    dias = (agora.date() - dt.date()).days

    if dias == 0:
        return "hoje"
    if dias == 1:
        return "ontem"
    if dias < 7:
        return f"há {dias} dias"
    if dias < 30:
        semanas = dias // 7
        return f"há {semanas} semana" if semanas == 1 else f"há {semanas} semanas"
    if dias < 365:
        # Aproximação de 30 dias/mês — sem dependência de dateutil.
        # 59 dias = 1 mês, 60 dias = 2 meses. Aceitável para uso em UI.
        meses = dias // 30
        return f"há {meses} mês" if meses == 1 else f"há {meses} meses"

    anos = dias // 365
    return f"há {anos} ano" if anos == 1 else f"há {anos} anos"


# ---------------------------------------------------------------------------
# Moeda
# ---------------------------------------------------------------------------


def formatar_moeda_brl(valor: Decimal | float | int) -> str:
    """
    Formata valor numérico como moeda brasileira.

    Exemplos:
      1500       → "R$ 1.500,00"
      1500.5     → "R$ 1.500,50"
      0.99       → "R$ 0,99"
      1000000    → "R$ 1.000.000,00"
    """
    # Garante Decimal para precisão
    if not isinstance(valor, Decimal):
        valor = Decimal(str(valor))

    # Arredonda para 2 casas
    valor = valor.quantize(Decimal("0.01"))

    # Separa parte inteira e decimal
    negativo = valor < 0
    valor_abs = abs(valor)
    partes = f"{valor_abs:.2f}".split(".")
    inteiro = partes[0]
    centavos = partes[1]

    # Insere pontos de milhar
    grupos = []
    while len(inteiro) > 3:
        grupos.append(inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.append(inteiro)
    inteiro_formatado = ".".join(reversed(grupos))

    sinal = "-" if negativo else ""
    return f"R$ {sinal}{inteiro_formatado},{centavos}"


# ---------------------------------------------------------------------------
# Número de processo CNJ
# ---------------------------------------------------------------------------


def formatar_numero_processo(numero: str) -> str:
    """
    Formata número de processo para o padrão CNJ pontuado.

    Aceita entrada com ou sem formatação (apenas dígitos também).
    Formato de saída: NNNNNNN-DD.AAAA.J.TT.OOOO

    Levanta ValueError se não contiver exatamente 20 dígitos.
    """
    limpo = re.sub(r"[^0-9]", "", numero)
    if len(limpo) != 20:
        raise ValueError(f"Número de processo deve ter 20 dígitos, recebeu {len(limpo)}")
    return f"{limpo[:7]}-{limpo[7:9]}.{limpo[9:13]}.{limpo[13]}.{limpo[14:16]}.{limpo[16:20]}"


# ---------------------------------------------------------------------------
# Emojis
# ---------------------------------------------------------------------------

_EMOJI_RE = re.compile(
    "["
    "\U0001f000-\U0001faff"  # emojis, pictogramas, símbolos suplementares
    "☀-➿"  # símbolos diversos e dingbats (⚖, ✅, ❌ etc.)
    "⬀-⯿"  # setas e estrelas (⭐, ⬆ etc.)
    "←-⇿"  # setas básicas usadas como emoji (↔️ etc.)
    "⌀-⏿"  # técnico misc. (⏰, ⌛ etc.)
    "■-◿"  # formas geométricas (▶️ etc.)
    " -‏"  # espaços tipográficos e ZWJ/ZWNJ de sequências emoji
    "⃣"  # keycap combinante (1️⃣ → remove o quadrado, mantém o dígito)
    "︎️"  # variation selectors (forma texto/emoji)
    "〰〽™©®"  # marcas usadas como emoji (™ © ®)
    "]+"
)


def remover_emojis(texto: str) -> str:
    """
    Remove emojis e caracteres de composição de emoji do texto.

    Rede de segurança das mensagens WhatsApp ao cliente: os templates não
    têm mais emojis, mas texto gerado pelo Claude pode trazê-los mesmo com
    a instrução em contrário no prompt. Dígitos de keycaps são preservados
    ("1️⃣" vira "1"). Espaços duplicados que sobram são colapsados.
    """
    sem_emoji = _EMOJI_RE.sub("", texto)
    # colapsa espaços que sobraram no lugar do emoji, sem tocar em quebras de linha
    sem_emoji = re.sub(r"[ \t]{2,}", " ", sem_emoji)
    # remove espaço órfão antes de pontuação final ("Até lá !" → "Até lá!")
    sem_emoji = re.sub(r" +([!?.,;:])", r"\1", sem_emoji)
    return "\n".join(linha.strip() for linha in sem_emoji.split("\n"))
