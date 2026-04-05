# feature_1_ia_personalizada/services/ai/hub_advogado_classifier.py
"""
Classificador de Intenção do Hub do Advogado.

Classifica a mensagem do advogado em uma das 7 intenções suportadas
usando uma combinação de heurísticas rápidas (sem IA) e Claude Haiku
quando necessário.

Ordem de decisão:
  1. tipo_media == "document" → ANALISE_PETICAO (sem Claude)
  2. Palavras-chave de status → STATUS_ESCRITORIO (sem Claude)
  3. Claude Haiku com prompt de classificação (timeout 5s)
  4. Fallback: DUVIDA_JURIDICA
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any

import anthropic
import structlog

from shared.config.settings import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Modelo leve para classificação (barato e rápido)
# ---------------------------------------------------------------------------

_MODELO_CLASSIFICACAO = "claude-haiku-4-5-20251001"
_MAX_TOKENS_CLASSIFICACAO = 150
_TIMEOUT_CLASSIFICACAO = 5.0  # segundos

# ---------------------------------------------------------------------------
# Heurísticas de status — palavras-chave que dispensam chamada ao Claude
# ---------------------------------------------------------------------------

_RE_STATUS = re.compile(
    r"\b(status|dashboard|resumo do dia|como est[aá] o escritório|métricas|hoje)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Enum público
# ---------------------------------------------------------------------------


class IntencaoAdvogado(str, Enum):
    RESUMO_PROCESSO = "resumo_processo"
    ANALISE_PETICAO = "analise_peticao"
    PESQUISA_JURISPRUDENCIA = "pesquisa_jurisprudencia"
    INSIGHT_CLIENTE = "insight_cliente"
    DUVIDA_JURIDICA = "duvida_juridica"
    STATUS_ESCRITORIO = "status_escritorio"
    RASCUNHO_MENSAGEM = "rascunho_mensagem"


# Prompt de classificação — injetado em SYSTEM; mensagem do advogado vai em USER
_SYSTEM_PROMPT_CLASSIFICADOR = (
    "Você é um classificador de intenções jurídicas. "
    "Dado o texto de um advogado, retorne EXCLUSIVAMENTE um JSON válido "
    "sem texto adicional, sem markdown.\n\n"
    "Formato obrigatório:\n"
    '{"intencao": "<valor>", "entidades": {"cliente_nome": null, '
    '"processo_cnj": null, "query_juris": null}}\n\n'
    "Valores válidos para intencao:\n"
    "  resumo_processo        — advogado quer resumo ou status de um processo\n"
    "  analise_peticao        — advogado envia ou menciona análise de peça jurídica\n"
    "  pesquisa_jurisprudencia — advogado busca jurisprudência / precedente\n"
    "  insight_cliente        — advogado quer análise CRM ou recomendação sobre cliente\n"
    "  duvida_juridica        — dúvida jurídica geral (artigo, prazo, procedimento)\n"
    "  status_escritorio      — quer métricas do dia / dashboard\n"
    "  rascunho_mensagem      — quer rascunho de mensagem para enviar a cliente\n\n"
    "Preencha entidades somente quando identificar claramente:\n"
    "  cliente_nome: nome do cliente mencionado\n"
    "  processo_cnj: número CNJ mencionado (formato 0000000-00.0000.0.00.0000)\n"
    "  query_juris: tema/assunto de jurisprudência mencionado"
)


# ---------------------------------------------------------------------------
# Classificador
# ---------------------------------------------------------------------------


class HubAdvogadoClassificador:
    """
    Classifica a intenção de uma mensagem do advogado.

    Uso:
        classificador = HubAdvogadoClassificador()
        resultado = await classificador.classificar(mensagem, tipo_media)
        # resultado.intencao, resultado.entidades
    """

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def classificar(
        self,
        mensagem: str,
        tipo_media: str = "texto",
    ) -> ClassificacaoAdvogado:
        """
        Classifica a mensagem do advogado.

        Args:
            mensagem: Texto da mensagem (vazio se for mídia pura).
            tipo_media: "texto" | "audio_transcrito" | "document" | "image"

        Returns:
            ClassificacaoAdvogado com intencao e entidades extraídas.
        """
        # Regra 1: documento PDF → análise de petição sem Claude
        if tipo_media == "document":
            logger.debug("classificacao_documento_direto")
            return ClassificacaoAdvogado(
                intencao=IntencaoAdvogado.ANALISE_PETICAO,
                entidades={},
            )

        # Regra 2: heurística de status (sem Claude)
        if mensagem and _RE_STATUS.search(mensagem):
            logger.debug("classificacao_status_heuristica")
            return ClassificacaoAdvogado(
                intencao=IntencaoAdvogado.STATUS_ESCRITORIO,
                entidades={},
            )

        # Regra 3: Claude Haiku com timeout
        if mensagem:
            try:
                resultado = await self._classificar_com_claude(mensagem)
                return resultado
            except Exception as exc:
                logger.warning(
                    "classificacao_claude_falhou_fallback",
                    erro=str(exc),
                    mensagem_trunc=mensagem[:80],
                )

        # Fallback
        return ClassificacaoAdvogado(
            intencao=IntencaoAdvogado.DUVIDA_JURIDICA,
            entidades={},
        )

    async def _classificar_com_claude(self, mensagem: str) -> ClassificacaoAdvogado:
        import asyncio

        resposta = await asyncio.wait_for(
            self._client.messages.create(
                model=_MODELO_CLASSIFICACAO,
                max_tokens=_MAX_TOKENS_CLASSIFICACAO,
                system=_SYSTEM_PROMPT_CLASSIFICADOR,
                messages=[{"role": "user", "content": mensagem}],
            ),
            timeout=_TIMEOUT_CLASSIFICACAO,
        )

        texto = resposta.content[0].text.strip()
        dados = json.loads(texto)

        intencao_str = dados.get("intencao", "duvida_juridica")
        try:
            intencao = IntencaoAdvogado(intencao_str)
        except ValueError:
            logger.warning("classificacao_intencao_invalida", valor=intencao_str)
            intencao = IntencaoAdvogado.DUVIDA_JURIDICA

        entidades: dict[str, Any] = dados.get("entidades") or {}

        logger.info(
            "classificacao_hub_advogado",
            intencao=intencao.value,
            tem_cliente=bool(entidades.get("cliente_nome")),
            tem_cnj=bool(entidades.get("processo_cnj")),
        )

        return ClassificacaoAdvogado(intencao=intencao, entidades=entidades)


# ---------------------------------------------------------------------------
# Dataclass de resultado
# ---------------------------------------------------------------------------


from dataclasses import dataclass, field


@dataclass
class ClassificacaoAdvogado:
    intencao: IntencaoAdvogado
    entidades: dict[str, Any] = field(default_factory=dict)

    @property
    def cliente_nome(self) -> str | None:
        return self.entidades.get("cliente_nome")

    @property
    def processo_cnj(self) -> str | None:
        return self.entidades.get("processo_cnj")

    @property
    def query_juris(self) -> str | None:
        return self.entidades.get("query_juris")
