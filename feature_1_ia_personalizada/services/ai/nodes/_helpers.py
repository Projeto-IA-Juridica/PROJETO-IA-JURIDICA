"""
Helpers de banco de dados reutilizados por múltiplos nós do orquestrador.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from feature_1_ia_personalizada.services.ai.prompts import gerar_instrucao_persona
from feature_1_ia_personalizada.services.ai.state import ConversationState, NodeDeps
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio
from shared.models.interacao import Interacao
from shared.models.processo import Processo

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from redis.asyncio import Redis

from sqlalchemy import select

logger = structlog.get_logger(__name__)


async def obter_escritorio_cliente(
    session: AsyncSession,
    escritorio_id: int,
    cliente_id: int,
) -> tuple[Escritorio | None, Cliente | None]:
    escritorio = await session.get(Escritorio, escritorio_id)
    cliente = await session.get(Cliente, cliente_id)
    return escritorio, cliente


async def listar_processos_ativos(
    session: AsyncSession,
    escritorio_id: int,
    cliente_id: int,
) -> list[Processo]:
    stmt = (
        select(Processo)
        .where(
            Processo.cliente_id == cliente_id,
            Processo.escritorio_id == escritorio_id,
            Processo.monitoramento_ativo.is_(True),
        )
        .order_by(Processo.data_ultimo_andamento.desc().nullslast())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def obter_persona(
    redis: Redis,
    escritorio_id: int,
    escritorio: Escritorio | None,
) -> str:
    """Retorna o bloco XML de persona. Cacheado no Redis por 1h."""
    cache_key = f"escritorio_persona:{escritorio_id}"
    try:
        cached = await redis.get(cache_key)
        if cached:
            return str(cached)
    except Exception:
        pass

    persona_nome = "Assistente Jurídico"
    persona_tom = "neutro"
    if escritorio:
        persona_nome = escritorio.persona_nome or persona_nome
        persona_tom = escritorio.persona_tom or persona_tom

    instrucao = gerar_instrucao_persona(persona_nome, persona_tom)

    try:
        await redis.set(cache_key, instrucao, ex=3600)
    except Exception:
        pass

    return instrucao


async def salvar_interacao(
    session: AsyncSession,
    state: ConversationState,
    resposta_final: str,
    tokens: dict[str, Any],
    custo: Decimal,
    metadata_extra: dict[str, Any] | None = None,
) -> None:
    metadata: dict[str, Any] = metadata_extra or {}
    if state.get("usando_fallback"):
        metadata["usando_fallback"] = True

    interacao = Interacao(
        escritorio_id=state["escritorio_id"],
        cliente_id=state["cliente_id"],
        processo_id=state.get("processo_id"),
        tipo=state.get("tipo_mensagem", "texto"),
        direcao="saida",
        mensagem_cliente=state["mensagem_original"],
        mensagem_ia=resposta_final,
        tokens_input=tokens.get("input", 0),
        tokens_output=tokens.get("output", 0),
        custo_estimado=custo,
        modelo_ia=state.get("modelo_ia_usado", "claude"),
        metadata_json=metadata or None,
    )
    session.add(interacao)
    await session.commit()


async def buscar_rag(
    state: ConversationState,
    deps: NodeDeps,
    contexto_processo: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Chama o RAGRetriever de forma segura. Retorna (contexto_str, docs_com_score)."""
    if not deps.rag:
        return "", []
    try:
        return await deps.rag.buscar_com_scores(
            query=state["mensagem_original"],
            escritorio_id=state["escritorio_id"],
            contexto_processo=contexto_processo,
        )
    except Exception as exc:
        logger.warning("rag_busca_falhou_graceful", erro=str(exc))
        return "", []
