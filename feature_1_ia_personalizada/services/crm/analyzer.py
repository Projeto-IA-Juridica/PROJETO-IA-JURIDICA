"""
feature_1_ia_personalizada/services/crm/analyzer.py
=====================================================
CRMAnalyzer — orquestra agregação e chamada ao Claude para análise CRM.

Fluxo:
  1. CRMDataAggregator  → coleta dados reais do cliente (conversa recente + sinais operacionais)
  2. Cache check        → se análise < 24h e sem interação nova, retorna sem chamar Claude
  3. Claude Haiku       → classifica o relacionamento (nível + score) e gera resumo e ação sugerida
  4. UPDATE no banco    → persiste crm_nivel, crm_score, crm_resumo, crm_acao_sugerida, crm_analisado_em
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
from shared.config.constants import CRM_NIVEL_FAIXAS
from shared.models.cliente import Cliente

logger = structlog.get_logger(__name__)

_MODELO_CRM = "claude-haiku-4-5-20251001"
_MAX_TOKENS_CRM = 500
_CACHE_TTL_HORAS = 24

# Palavras proibidas por compliance OAB (usadas na validação do output)
_PALAVRAS_PROIBIDAS = {"vitória", "vitoria", "ganhar", "perder", "probabilidade de"}

# Faixa de score válida por nível, derivada de CRM_NIVEL_FAIXAS
# (ex.: {"excelente": (76, 100), "satisfeito": (51, 75), ...})
_FAIXA_POR_NIVEL: dict[str, tuple[int, int]] = {}
_teto = 100
for _minimo, _nivel in CRM_NIVEL_FAIXAS:
    _FAIXA_POR_NIVEL[_nivel] = (_minimo, _teto)
    _teto = _minimo - 1


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


def _tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _construir_input_claude(ctx: CRMContexto) -> str:
    linhas_msgs = []
    for m in ctx.ultimas_mensagens:
        data_txt = f"[{_tz(m.data).strftime('%d/%m/%Y')}] " if m.data else ""
        linhas_msgs.append(f"  {data_txt}Cliente: {m.pergunta_cliente}\n  IA: {m.resposta_ia}")
    msgs_txt = "\n".join(linhas_msgs) or "  Sem mensagens recentes"

    return (
        f"Cliente: {ctx.nome}"
        + (f", {ctx.profissao}" if ctx.profissao else "")
        + (f" em {ctx.empresa}" if ctx.empresa else "")
        + f"\nÚltimo contato: {ctx.dias_desde_ultimo_contato} dias atrás"
        + f"\nInterações com a IA nos últimos 30 dias: {ctx.total_interacoes_30d}"
        + f"\nProcessos ativos: {len(ctx.processos_ativos)}"
        + f"\nEscalações: {ctx.escalacoes_pendentes} pendente(s),"
        + f" {ctx.escalacoes_rejeitadas_30d} rejeitada(s) nos últimos 30 dias"
        + f"\n\nConversa recente (ordem cronológica):\n{msgs_txt}"
    )


def _extrair_json(texto: str) -> dict:
    """Extrai o objeto JSON da resposta, tolerando cercas de código e texto ao redor."""
    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio == -1 or fim == -1 or fim <= inicio:
        raise ValueError("Resposta do Claude não contém JSON")
    dados = json.loads(texto[inicio : fim + 1])
    if not isinstance(dados, dict):
        raise ValueError("JSON da resposta não é um objeto")
    return dados


def _normalizar_classificacao(dados: dict) -> tuple[str, int]:
    """Valida o nível e força o score para dentro da faixa do nível."""
    nivel = str(dados.get("nivel", "")).strip().lower()
    if nivel not in _FAIXA_POR_NIVEL:
        raise ValueError(f"Nível inválido retornado pelo Claude: '{nivel}'")

    minimo, maximo = _FAIXA_POR_NIVEL[nivel]
    try:
        # Indexação direta (e não .get) para o mypy não ver `Any | None` em int();
        # a chave ausente cai no mesmo fallback, agora via KeyError.
        score = int(dados["score"])
    except (KeyError, TypeError, ValueError):
        score = (minimo + maximo) // 2
    score = max(minimo, min(maximo, score))
    return nivel, score


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

        # 2. Cache check — reutiliza a análise se for recente e não houver interação nova
        if (
            ctx.crm_analisado_em_anterior
            and ctx.crm_nivel_anterior
            and ctx.crm_resumo_anterior
            and ctx.crm_score_anterior is not None
            and (datetime.now(UTC) - _tz(ctx.crm_analisado_em_anterior))
            < timedelta(hours=_CACHE_TTL_HORAS)
            and (
                ctx.ultimo_contato_at is None
                or _tz(ctx.ultimo_contato_at) <= _tz(ctx.crm_analisado_em_anterior)
            )
        ):
            log.info("crm.analyzer.cache_hit")
            return CRMAnaliseResult(
                nivel=ctx.crm_nivel_anterior,
                score=ctx.crm_score_anterior,
                resumo=ctx.crm_resumo_anterior,
                acao_sugerida=ctx.crm_acao_sugerida_anterior or "Nenhuma ação necessária",
                tokens_input=0,
                tokens_output=0,
                custo=Decimal("0"),
                cache_hit=True,
            )

        # 3. Chama Claude Haiku — classifica o relacionamento pela conversa recente
        input_txt = _construir_input_claude(ctx)
        log.info("crm.analyzer.chamando_claude", mensagens=len(ctx.ultimas_mensagens))

        try:
            resp = await self._claude._client.messages.create(
                model=_MODELO_CRM,
                max_tokens=_MAX_TOKENS_CRM,
                temperature=0.2,
                system=SYSTEM_PROMPT_CRM_ANALISE,
                messages=[{"role": "user", "content": input_txt}],
            )

            bloco = resp.content[0]
            texto = bloco.text if hasattr(bloco, "text") else ""
            dados = _extrair_json(texto)
            nivel, score = _normalizar_classificacao(dados)
            resumo = str(dados.get("resumo", "")).strip()
            acao = str(dados.get("acao_sugerida", "Nenhuma ação necessária")).strip()

            _validar_output(resumo, acao)

            tokens_in = resp.usage.input_tokens
            tokens_out = resp.usage.output_tokens
            custo = (Decimal(tokens_in) / 1_000_000 * Decimal("0.80")) + (
                Decimal(tokens_out) / 1_000_000 * Decimal("4.00")
            )

        except Exception as exc:
            # Sem classificação do modelo não há o que persistir — a análise
            # anterior (se existir) permanece intacta no banco.
            log.warning("crm.analyzer.claude_falhou", erro=str(exc))
            raise RuntimeError("Análise CRM indisponível no momento") from exc

        # 4. Persiste resultado
        agora = datetime.now(UTC)
        await self._db.execute(
            update(Cliente)
            .where(Cliente.id == cliente_id)
            .values(
                crm_nivel=nivel,
                crm_score=score,
                crm_resumo=resumo or None,
                crm_acao_sugerida=acao or None,
                crm_analisado_em=agora,
            )
        )
        await self._db.commit()

        log.info("crm.analyzer.concluido", nivel=nivel, score=score)

        return CRMAnaliseResult(
            nivel=nivel,
            score=score,
            resumo=resumo,
            acao_sugerida=acao,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            custo=custo,
        )
