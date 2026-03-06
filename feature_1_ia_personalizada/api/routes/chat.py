from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.workers.send_notifications import (
    processar_mensagem_recebida,
)
from shared.database.session import get_db
from shared.models.cliente import Cliente
from shared.models.interacao import Interacao
from shared.utils.lgpd import registrar_acesso

router = APIRouter(prefix="/chat", tags=["Histórico e Chat"])


def _get_user_id(request: Request) -> int:
    payload = getattr(request.state, "user_payload", {})
    return int(payload.get("sub", 0))


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# --- Schemas Inline (Específicos da Rota) ---
class InteracaoResponse(BaseModel):
    id: int
    data: datetime
    direcao: str
    mensagem_cliente: str | None
    mensagem_ia: str | None
    tokens_input: int
    tokens_output: int
    custo_estimado: Decimal


class SendMessageRequest(BaseModel):
    mensagem: str
    tipo: str = "texto"


class ChatStatsResponse(BaseModel):
    total_interacoes: int
    total_tokens: int
    custo_total_usd: Decimal


def _get_escritorio_id(request: Request) -> int:
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Não autenticado")
    return int(request.state.user_payload.get("escritorio_id"))


@router.get("/history/{cliente_id}", response_model=list[InteracaoResponse])
async def get_history(
    cliente_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=200),
):
    """Retorna o histórico de conversas recentes de um cliente."""
    escritorio_id = _get_escritorio_id(request)

    # 1. Checa se o cliente pertence ao escritório
    cliente = await db.get(Cliente, cliente_id)
    if not cliente or cliente.escritorio_id != escritorio_id:
        raise HTTPException(
            status_code=404, detail="Cliente não encontrado ou acesso restrito."
        )

    registrar_acesso(
        _get_user_id(request),
        f"chat:historico:cliente:{cliente_id}",
        "leitura",
        _get_ip(request),
    )

    stmt = (
        select(Interacao)
        .where(Interacao.cliente_id == cliente_id)
        .order_by(Interacao.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    interacoes = result.scalars().all()

    # Para o front-end, retornamos do mais antigo pro mais novo usualmente,
    # mas aqui mapeamos cru para o front resolver a ordem de scroll.
    response_list = []
    for i in interacoes:
        response_list.append(
            InteracaoResponse(
                id=i.id,
                data=i.created_at,
                direcao=i.direcao,
                mensagem_cliente=i.mensagem_cliente,
                mensagem_ia=i.mensagem_ia,
                tokens_input=i.tokens_input,
                tokens_output=i.tokens_output,
                custo_estimado=i.custo_estimado,
            )
        )
    return response_list


@router.post("/send/{cliente_id}", status_code=status.HTTP_202_ACCEPTED)
async def send_proactive_message(
    cliente_id: int,
    payload: SendMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Envia uma mensagem ativamente (proativa) para um cliente da base via Celery."""
    escritorio_id = _get_escritorio_id(request)

    cliente = await db.get(Cliente, cliente_id)
    if not cliente or cliente.escritorio_id != escritorio_id:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")

    registrar_acesso(
        _get_user_id(request),
        f"chat:envio_proativo:cliente:{cliente_id}",
        "escrita",
        _get_ip(request),
    )

    # Despacha para a IA/Celery formatar e mandar via Evolution API
    processar_mensagem_recebida.delay(
        id_escritorio=escritorio_id,
        id_cliente=cliente_id,
        mensagem=payload.mensagem,
        tipo=payload.tipo,
    )
    return {
        "status": "enfileirado",
        "message": "A mensagem foi encaminhada aos workers para envio.",
    }


@router.get("/stats/dashboard", response_model=ChatStatsResponse)
async def get_chat_stats(request: Request, db: AsyncSession = Depends(get_db)):
    """Retorna estatísticas gerais de uso da I.A. pelo escritório (tokens e grana gasta)."""
    escritorio_id = _get_escritorio_id(request)

    stmt_count = select(func.count(Interacao.id)).where(
        Interacao.escritorio_id == escritorio_id
    )
    total_interacoes = await db.scalar(stmt_count) or 0

    stmt_tokens = select(
        func.sum(Interacao.tokens_input + Interacao.tokens_output)
    ).where(Interacao.escritorio_id == escritorio_id)
    total_tokens = await db.scalar(stmt_tokens) or 0

    stmt_custos = select(func.sum(Interacao.custo_estimado)).where(
        Interacao.escritorio_id == escritorio_id
    )
    custo_total = await db.scalar(stmt_custos) or Decimal("0.0")

    return ChatStatsResponse(
        total_interacoes=total_interacoes,
        total_tokens=total_tokens,
        custo_total_usd=custo_total,
    )
