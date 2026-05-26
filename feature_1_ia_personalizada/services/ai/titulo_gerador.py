"""
Geração de título de conversa com Claude Haiku.

Chamado de forma assíncrona (fire-and-forget) na primeira mensagem de cada
conversa. Usa Haiku porque o custo é ~60× menor que Opus e a tarefa é simples.
"""

from __future__ import annotations

import anthropic
import structlog

from shared.config.settings import settings

logger = structlog.get_logger(__name__)

_MODELO = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 25

_PROMPT_SISTEMA = (
    "Você é um assistente que cria títulos concisos para conversas jurídicas. "
    "Responda APENAS com o título — sem aspas, sem pontuação final, sem explicações."
)

_PROMPT_USUARIO = (
    "Crie um título de até 6 palavras para esta pergunta jurídica:\n\n{mensagem}"
)


async def gerar_titulo_conversa(mensagem: str) -> str:
    """
    Gera um título curto para uma conversa com base na primeira mensagem.

    Returns:
        Título com no máximo 120 caracteres. Em caso de falha retorna
        os primeiros 80 chars da mensagem (fallback seguro).
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        resposta = await client.messages.create(
            model=_MODELO,
            max_tokens=_MAX_TOKENS,
            system=_PROMPT_SISTEMA,
            messages=[
                {
                    "role": "user",
                    "content": _PROMPT_USUARIO.format(mensagem=mensagem[:600]),
                }
            ],
        )
        titulo = resposta.content[0].text.strip().strip('"').strip("'").rstrip(".")
        logger.info(
            "titulo_gerado",
            modelo=_MODELO,
            tokens_input=resposta.usage.input_tokens,
            tokens_output=resposta.usage.output_tokens,
        )
        return titulo[:120]
    except Exception as exc:
        logger.warning("titulo_geracao_falhou", erro=str(exc))
        return mensagem[:80]
