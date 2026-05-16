"""
Rotas de Escalações — Human-in-the-Loop
========================================
feature_1_ia_personalizada/api/routes/escalacoes.py

Permite que advogados visualizem, aprovem ou rejeitem escalações geradas
pelo EscalacaoManager quando a IA não atingiu confiança suficiente para
responder autonomamente.

Fluxo:
  1. Orchestrador detecta baixa confiança → EscalacaoManager cria Interacao
     com tipo="escalacao", metadata_json.escalacao.status="pendente"
     e notifica advogados via WhatsApp.
  2. Advogado abre este endpoint para listar escalações pendentes.
  3. Advogado aprova (opcionalmente editando a sugestão da IA) ou rejeita.
  4. Ao aprovar: resposta é enviada ao cliente via WhatsApp e status → "aprovada".
  5. Ao rejeitar: status → "rejeitada", sem envio.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.api.middleware.auth import (
    get_advogado_id,
    get_escritorio_id_advogado,
    require_advogado,
)
from feature_1_ia_personalizada.services.messaging.evolution_client import EvolutionClient
from shared.config.settings import settings
from shared.database.session import get_db
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio
from shared.models.interacao import Interacao

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/escalacoes",
    tags=["Escalações"],
    dependencies=[Depends(require_advogado)],
)

_STATUS_VALIDOS = {"pendente", "aprovada", "rejeitada"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class EscalacaoItem(BaseModel):
    id: int
    cliente_id: int
    cliente_nome: str | None
    mensagem_cliente: str | None
    sugestao_resposta: str | None
    motivo: str | None
    status_escalacao: str
    created_at: datetime

    class Config:
        from_attributes = True


class AprovarRequest(BaseModel):
    resposta_final: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extrair_escalacao(metadata: dict | None) -> dict[str, Any]:
    if not metadata:
        return {}
    return metadata.get("escalacao", {})


def _get_evolution() -> EvolutionClient:
    return EvolutionClient(settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY)


# ---------------------------------------------------------------------------
# GET /escalacoes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[EscalacaoItem], status_code=status.HTTP_200_OK)
async def listar_escalacoes(
    status_filtro: str = Query("pendente", alias="status", description="pendente | aprovada | rejeitada"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    db: AsyncSession = Depends(get_db),
):
    """
    Lista escalações do escritório filtradas por status.

    Cada item inclui o texto do cliente, a sugestão gerada pela IA e o motivo
    da escalação — tudo que o advogado precisa para aprovar ou rejeitar.
    """
    if status_filtro not in _STATUS_VALIDOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Status inválido. Use: {', '.join(sorted(_STATUS_VALIDOS))}",
        )

    offset = (page - 1) * limit

    stmt = (
        select(Interacao)
        .where(
            Interacao.escritorio_id == escritorio_id,
            Interacao.tipo == "escalacao",
            Interacao.metadata_json["escalacao"]["status"].astext == status_filtro,
        )
        .order_by(Interacao.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()

    # Busca nomes dos clientes em batch
    cliente_ids = list({r.cliente_id for r in rows})
    nomes: dict[int, str] = {}
    if cliente_ids:
        clientes_stmt = select(Cliente.id, Cliente.nome).where(Cliente.id.in_(cliente_ids))
        for cid, cnome in (await db.execute(clientes_stmt)).all():
            nomes[cid] = cnome

    return [
        EscalacaoItem(
            id=r.id,
            cliente_id=r.cliente_id,
            cliente_nome=nomes.get(r.cliente_id),
            mensagem_cliente=r.mensagem_cliente,
            sugestao_resposta=_extrair_escalacao(r.metadata_json).get("sugestao_resposta"),
            motivo=_extrair_escalacao(r.metadata_json).get("motivo"),
            status_escalacao=_extrair_escalacao(r.metadata_json).get("status", "pendente"),
            created_at=r.created_at,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# POST /escalacoes/{id}/aprovar
# ---------------------------------------------------------------------------

@router.post("/{escalacao_id}/aprovar", status_code=status.HTTP_200_OK)
async def aprovar_escalacao(
    escalacao_id: int,
    body: AprovarRequest = Body(default=AprovarRequest()),
    advogado_id: int = Depends(get_advogado_id),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    db: AsyncSession = Depends(get_db),
):
    """
    Aprova a escalação enviando a resposta ao cliente via WhatsApp.

    Se `resposta_final` não for informada, usa a sugestão gerada pela IA.
    """
    interacao = await _get_escalacao_ou_404(escalacao_id, escritorio_id, db)
    esc_meta = _extrair_escalacao(interacao.metadata_json)

    if esc_meta.get("status") != "pendente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Escalação já foi {esc_meta.get('status', 'processada')}.",
        )

    resposta = body.resposta_final or esc_meta.get("sugestao_resposta", "")
    if not resposta:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nenhuma resposta disponível. Forneça 'resposta_final'.",
        )

    # Carregar cliente e escritório para WhatsApp
    cliente = await db.get(Cliente, interacao.cliente_id)
    escritorio = await db.get(Escritorio, escritorio_id)

    if not cliente or not escritorio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente ou escritório não encontrado.")

    instance = escritorio.webhook_whatsapp_instance
    enviado = False
    if instance and cliente.telefone_whatsapp:
        try:
            evo = _get_evolution()
            await evo.enviar_texto(
                instance=instance,
                numero=cliente.telefone_whatsapp,
                texto=resposta,
            )
            enviado = True
        except Exception as exc:
            logger.error("escalacao_aprovar_whatsapp_falhou", escalacao_id=escalacao_id, erro=str(exc))

    # Atualiza status no metadata_json
    meta = dict(interacao.metadata_json or {})
    meta["escalacao"] = {
        **esc_meta,
        "status": "aprovada",
        "resposta_enviada": resposta,
        "aprovado_por": advogado_id,
        "ts_aprovacao": datetime.now(UTC).isoformat(),
        "whatsapp_enviado": enviado,
    }
    interacao.metadata_json = meta
    await db.commit()

    logger.info("escalacao_aprovada", escalacao_id=escalacao_id, advogado_id=advogado_id, enviado=enviado)
    return {"ok": True, "enviado": enviado, "resposta": resposta}


# ---------------------------------------------------------------------------
# POST /escalacoes/{id}/rejeitar
# ---------------------------------------------------------------------------

@router.post("/{escalacao_id}/rejeitar", status_code=status.HTTP_200_OK)
async def rejeitar_escalacao(
    escalacao_id: int,
    advogado_id: int = Depends(get_advogado_id),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    db: AsyncSession = Depends(get_db),
):
    """
    Rejeita a escalação sem enviar resposta ao cliente.
    Útil para escalações inválidas ou duplicadas.
    """
    interacao = await _get_escalacao_ou_404(escalacao_id, escritorio_id, db)
    esc_meta = _extrair_escalacao(interacao.metadata_json)

    if esc_meta.get("status") != "pendente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Escalação já foi {esc_meta.get('status', 'processada')}.",
        )

    meta = dict(interacao.metadata_json or {})
    meta["escalacao"] = {
        **esc_meta,
        "status": "rejeitada",
        "rejeitado_por": advogado_id,
        "ts_rejeicao": datetime.now(UTC).isoformat(),
    }
    interacao.metadata_json = meta
    await db.commit()

    logger.info("escalacao_rejeitada", escalacao_id=escalacao_id, advogado_id=advogado_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _get_escalacao_ou_404(
    escalacao_id: int,
    escritorio_id: int,
    db: AsyncSession,
) -> Interacao:
    interacao = await db.get(Interacao, escalacao_id)
    if not interacao or interacao.tipo != "escalacao":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escalação não encontrada.")
    if interacao.escritorio_id != escritorio_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado.")
    return interacao
