"""
Motor de humanização — faz a conversa da IA parecer conversa de gente.

Quatro peças:
  chunker         quebra a resposta em balões curtos; mata markdown/emoji/travessão
  cadencia        ritmo: leitura, "digitando", pausa entre balões (com jitter)
  buffer          espera a pessoa terminar de escrever e concatena as mensagens
  estilo          como a Clara escreve (system prompt) + regra de identidade

Regra de identidade (estilo.REGRA_IDENTIDADE): a IA soa humana, mas se
perguntarem se é uma IA, responde a verdade. Não remover — é o que protege a
marca e vira o gancho de venda.
"""

from feature_vendas.services.humanizacao.buffer import BufferMensagens
from feature_vendas.services.humanizacao.cadencia import (
    EntregaHumanizada,
    Ritmo,
    calcular_ritmo,
)
from feature_vendas.services.humanizacao.chunker import limpar, quebrar
from feature_vendas.services.humanizacao.estilo import (
    CLARA_PERSONA,
    ESTILO_WHATSAPP,
    REGRA_IDENTIDADE,
    system_prompt_clara,
)
from feature_vendas.services.humanizacao.evolution_humano import EvolutionHumano

__all__ = [
    "BufferMensagens",
    "EntregaHumanizada",
    "Ritmo",
    "calcular_ritmo",
    "limpar",
    "quebrar",
    "CLARA_PERSONA",
    "ESTILO_WHATSAPP",
    "REGRA_IDENTIDADE",
    "system_prompt_clara",
    "EvolutionHumano",
]
