"""
feature_1_ia_personalizada/services/ai/juridical_translator.py

Traduz jargão jurídico para português claro usando Claude Haiku.

Uso:
    texto_simples = JuridicalTranslator.traduzir_andamento(texto_juridico)

Em caso de falha (API indisponível, timeout, etc.) retorna o texto original
sem interromper o pipeline de monitoramento.
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

_PROMPT_SISTEMA = (
    "Você é um assistente jurídico especializado em simplificar linguagem jurídica "
    "para clientes leigos. Reescreva o andamento processual abaixo em português "
    "claro e direto, em no máximo 2 frases curtas. Não use jargão jurídico. "
    "Não adicione explicações, apenas reescreva."
)


class JuridicalTranslator:
    """Simplifica andamentos judiciais para linguagem acessível via Claude."""

    @staticmethod
    def traduzir_andamento(texto: str) -> str:
        """
        Recebe um andamento limpo (sem HTML) e retorna versão em português simples.

        Usa Claude Haiku (modelo mais rápido e barato) com max_tokens=150.
        Em caso de qualquer erro, retorna o `texto` original como fallback
        para não interromper o pipeline de monitoramento.
        """
        if not texto or not texto.strip():
            return texto

        try:
            import anthropic
            from shared.config.settings import settings

            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            resposta = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                messages=[
                    {
                        "role": "user",
                        "content": f"{_PROMPT_SISTEMA}\n\nAndamento:\n{texto.strip()}",
                    }
                ],
            )
            traduzido = resposta.content[0].text.strip()
            logger.info(
                "juridical_translator_ok",
                original_len=len(texto),
                traduzido_len=len(traduzido),
            )
            return traduzido

        except Exception as exc:
            logger.warning(
                "juridical_translator_erro_fallback",
                erro=str(exc),
                texto_original=texto[:80],
            )
            return texto
