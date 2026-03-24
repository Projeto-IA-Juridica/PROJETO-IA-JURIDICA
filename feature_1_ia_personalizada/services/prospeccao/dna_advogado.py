"""
feature_1_ia_personalizada/services/prospeccao/dna_advogado.py

Gera e persiste o DNA de especialização do escritório a partir do histórico
de processos no banco. Resultado salvo em escritorio.dna_prospeccao (JSONB)
e cacheado no Redis (TTL 6h).

O DNA determina:
  - Quais tipos de ação o escritório domina
  - Se o perfil é B2B (empresa) ou B2C (pessoa física) ou ambos
  - Setores-alvo para prospecção
  - Diferenciais para abordagem inicial
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
from feature_1_ia_personalizada.services.ai.prompts import SYSTEM_PROMPT_DNA_ADVOGADO
from shared.models.escritorio import Escritorio
from shared.models.processo import Processo

logger = structlog.get_logger(__name__)

_MODELO_HAIKU = "claude-haiku-4-5-20251001"
_MAX_TOKENS_DNA = 600
_MIN_PROCESSOS = 5
_CACHE_TTL_S = 60 * 60 * 6  # 6h


@dataclass
class DNAEscritorio:
    escritorio_id: int
    especialidades: list[str] = field(default_factory=list)
    setores_alvo: list[str] = field(default_factory=list)
    # 'empresa' | 'pessoa' | 'ambos'
    tipo_lead_predominante: str = "ambos"
    perfil_cliente_ideal: str = ""
    diferenciais: list[str] = field(default_factory=list)
    top_tipos_acao: list[dict[str, Any]] = field(default_factory=list)
    dados_insuficientes: bool = False
    gerado_em: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "escritorio_id": self.escritorio_id,
            "especialidades": self.especialidades,
            "setores_alvo": self.setores_alvo,
            "tipo_lead_predominante": self.tipo_lead_predominante,
            "perfil_cliente_ideal": self.perfil_cliente_ideal,
            "diferenciais": self.diferenciais,
            "top_tipos_acao": self.top_tipos_acao,
            "dados_insuficientes": self.dados_insuficientes,
            "gerado_em": self.gerado_em.isoformat() if self.gerado_em else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DNAEscritorio:
        gerado_em = None
        if data.get("gerado_em"):
            gerado_em = datetime.fromisoformat(data["gerado_em"])
        return cls(
            escritorio_id=data["escritorio_id"],
            especialidades=data.get("especialidades", []),
            setores_alvo=data.get("setores_alvo", []),
            tipo_lead_predominante=data.get("tipo_lead_predominante", "ambos"),
            perfil_cliente_ideal=data.get("perfil_cliente_ideal", ""),
            diferenciais=data.get("diferenciais", []),
            top_tipos_acao=data.get("top_tipos_acao", []),
            dados_insuficientes=data.get("dados_insuficientes", False),
            gerado_em=gerado_em,
        )


class DNAAdvogadoService:
    """
    Gera e recupera o DNA de especialização de um escritório.

    Uso:
        service = DNAAdvogadoService(claude_client, redis)
        dna = await service.obter_dna(escritorio_id, db)
    """

    def __init__(self, claude: ClaudeClient, redis: Any) -> None:
        self._claude = claude
        self._redis = redis

    # ------------------------------------------------------------------
    # Interface pública
    # ------------------------------------------------------------------

    async def obter_dna(
        self, escritorio_id: int, db: AsyncSession
    ) -> DNAEscritorio:
        """
        Retorna o DNA do escritório. Ordem de resolução:
          1. Cache Redis (TTL 6h)
          2. escritorio.dna_prospeccao (banco)
          3. Gera novo DNA via Claude
        """
        cached = await self._get_cache(escritorio_id)
        if cached is not None:
            logger.debug("dna.cache_hit", escritorio_id=escritorio_id)
            return cached

        dna_banco, nome = await self._ler_banco(escritorio_id, db)
        if dna_banco is not None:
            await self._set_cache(escritorio_id, dna_banco)
            return dna_banco

        return await self.gerar_dna(escritorio_id, db, nome_escritorio=nome)

    async def gerar_dna(
        self,
        escritorio_id: int,
        db: AsyncSession,
        nome_escritorio: str | None = None,
    ) -> DNAEscritorio:
        """
        Força regeneração do DNA — invalida cache e recalcula.
        Chamado na primeira vez ou quando o advogado pede atualização.
        """
        await self._invalidar_cache(escritorio_id)

        stats = await self._calcular_stats(escritorio_id, db)
        total = sum(r["contagem"] for r in stats)

        if total < _MIN_PROCESSOS:
            logger.info(
                "dna.dados_insuficientes",
                escritorio_id=escritorio_id,
                total=total,
            )
            return DNAEscritorio(
                escritorio_id=escritorio_id,
                dados_insuficientes=True,
                top_tipos_acao=stats,
            )

        # Se nome não foi passado (chamada direta ao gerar_dna), busca agora
        if nome_escritorio is None:
            nome_escritorio = await self._obter_nome_escritorio(escritorio_id, db)

        dna = await self._gerar_com_claude(escritorio_id, stats, db, nome_escritorio)
        await self._persistir(escritorio_id, dna, db)
        await self._set_cache(escritorio_id, dna)
        return dna

    # ------------------------------------------------------------------
    # Internos — queries
    # ------------------------------------------------------------------

    async def _calcular_stats(
        self, escritorio_id: int, db: AsyncSession
    ) -> list[dict[str, Any]]:
        """Retorna top 10 tipos de ação com contagem e percentual."""
        stmt = (
            select(
                Processo.tipo_acao,
                func.count().label("contagem"),
            )
            .where(
                Processo.escritorio_id == escritorio_id,
                Processo.tipo_acao.isnot(None),
            )
            .group_by(Processo.tipo_acao)
            .order_by(func.count().desc())
            .limit(10)
        )
        rows = (await db.execute(stmt)).all()
        total = sum(r.contagem for r in rows)

        return [
            {
                "tipo": r.tipo_acao,
                "contagem": r.contagem,
                "percentual": round((r.contagem / total * 100), 1) if total else 0,
            }
            for r in rows
        ]

    async def _calcular_polo(
        self, escritorio_id: int, db: AsyncSession
    ) -> dict[str, int]:
        """Retorna distribuição autor/réu/terceiro."""
        stmt = (
            select(
                Processo.polo_cliente,
                func.count().label("contagem"),
            )
            .where(Processo.escritorio_id == escritorio_id)
            .group_by(Processo.polo_cliente)
        )
        rows = (await db.execute(stmt)).all()
        return {r.polo_cliente: r.contagem for r in rows if r.polo_cliente}

    # ------------------------------------------------------------------
    # Internos — Claude
    # ------------------------------------------------------------------

    async def _gerar_com_claude(
        self,
        escritorio_id: int,
        stats: list[dict],
        db: AsyncSession,
        nome_escritorio: str = "Escritório",
    ) -> DNAEscritorio:
        polo_dist = await self._calcular_polo(escritorio_id, db)

        prompt = SYSTEM_PROMPT_DNA_ADVOGADO.format(
            nome_escritorio=nome_escritorio,
            total_processos=sum(r["contagem"] for r in stats),
            top_tipos_acao=json.dumps(stats, ensure_ascii=False),
            distribuicao_polo=json.dumps(polo_dist, ensure_ascii=False),
        )

        try:
            resultado = await self._claude.chamar_direto(
                system_prompt=prompt,
                mensagem="Gere o DNA do escritório.",
                modelo=_MODELO_HAIKU,
                max_tokens=_MAX_TOKENS_DNA,
                temperature=0.2,
            )
            dados = json.loads(resultado["resposta"])
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(
                "dna.parse_error",
                escritorio_id=escritorio_id,
                error=str(exc),
            )
            # Fallback: DNA parcial sem análise Claude
            return DNAEscritorio(
                escritorio_id=escritorio_id,
                top_tipos_acao=stats,
                dados_insuficientes=False,
                gerado_em=datetime.now(timezone.utc),
            )

        logger.info(
            "dna.gerado",
            escritorio_id=escritorio_id,
            tipo_lead=dados.get("tipo_lead_predominante"),
            tokens=resultado["tokens_input"] + resultado["tokens_output"],
        )

        return DNAEscritorio(
            escritorio_id=escritorio_id,
            especialidades=dados.get("especialidades", []),
            setores_alvo=dados.get("setores_alvo", []),
            tipo_lead_predominante=dados.get("tipo_lead_predominante", "ambos"),
            perfil_cliente_ideal=dados.get("perfil_cliente_ideal", ""),
            diferenciais=dados.get("diferenciais", []),
            top_tipos_acao=stats,
            dados_insuficientes=False,
            gerado_em=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Internos — persistência
    # ------------------------------------------------------------------

    async def _persistir(
        self, escritorio_id: int, dna: DNAEscritorio, db: AsyncSession
    ) -> None:
        await db.execute(
            update(Escritorio)
            .where(Escritorio.id == escritorio_id)
            .values(dna_prospeccao=dna.to_dict())
        )
        await db.commit()

    async def _ler_banco(
        self, escritorio_id: int, db: AsyncSession
    ) -> tuple[DNAEscritorio | None, str]:
        """Retorna (dna, nome_escritorio) em uma única query."""
        stmt = select(Escritorio.dna_prospeccao, Escritorio.nome).where(
            Escritorio.id == escritorio_id
        )
        row = (await db.execute(stmt)).one_or_none()
        if row is None:
            return None, "Escritório"
        nome = row.nome or "Escritório"
        if row.dna_prospeccao:
            try:
                return DNAEscritorio.from_dict(row.dna_prospeccao), nome
            except (KeyError, TypeError) as exc:
                logger.debug(
                    "dna.banco_parse_error",
                    escritorio_id=escritorio_id,
                    error=str(exc),
                )
        return None, nome

    async def _obter_nome_escritorio(
        self, escritorio_id: int, db: AsyncSession
    ) -> str:
        """Usado apenas quando gerar_dna é chamado diretamente (sem passar por obter_dna)."""
        stmt = select(Escritorio.nome).where(Escritorio.id == escritorio_id)
        return (await db.execute(stmt)).scalar_one_or_none() or "Escritório"

    # ------------------------------------------------------------------
    # Internos — cache
    # ------------------------------------------------------------------

    def _cache_key(self, escritorio_id: int) -> str:
        return f"dna:{escritorio_id}"

    async def _get_cache(self, escritorio_id: int) -> DNAEscritorio | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(self._cache_key(escritorio_id))
            if raw:
                return DNAEscritorio.from_dict(json.loads(raw))
        except (TypeError, KeyError) as exc:
            logger.debug(
                "dna.cache_parse_error",
                escritorio_id=escritorio_id,
                error=str(exc),
            )
        except Exception as exc:
            logger.debug("dna.cache_error", escritorio_id=escritorio_id, error=str(exc))
        return None

    async def _set_cache(self, escritorio_id: int, dna: DNAEscritorio) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.setex(
                self._cache_key(escritorio_id),
                _CACHE_TTL_S,
                json.dumps(dna.to_dict()),
            )
        except Exception:
            pass

    async def _invalidar_cache(self, escritorio_id: int) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.delete(self._cache_key(escritorio_id))
        except Exception:
            pass
