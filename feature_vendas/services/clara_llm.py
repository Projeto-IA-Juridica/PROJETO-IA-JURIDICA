"""
O cérebro da Clara — chamada ao modelo, tunada para MÁXIMA inteligência.

Diferente do wrapper do produto (que usa Sonnet, calibrado para custo em alto
volume de clientes), aqui a conversa é de VENDAS: baixo volume, altíssimo valor
por conversa (cada lead pode virar R$ 997+/mês recorrente). Então vale o modelo
mais forte que o projeto usa — o de escalação (Opus) — e uma janela de resposta
maior para ela raciocinar.

Isolado: usa o SDK Anthropic direto (mesmo padrão do titulo_gerador do produto),
sem passar pelo ClaudeClient. Assim a Clara pode ter modelo e parâmetros próprios
sem alterar nada do produto.

Prompt caching:
  - o system prompt (persona + estilo + contexto do lead) é marcado para cache;
    da 2ª mensagem em diante a maior parte dos tokens de entrada vira cache hit.
  - o último turno do histórico também é marcado, encadeando o cache da conversa.
"""

from __future__ import annotations

from typing import Any

import anthropic
import structlog
from anthropic.types import TextBlock

from shared.config.settings import settings

logger = structlog.get_logger(__name__)

# Modelo: o mais capaz que o projeto configura (Opus, o de escalação jurídica).
# Ler de settings mantém alinhado com as escolhas de modelo do produto.
_MODELO = settings.MODELO_ESCALACAO
_MAX_TOKENS = 700  # resposta de vendas é curta, mas deixa espaço para raciocínio
_TEMPERATURE = 0.7  # conversa humana pede variação; não é tarefa determinística


def _system_blocks(system_prompt: str) -> list[dict[str, Any]]:
    """System prompt como bloco único cacheável."""
    return [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _messages(historico: list[dict[str, str]], mensagem: str) -> list[dict[str, Any]]:
    """
    Histórico + mensagem atual. Marca o último turno anterior para cache, para
    que a conversa acumulada vire cache hit na próxima chamada.
    """
    msgs: list[dict[str, Any]] = []
    for i, m in enumerate(historico):
        bloco: dict[str, Any] = {"type": "text", "text": m["content"]}
        if i == len(historico) - 1:
            bloco["cache_control"] = {"type": "ephemeral"}
        msgs.append({"role": m["role"], "content": [bloco]})
    msgs.append({"role": "user", "content": mensagem})
    return msgs


class ClaraLLM:
    """Chamada ao modelo para a persona de vendas. Instanciar uma vez por task."""

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def responder(
        self,
        *,
        system_prompt: str,
        historico: list[dict[str, str]],
        mensagem: str,
    ) -> str:
        try:
            resposta = await self._client.messages.create(
                model=_MODELO,
                max_tokens=_MAX_TOKENS,
                temperature=_TEMPERATURE,
                system=_system_blocks(system_prompt),  # type: ignore[arg-type]
                messages=_messages(historico, mensagem),  # type: ignore[arg-type]
            )
            for bloco in resposta.content:
                if isinstance(bloco, TextBlock):
                    return bloco.text.strip()
            return ""
        except Exception as exc:
            logger.error("clara_llm_falhou", erro=str(exc))
            # Fallback seguro: nunca deixa o lead sem resposta por erro do modelo.
            return "opa, me perdi aqui um segundo. pode repetir?"
