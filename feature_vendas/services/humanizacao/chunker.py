"""
Quebra a resposta do modelo em mensagens curtas de WhatsApp.

O maior denunciador de bot não é o texto errado — é o textão. Gente escreve
em rajadas curtas: manda uma linha, pensa, manda outra. Este módulo pega a
resposta inteira do Claude e devolve 1–3 pedaços que serão enviados como
mensagens separadas, com "digitando" entre eles (ver cadencia.py).

Também é a última barreira contra os tiques de LLM que sobrevivem ao prompt:
markdown, emoji, travessão, bullet list. O prompt pede para não usar; aqui a
gente garante.
"""

from __future__ import annotations

import re

# Alvo de tamanho por mensagem. Abaixo de _MIN não vale a pena quebrar
# (mensagem de 3 palavras seguida de outra de 3 parece nervosismo, não fala
# natural); acima de _MAX vira textão.
_ALVO_CHARS = 130
_MAX_CHARS = 220
_MIN_CHARS = 25

# Nunca mais que isso — 4 balões seguidos já é metralhadora, não conversa.
_MAX_CHUNKS = 3

_RE_EMOJI = re.compile(
    "[" "\U0001f300-\U0001faff" "\U00002600-\U000027bf" "\U0001f1e6-\U0001f1ff" "←-⇿" "⬀-⯿" "️" "]",
    flags=re.UNICODE,
)

# Fim de frase: pontuação seguida de espaço + maiúscula, ou fim de texto.
_RE_FIM_FRASE = re.compile(r"(?<=[.!?])\s+")

# Tiques de LLM que o prompt já proíbe, removidos aqui por segurança.
_RE_MARKDOWN = re.compile(r"[*_`#]+")
_RE_BULLET = re.compile(r"^\s*[-•*]\s+", flags=re.MULTILINE)
_RE_ESPACO = re.compile(r"[ \t]{2,}")


def limpar(texto: str) -> str:
    """Remove emoji, markdown, bullets e travessão. Normaliza espaços."""
    t = _RE_EMOJI.sub("", texto)
    t = _RE_MARKDOWN.sub("", t)
    t = _RE_BULLET.sub("", t)
    # Travessão e meia-risca viram vírgula — ninguém digita travessão no celular.
    t = t.replace(" — ", ", ").replace(" – ", ", ").replace("—", ",").replace("–", ",")
    t = _RE_ESPACO.sub(" ", t)
    return t.strip()


def _paragrafos(texto: str) -> list[list[str]]:
    """
    Parágrafos (separados por quebra de linha), cada um já dividido em frases.

    A quebra de linha é FRONTEIRA DURA: quando o modelo pula linha, ele mudou de
    ideia — e gente manda ideia nova em mensagem nova. Nunca reagrupamos frases
    de parágrafos diferentes no mesmo balão.
    """
    saida: list[list[str]] = []
    for paragrafo in texto.split("\n"):
        paragrafo = paragrafo.strip()
        if not paragrafo:
            continue
        frases = [f.strip() for f in _RE_FIM_FRASE.split(paragrafo) if f.strip()]
        if frases:
            saida.append(frases)
    return saida


def _cortar_longa(frase: str) -> list[str]:
    """
    Frase única maior que _MAX_CHARS: corta na vírgula mais próxima do alvo,
    ou no espaço, para nunca partir palavra ao meio.
    """
    pedacos: list[str] = []
    resto = frase
    while len(resto) > _MAX_CHARS:
        janela = resto[:_MAX_CHARS]
        corte = janela.rfind(", ")
        if corte < _MIN_CHARS:
            corte = janela.rfind(" ")
        if corte < _MIN_CHARS:
            corte = _MAX_CHARS  # sem ponto de corte razoável: corta seco
        pedacos.append(resto[:corte].strip(" ,"))
        resto = resto[corte:].strip(" ,")
    if resto:
        pedacos.append(resto)
    return pedacos


def quebrar(texto: str) -> list[str]:
    """
    Devolve as mensagens a enviar, na ordem.

    Regras, na ordem de prioridade:
      1. quebra de linha = balão novo (fronteira dura — ideia nova, mensagem nova);
      2. dentro do parágrafo, agrupa frases até ~_ALVO_CHARS;
      3. frase gigante é cortada sem partir palavra;
      4. no máximo _MAX_CHUNKS balões (senão vira metralhadora).

    Texto curto de uma linha só continua um balão único — o caso mais comum e o
    mais natural.
    """
    limpo = limpar(texto)
    if not limpo:
        return []

    paragrafos = _paragrafos(limpo)
    if not paragrafos:
        return []

    # Caso simples: um parágrafo curto, uma ideia → um balão.
    if len(paragrafos) == 1 and len(limpo) <= _MAX_CHARS and limpo.count(". ") <= 1:
        return [limpo]

    chunks: list[str] = []
    for frases in paragrafos:
        atual = ""
        for frase in frases:
            for pedaco in _cortar_longa(frase) if len(frase) > _MAX_CHARS else [frase]:
                if not atual:
                    atual = pedaco
                elif len(atual) + 1 + len(pedaco) <= _ALVO_CHARS:
                    atual = f"{atual} {pedaco}"
                else:
                    chunks.append(atual)
                    atual = pedaco
        if atual:
            chunks.append(atual)  # fim do parágrafo fecha o balão

    # Estourou o teto de balões: junta o excedente no último.
    if len(chunks) > _MAX_CHUNKS:
        cabeca = chunks[: _MAX_CHUNKS - 1]
        cauda = " ".join(chunks[_MAX_CHUNKS - 1 :])
        chunks = [*cabeca, cauda]

    # Sobra minúscula no fim ("Certo.") gruda no balão anterior.
    if len(chunks) > 1 and len(chunks[-1]) < _MIN_CHARS:
        ultimo = chunks.pop()
        chunks[-1] = f"{chunks[-1]} {ultimo}"

    return chunks
