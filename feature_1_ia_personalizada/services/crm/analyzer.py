"""
feature_1_ia_personalizada/services/crm/analyzer.py
=====================================================
CRMAnalyzer — orquestra agregação, score e chamada ao Claude para análise CRM.

Fluxo:
  1. CRMDataAggregator  → coleta dados reais do cliente
  2. CRMScoreCalculator → score determinístico (sem Claude)
  3. Cache check        → se score não mudou e análise < 24h, retorna sem chamar Claude
  4. Claude Haiku       → gera resumo e ação sugerida
  5. UPDATE no banco    → persiste crm_nivel, crm_score, crm_resumo, crm_acao_sugerida, crm_analisado_em
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
from feature_1_ia_personalizada.services.ai.prompts import SYSTEM_PROMPT_CRM_ANALISE
from feature_1_ia_personalizada.services.crm.aggregator import CRMContexto, CRMDataAggregator
from feature_1_ia_personalizada.services.crm.score_calculator import calcular_score_crm
from shared.models.cliente import Cliente

logger = structlog.get_logger(__name__)

_MODELO_CRM = "claude-haiku-4-5-20251001"
_MAX_TOKENS_CRM = 300
_CACHE_TTL_HORAS = 24

# Palavras proibidas por compliance OAB (usadas na validação do output)
_PALAVRAS_PROIBIDAS = {"vitória", "vitoria", "ganhar", "perder", "probabilidade de"}


@dataclass
class CRMAnaliseResult:
    nivel: str
    score: int
    resumo: str
    acao_sugerida: str
    tokens_input: int
    tokens_output: int
    custo: Decimal
    cache_hit: bool = False


def _construir_input_claude(ctx: CRMContexto, nivel: str, score: int) -> str:
    msgs_txt = (
        "\n".join(
            f"  Cliente: {m.pergunta_cliente}\n  IA: {m.resposta_ia}" for m in ctx.ultimas_mensagens
        )
        or "  Sem mensagens recentes"
    )

    return (
        f"Cliente: {ctx.nome}"
        + (f", {ctx.profissao}" if ctx.profissao else "")
        + (f" em {ctx.empresa}" if ctx.empresa else "")
        + f"\nNível de satisfação: {nivel} (score {score}/100)"
        + f"\nNPS médio 3 meses: {ctx.nps_medio_3m if ctx.nps_medio_3m is not None else 'sem dados'}"
        + f" ({len(ctx.nps_historico)} avaliações)"
        + f"\nÚltimo contato: {ctx.dias_desde_ultimo_contato} dias atrás"
        + f"\nInterações com a IA nos últimos 30 dias: {ctx.total_interacoes_30d}"
        + f"\nEscalações: {ctx.escalacoes_pendentes} pendente(s),"
        + f" {ctx.escalacoes_rejeitadas_30d} rejeitada(s) nos últimos 30 dias"
        + f"\nHistórico de conversas:\n{msgs_txt}"
    )


def _validar_output(resumo: str, acao: str) -> None:
    texto = (resumo + " " + acao).lower()
    for palavra in _PALAVRAS_PROIBIDAS:
        if palavra in texto:
            raise ValueError(f"Output do Claude viola compliance OAB: contém '{palavra}'")


class CRMAnalyzer:
    def __init__(self, claude_client: ClaudeClient, db: AsyncSession) -> None:
        self._claude = claude_client
        self._db = db

    async def analisar_cliente(self, cliente_id: int, escritorio_id: int) -> CRMAnaliseResult:
        log = logger.bind(cliente_id=cliente_id, escritorio_id=escritorio_id)

        # 1. Agrega dados reais
        aggregator = CRMDataAggregator(self._db)
        ctx: CRMContexto = await aggregator.coletar_contexto_cliente(cliente_id, escritorio_id)

        # 2. Score determinístico
        crm_score = calcular_score_crm(ctx)

        # 3. Cache check — usa dados já carregados pelo aggregator (sem roundtrip extra)
        if (
            ctx.crm_analisado_em_anterior
            and ctx.crm_resumo_anterior
            and ctx.crm_score_anterior == crm_score.score
            and (datetime.now(UTC) - ctx.crm_analisado_em_anterior)
            < timedelta(hours=_CACHE_TTL_HORAS)
        ):
            log.info("crm.analyzer.cache_hit")
            return CRMAnaliseResult(
                nivel=crm_score.nivel,
                score=crm_score.score,
                resumo=ctx.crm_resumo_anterior,
                acao_sugerida=ctx.crm_acao_sugerida_anterior or "Nenhuma ação necessária",
                tokens_input=0,
                tokens_output=0,
                custo=Decimal("0"),
                cache_hit=True,
            )

        # 4. Chama Claude Haiku
        input_txt = _construir_input_claude(ctx, crm_score.nivel, crm_score.score)
        log.info("crm.analyzer.chamando_claude", score=crm_score.score, nivel=crm_score.nivel)

        try:
            resp = await self._claude._client.messages.create(
                model=_MODELO_CRM,
                max_tokens=_MAX_TOKENS_CRM,
                temperature=0.3,
                system=SYSTEM_PROMPT_CRM_ANALISE,
                messages=[{"role": "user", "content": input_txt}],
            )

            bloco = resp.content[0]
            texto = bloco.text if hasattr(bloco, "text") else ""
            dados = json.loads(texto)
            resumo = dados.get("resumo", "").strip()
            acao = dados.get("acao_sugerida", "Nenhuma ação necessária").strip()

            _validar_output(resumo, acao)

            tokens_in = resp.usage.input_tokens
            tokens_out = resp.usage.output_tokens
            custo = (Decimal(tokens_in) / 1_000_000 * Decimal("0.80")) + (
                Decimal(tokens_out) / 1_000_000 * Decimal("4.00")
            )

        except Exception as exc:
            # Graceful degradation: persiste score sem resumo
            log.warning("crm.analyzer.claude_falhou", erro=str(exc))
            resumo = ""
            acao = "Nenhuma ação necessária"
            tokens_in = tokens_out = 0
            custo = Decimal("0")

        # 5. Persiste resultado
        agora = datetime.now(UTC)
        await self._db.execute(
            update(Cliente)
            .where(Cliente.id == cliente_id)
            .values(
                crm_nivel=crm_score.nivel,
                crm_score=crm_score.score,
                crm_resumo=resumo or None,
                crm_acao_sugerida=acao or None,
                crm_analisado_em=agora,
            )
        )
        await self._db.commit()

        log.info("crm.analyzer.concluido", nivel=crm_score.nivel, score=crm_score.score)

        return CRMAnaliseResult(
            nivel=crm_score.nivel,
            score=crm_score.score,
            resumo=resumo,
            acao_sugerida=acao,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            custo=custo,
        )
