"""
Opt-out: quem pede para parar, para. Para sempre.

Isto não é cortesia — é o que separa prospecção de spam. Numa máquina que aborda
gente que não pediu contato, o opt-out é a única promessa que NÃO pode falhar:
quebrá-la é dano de reputação (advogado que se sente perseguido escreve sobre
isso) e risco regulatório (CDC, LGPD, marco de IA).

O prompt da Clara já promete parar. Este módulo faz o sistema CUMPRIR:

  1. detecta o pedido na mensagem (regex barata, antes de gastar token);
  2. o worker marca o alvo como descartado + opt_out e manda UMA confirmação;
  3. a Clara não responde mais àquele número;
  4. a importação de planilha PULA quem já pediu para sair — mesmo que o número
     volte numa lista futura. É isso que torna o opt-out eterno.

Falso positivo custa um lead. Falso negativo custa a reputação. Na dúvida, o
código erra para o lado de respeitar o pedido.
"""

from __future__ import annotations

import re

# Pedidos explícitos de parar. Deliberadamente exige sinal claro: "não quero"
# sozinho aparece em conversa normal ("não quero agendar hoje") e não pode
# matar um lead morno por engano.
_RE_OPT_OUT = re.compile(
    r"\b("
    r"n[ãa]o\s+(me\s+)?(mand[ea]|envi[ea]|escrev[ae]|perturb|ench)"  # não me mande/envie
    r"|par[ea]\s+de\s+(me\s+)?(mandar|enviar|escrever|ligar|perturbar)"  # pare de me mandar
    r"|n[ãa]o\s+(tenho|há|ha)\s+interesse"  # não tenho interesse
    r"|n[ãa]o\s+quero\s+(receber|mais|nada|contato|mensagens?)"  # não quero receber/mais
    r"|(remov|descadastr|desinscrev)\w*"  # remover/descadastrar
    r"|(me\s+)?(tir[ae]|exclu[ai])\w*\s+(d[ao]|dessa|desta)\s+lista"  # me tire da lista
    r"|sair\s+da\s+lista"
    r"|\bspam\b"
    r"|vou\s+denunciar|denunciar\s+voc[êe]"
    r"|perde[rn]?\s+meu\s+tempo"
    r"|me\s+deix[ea]\s+em\s+paz"
    r")",
    re.IGNORECASE,
)


def pediu_para_parar(texto: str) -> bool:
    """True quando a pessoa pede, de forma reconhecível, para não ser mais contatada."""
    return bool(_RE_OPT_OUT.search(texto))


# Confirmação única. Curta, sem tentar reverter — insistir depois de um "pare"
# é exatamente o comportamento que queremos nunca ter.
MENSAGEM_CONFIRMACAO = "sem problema, doutor. não te incomodo mais. sucesso com a banca!"
