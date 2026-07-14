"""
Contexto do lead: faz a Clara saber COM QUEM ela está falando e POR QUE
essa pessoa apareceu.

Sem isto, a Clara trata igual quem acabou de receber uma mensagem citando o
processo do escritório dele e quem escaneou um QR code de um currículo de
brincadeira. São conversas completamente diferentes, e responder as duas com
"oi, tudo bem? sou a Clara, assistente do Concierge" queima as duas.

Duas responsabilidades:

  1. detectar_origem(texto)  — o primeiro texto que a pessoa manda costuma vir
     pré-preenchido pelo link wa.me de cada canal ("Olá Clara, recebi seu
     currículo"). Isso identifica a origem sozinho, de graça.

  2. montar_contexto(...)    — vira um bloco injetado no system prompt, com o
     que sabemos do lead e como agir naquele canal.

O bloco é INSTRUÇÃO INTERNA: a Clara usa, mas não recita ("vi aqui que você
veio da landing page" é constrangedor e denuncia o sistema).
"""

from __future__ import annotations

import re

# Textos pré-preenchidos dos links wa.me de cada canal (ver PLAYBOOK).
# Casamos por trecho, não igualdade: a pessoa pode editar antes de enviar.
_SINAIS_ORIGEM: list[tuple[str, re.Pattern[str]]] = [
    ("curriculo", re.compile(r"curr[ií]culo|curriculum|\bvaga\b|candidat", re.I)),
    ("calculadora", re.compile(r"fiz a conta|calculadora|a conta do meu escrit", re.I)),
    ("indicacao", re.compile(r"me indicou|indica[çc][ãa]o|contador", re.I)),
    ("landing", re.compile(r"vim pelo site|pelo site|site de voc[êe]s", re.I)),
]


def detectar_origem(texto: str) -> str | None:
    """Origem inferida da primeira mensagem. None = sem sinal (inbound cru)."""
    for origem, rx in _SINAIS_ORIGEM:
        if rx.search(texto):
            return origem
    return None


# Como a Clara deve se portar em cada canal. O tom muda porque o estado mental
# da pessoa muda: quem recebeu o currículo está achando graça; quem respondeu à
# mensagem-espelho já viu a demonstração e não quer ouvi-la de novo.
_ROTEIRO_POR_ORIGEM: dict[str, str] = {
    "espelho": (
        "Esta pessoa RECEBEU de nós, no WhatsApp, uma mensagem mostrando a "
        "movimentação real do processo {cnj} do escritório dela, junto com a "
        "notificação que o cliente dela teria recebido em linguagem simples. "
        "Ela está respondendo a isso.\n"
        "Como agir: ela JÁ viu a demonstração. Não repita a explicação nem se "
        "reapresente do zero. Avance: responda o que ela perguntou e ofereça "
        "testar com outro processo dela, ou mostrar o agendamento."
    ),
    "frio_generico": (
        "Esta pessoa recebeu de nós uma mensagem curta apresentando a "
        "assistente e convidando a testar. Ela está respondendo a isso.\n"
        "Como agir: ela ainda não viu nada funcionando. O caminho mais forte é "
        "pedir o número de um processo dela e mostrar a notificação que o "
        "cliente dela receberia."
    ),
    "curriculo": (
        "Esta pessoa recebeu um 'currículo' seu, em papel ou PDF, candidatando "
        "você à vaga de secretária/atendimento do escritório dela. Era uma "
        "brincadeira séria: pretensão salarial R$ 997/mês, disponibilidade 24h, "
        "sem INSS. Ela escaneou o QR para 'te entrevistar'.\n"
        "Como agir: entre na brincadeira, com leveza e sem forçar. Você está "
        "numa entrevista de emprego. Deixe que ela te 'entreviste' e responda "
        "como quem quer a vaga. Em algum momento, proponha a prova prática: "
        "pedir um processo real do escritório e mostrar o que você faria."
    ),
    "landing": (
        "Esta pessoa veio do nosso site e quis conversar com você.\n"
        "Como agir: ela está curiosa mas fria. Não despeje explicação. Descubra "
        "rápido a área dela e leve para a demonstração com um processo real."
    ),
    "calculadora": (
        "Esta pessoa usou nossa calculadora no site e viu quanto tempo e dinheiro "
        "o escritório dela gasta respondendo 'tem novidade?' no WhatsApp.\n"
        "Como agir: ela já está com o problema na cabeça e viu um número. Não "
        "repita a conta. Mostre a solução funcionando: peça um processo dela."
    ),
    "indicacao": (
        "Esta pessoa chegou por indicação de alguém em quem ela confia.\n"
        "Como agir: a confiança já veio emprestada, então nada de tom de venda. "
        "Seja direta e prestativa, como quem foi apresentado por um amigo em "
        "comum. Vá para a demonstração com naturalidade."
    ),
    "inbound": (
        "Esta pessoa mandou mensagem sem que a gente soubesse de onde veio.\n"
        "Como agir: descubra com naturalidade quem é e o que a trouxe, antes de "
        "oferecer qualquer coisa."
    ),
}


def montar_contexto(
    *,
    origem: str,
    template_usado: str | None = None,
    processo_cnj: str | None = None,
    nome_escritorio: str | None = None,
    nome_contato: str | None = None,
    cidade: str | None = None,
    area: str | None = None,
) -> str:
    """
    Bloco de contexto para o system prompt da Clara.

    `origem` é o campo do AlvoVendas (planilha/vaga/anuncio/indicacao/inbound)
    ou uma origem detectada pela primeira mensagem (curriculo/landing/...).
    Quando a pessoa veio de uma abordagem nossa (origem planilha/vaga/anuncio),
    o roteiro depende do TEMPLATE que enviamos: A (espelho com processo) ou B.
    """
    if origem in _ROTEIRO_POR_ORIGEM:
        chave = origem
    elif template_usado == "A" and processo_cnj:
        chave = "espelho"
    elif template_usado == "B":
        chave = "frio_generico"
    else:
        chave = "inbound"

    roteiro = _ROTEIRO_POR_ORIGEM[chave].format(cnj=processo_cnj or "")

    quem: list[str] = []
    if nome_escritorio and not nome_escritorio.startswith("("):
        quem.append(nome_escritorio)
    if nome_contato:
        quem.append(nome_contato)
    if cidade:
        quem.append(cidade)
    if area:
        quem.append(f"área: {area}")

    linhas = ["CONTEXTO DESTE LEAD (instrução interna — nunca recite isto)"]
    if quem:
        linhas.append(f"Quem é: {', '.join(quem)}.")
    linhas.append(roteiro)
    linhas.append(
        "Você sabe disso porque é o seu trabalho saber, não porque 'o sistema "
        "informou'. Nunca diga que tem essas informações; apenas aja de acordo."
    )
    return "\n".join(linhas)
