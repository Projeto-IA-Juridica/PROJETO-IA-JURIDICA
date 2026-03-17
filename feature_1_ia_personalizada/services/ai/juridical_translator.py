"""
feature_1_ia_personalizada/services/ai/juridical_translator.py

Traduz jargão jurídico para português claro usando Claude Haiku.

Métodos disponíveis:
    JuridicalTranslator.traduzir_andamento(texto)
        → tradução simples, sem contexto histórico (comportamento original)

    JuridicalTranslator.traduzir_com_contexto(andamento, fase_atual, historico,
                                               tipo_acao, polo_cliente,
                                               nome_escritorio, nome_cliente)
        → resumo contextualizado usando SYSTEM_PROMPT_ANDAMENTO_CONTEXTUALIZADO,
          adequado para envio direto via WhatsApp

Em caso de falha (API indisponível, timeout, etc.) ambos retornam o texto original
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
            import anthropic  # noqa: I001
            from shared.config.settings import settings  # noqa: I001

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
            bloco = resposta.content[0]
            traduzido = getattr(bloco, "text", str(bloco)).strip()
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

    @staticmethod
    def traduzir_com_contexto(
        andamento: str,
        fase_atual: str,
        historico: str,
        tipo_acao: str,
        polo_cliente: str,
        nome_escritorio: str = "do escritório",
        nome_cliente: str = "cliente",
    ) -> str:
        """
        Gera resumo contextualizado do andamento usando SYSTEM_PROMPT_ANDAMENTO_CONTEXTUALIZADO.

        Diferente de traduzir_andamento(), este método recebe o contexto histórico
        do processo (fase atual, andamentos anteriores, tipo de ação) e produz
        uma mensagem completa e humanizada pronta para envio via WhatsApp.

        Usa Claude Haiku com max_tokens=400 (suficiente para 4 parágrafos curtos).
        Em caso de falha, retorna o andamento original como fallback.

        Args:
            andamento:       Texto limpo do novo andamento detectado.
            fase_atual:      Fase processual classificada pelo ProcessoStateManager.
            historico:       String enumerada gerada por gerar_contexto_historico().
            tipo_acao:       Tipo da ação judicial (ex: "Ação de Cobrança").
            polo_cliente:    Polo do cliente no processo (ex: "autor", "réu").
            nome_escritorio: Nome do escritório para personalização do prompt.
            nome_cliente:    Primeiro nome do cliente para personalização.
        """
        if not andamento or not andamento.strip():
            return andamento

        try:
            import anthropic  # noqa: I001
            from shared.config.settings import settings  # noqa: I001
            from feature_1_ia_personalizada.services.ai.prompts import (  # noqa: I001
                SYSTEM_PROMPT_ANDAMENTO_CONTEXTUALIZADO,
            )

            system = SYSTEM_PROMPT_ANDAMENTO_CONTEXTUALIZADO.format(
                nome_escritorio=nome_escritorio,
                nome_cliente=nome_cliente,
                tipo_acao=tipo_acao or "não informado",
                fase_processual=fase_atual,
                polo_cliente=polo_cliente,
                historico_andamentos=historico,
                novo_andamento=andamento.strip(),
            )

            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            resposta = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                system=system,
                messages=[
                    {
                        "role": "user",
                        "content": "Escreva o resumo do andamento para o cliente.",
                    }
                ],
            )
            bloco = resposta.content[0]
            resumo = getattr(bloco, "text", str(bloco)).strip()
            logger.info(
                "juridical_translator_contexto_ok",
                fase=fase_atual,
                tokens_input=resposta.usage.input_tokens,
                tokens_output=resposta.usage.output_tokens,
            )
            return resumo

        except Exception as exc:
            logger.warning(
                "juridical_translator_contexto_erro_fallback",
                erro=str(exc),
                andamento=andamento[:80],
            )
            return andamento
