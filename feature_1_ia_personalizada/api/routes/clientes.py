"""
feature_1_ia_personalizada/api/routes/clientes.py
===================================================
Endpoints LGPD para gestão de dados de clientes.

Implementa os direitos do titular previstos na Lei nº 13.709/2018:
  - Art. 18, V  — Portabilidade: GET  /clientes/{id}/exportar
  - Art. 18, IV — Esquecimento:  DELETE /clientes/{id}

Acesso restrito a roles 'advogado' e 'admin' com isolamento por escritório.

Rate limits LGPD (por user_id — não por IP):
  - Exportar:  10 por hora (prevenção de data dump via token comprometido)
  - Deletar:    5 por hora (operação irreversível)
"""

from typing import Any

import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.api.middleware.auth import (
    get_advogado_id,
    get_escritorio_id_advogado,
)
from feature_1_ia_personalizada.api.routes.processos import (
    _disparar_monitoramento,
    _enriquecer_processo_async,
)
from shared.database.session import get_db
from shared.security.encryption import criptografar
from shared.models.cliente import Cliente
from shared.models.documento_cliente import (
    MAX_TAMANHO_BYTES,
    TIPOS_DOCUMENTO_CLIENTE,
    DocumentoCliente,
)
from shared.models.processo import Processo
from shared.schemas.cliente import ClienteCreateManual, ClienteCreateManualResponse
from shared.utils.lgpd import (
    anonimizar_dados_cliente,
    exportar_dados_cliente,
    registrar_acesso,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/clientes", tags=["Clientes — LGPD"])


# ---------------------------------------------------------------------------
# Rate-limit LGPD — dependency por endpoint, bucket por user_id
# ---------------------------------------------------------------------------


def _make_lgpd_rate_limit(action: str, limit: int, window_s: int) -> Any:
    """
    Retorna uma FastAPI dependency que aplica rate limit por user_id no Redis.
    Falha aberta se Redis estiver indisponível (não bloqueia o usuário).
    """

    async def _dep(
        request: Request,
        user_id: int = Depends(get_advogado_id),
    ) -> None:
        r = getattr(request.app.state, "redis_client", None)
        if r is None:
            return
        key = f"rate_limit:lgpd:{action}:{user_id}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, window_s)
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Limite LGPD atingido: máximo de {limit} operações "
                    f"de '{action}' por hora. Tente novamente em breve."
                ),
                headers={"Retry-After": str(window_s)},
            )

    return _dep


_rl_exportar = _make_lgpd_rate_limit("exportar", limit=10, window_s=3600)
_rl_deletar = _make_lgpd_rate_limit("deletar", limit=5, window_s=3600)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return str(forwarded).split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _get_cliente_do_escritorio(
    cliente_id: int,
    escritorio_id: int,
    db: AsyncSession,
) -> Cliente:
    """
    Busca um cliente garantindo que pertence ao escritório do token (tenant isolation).
    Levanta 404 se não encontrado ou se pertencer a outro escritório.
    """
    resultado = await db.execute(
        select(Cliente).where(
            Cliente.id == cliente_id,
            Cliente.escritorio_id == escritorio_id,
        )
    )
    cliente = resultado.scalars().first()
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente não encontrado ou sem permissão de acesso.",
        )
    return cliente


# ---------------------------------------------------------------------------
# POST /clientes  — cadastro manual pelo advogado
# ---------------------------------------------------------------------------


@router.post("", response_model=ClienteCreateManualResponse, status_code=status.HTTP_201_CREATED)
async def criar_cliente_manual(
    payload: ClienteCreateManual,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
) -> ClienteCreateManualResponse:
    """
    Cadastra um cliente manualmente com nome + telefone + processo opcional.
    Diferente do fluxo WhatsApp (automático) e CSV (bulk), este endpoint é
    voltado para o advogado registrar um cliente de forma pontual na interface.

    Fluxo:
    1. Verifica duplicata de telefone no mesmo escritório.
    2. Cria o cliente (sem CPF — pode ser adicionado depois via edição).
    3. Se numero_cnj informado, cria o processo vinculado e dispara enriquecimento.
    """
    # 1. Duplicata por telefone
    existente = await db.execute(
        select(Cliente).where(
            Cliente.escritorio_id == escritorio_id,
            Cliente.telefone_whatsapp == payload.telefone_whatsapp,
        )
    )
    if existente.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe um cliente com este número de telefone no escritório.",
        )

    # 2. Criar cliente
    try:
        cpf_criptografado = criptografar(payload.cpf)
        
        novo_cliente = Cliente(
            escritorio_id=escritorio_id,
            nome=payload.nome,
            cpf=cpf_criptografado,
            telefone_whatsapp=payload.telefone_whatsapp,
            ativo=True,
            aceite_lgpd=False,
        )
        db.add(novo_cliente)
        await db.flush()

        logger.info("cliente_manual_criado", cliente_id=novo_cliente.id, escritorio_id=escritorio_id)

        # 3. Processo opcional
        processo_id: int | None = None
        if payload.numero_cnj:
            novo_processo = Processo(
                escritorio_id=escritorio_id,
                numero_cnj=payload.numero_cnj,
                cliente_id=novo_cliente.id,
                polo_cliente=payload.polo_cliente,
                tipo_acao=payload.tipo_acao,
                status="ativo",
                monitoramento_ativo=True,
            )
            db.add(novo_processo)
            await db.flush()
            processo_id = novo_processo.id

            background_tasks.add_task(
                _enriquecer_processo_async, novo_processo.id, novo_processo.numero_cnj
            )
            background_tasks.add_task(_disparar_monitoramento, novo_processo.id)
            
        await db.commit()

        return ClienteCreateManualResponse(
            id=novo_cliente.id,
            nome=novo_cliente.nome,
            telefone_whatsapp=novo_cliente.telefone_whatsapp,
            processo_id=processo_id,
        )
    except Exception as e:
        await db.rollback()
        import traceback
        tb = traceback.format_exc()
        logger.error("erro_criar_cliente_manual", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno: {str(e)}\nTraceback: {tb}"
        )


# ---------------------------------------------------------------------------
# GET /clientes/{cliente_id}/exportar
# ---------------------------------------------------------------------------


@router.get(
    "/{cliente_id}/exportar",
    summary="Exportar dados pessoais do cliente (LGPD Art. 18, V)",
    response_class=JSONResponse,
)
async def exportar_dados(
    cliente_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    user_id: int = Depends(get_advogado_id),
    _: None = Depends(_rl_exportar),
) -> JSONResponse:
    """
    Retorna todos os dados pessoais armazenados sobre o cliente em formato JSON.

    Inclui: dados cadastrais, histórico de processos e histórico de interações (mensagens).
    O CPF criptografado não é exposto — apenas sua presença é indicada.

    Conforme LGPD Art. 18, V — direito à portabilidade dos dados a outro fornecedor.

    **Acesso:** advogado ou admin do mesmo escritório.
    **Rate limit:** 10 exportações por hora por usuário.
    """
    await _get_cliente_do_escritorio(cliente_id, escritorio_id, db)

    registrar_acesso(
        user_id=user_id,
        recurso=f"cliente:{cliente_id}",
        acao="exportacao",
        ip=_get_ip(request),
    )

    try:
        dados = await exportar_dados_cliente(db, cliente_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return JSONResponse(
        content=dados,
        headers={
            "Content-Disposition": f'attachment; filename="lgpd_cliente_{cliente_id}.json"',
        },
    )


# ---------------------------------------------------------------------------
# DELETE /clientes/{cliente_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/{cliente_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Anonimizar dados pessoais do cliente (LGPD Art. 18, IV)",
)
async def deletar_dados(
    cliente_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    user_id: int = Depends(get_advogado_id),
    _: None = Depends(_rl_deletar),
) -> None:
    """
    Anonimiza todos os dados pessoais do cliente (direito ao esquecimento).

    **O que é feito:**
    - Dados cadastrais substituídos por valores neutros (nome, CPF, telefone, e-mail, etc.)
    - Conteúdo das mensagens apagado (mensagem_cliente, mensagem_ia, audio_transcricao)
    - Cliente marcado como inativo — nenhuma mensagem futura será enviada
    - Processos e registros de auditoria mantidos para integridade financeira/legal

    **Não é um hard delete:** os registros permanecem no banco sem identificação pessoal,
    preservando rastreabilidade exigida por outras obrigações legais.

    Conforme LGPD Art. 18, IV — direito à eliminação dos dados pessoais tratados.

    **Acesso:** advogado ou admin do mesmo escritório.
    **Rate limit:** 5 anonimizações por hora por usuário.
    """
    await _get_cliente_do_escritorio(cliente_id, escritorio_id, db)

    try:
        await anonimizar_dados_cliente(db, cliente_id, solicitado_por=user_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return None


# ---------------------------------------------------------------------------
# Schemas para documentos do cliente
# ---------------------------------------------------------------------------


class DocumentoClienteItem(BaseModel):
    id: int
    nome: str
    arquivo_nome: str
    mime_type: str
    tamanho_bytes: int
    tipo: str
    processo_id: int | None
    created_at: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# GET /clientes/{cliente_id}/documentos
# ---------------------------------------------------------------------------


@router.get("/{cliente_id}/documentos", response_model=list[DocumentoClienteItem])
async def listar_documentos_cliente(
    cliente_id: int,
    db: AsyncSession = Depends(get_db),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
) -> list[DocumentoClienteItem]:
    """Lista documentos de um cliente (sem o conteúdo binário)."""
    await _get_cliente_do_escritorio(cliente_id, escritorio_id, db)

    rows = (
        await db.execute(
            select(
                DocumentoCliente.id,
                DocumentoCliente.nome,
                DocumentoCliente.arquivo_nome,
                DocumentoCliente.mime_type,
                DocumentoCliente.tamanho_bytes,
                DocumentoCliente.tipo,
                DocumentoCliente.processo_id,
                DocumentoCliente.created_at,
            )
            .where(
                DocumentoCliente.cliente_id == cliente_id,
                DocumentoCliente.escritorio_id == escritorio_id,
                DocumentoCliente.ativo.is_(True),
            )
            .order_by(DocumentoCliente.created_at.desc())
        )
    ).all()

    return [
        DocumentoClienteItem(
            id=r.id,
            nome=r.nome,
            arquivo_nome=r.arquivo_nome,
            mime_type=r.mime_type,
            tamanho_bytes=r.tamanho_bytes,
            tipo=r.tipo,
            processo_id=r.processo_id,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# POST /clientes/{cliente_id}/documentos
# ---------------------------------------------------------------------------


@router.post(
    "/{cliente_id}/documentos",
    response_model=DocumentoClienteItem,
    status_code=status.HTTP_201_CREATED,
)
async def upload_documento_cliente(
    cliente_id: int,
    file: UploadFile = File(...),
    nome: str = "",
    tipo: str = "outro",
    processo_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
) -> DocumentoClienteItem:
    """Faz upload de um documento para um cliente específico."""
    await _get_cliente_do_escritorio(cliente_id, escritorio_id, db)

    if tipo not in TIPOS_DOCUMENTO_CLIENTE:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo inválido. Use: {', '.join(sorted(TIPOS_DOCUMENTO_CLIENTE))}",
        )

    conteudo = await file.read()
    if len(conteudo) > MAX_TAMANHO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Máximo: {MAX_TAMANHO_BYTES // (1024 * 1024)} MB.",
        )
    if not conteudo:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")

    arquivo_nome = file.filename or "arquivo"
    nome_final = nome.strip() or arquivo_nome.rsplit(".", 1)[0]
    mime = file.content_type or "application/octet-stream"

    doc = DocumentoCliente(
        escritorio_id=escritorio_id,
        cliente_id=cliente_id,
        processo_id=processo_id,
        nome=nome_final,
        arquivo_nome=arquivo_nome,
        mime_type=mime,
        tamanho_bytes=len(conteudo),
        tipo=tipo,
        conteudo=conteudo,
        ativo=True,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    logger.info(
        "documento_cliente_upload",
        cliente_id=cliente_id,
        doc_id=doc.id,
        tipo=tipo,
        tamanho=len(conteudo),
    )

    return DocumentoClienteItem(
        id=doc.id,
        nome=doc.nome,
        arquivo_nome=doc.arquivo_nome,
        mime_type=doc.mime_type,
        tamanho_bytes=doc.tamanho_bytes,
        tipo=doc.tipo,
        processo_id=doc.processo_id,
        created_at=doc.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# GET /clientes/{cliente_id}/documentos/{doc_id}/download
# ---------------------------------------------------------------------------


@router.get("/{cliente_id}/documentos/{doc_id}/download")
async def download_documento_cliente(
    cliente_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
) -> Response:
    """Faz download do conteúdo binário de um documento."""
    await _get_cliente_do_escritorio(cliente_id, escritorio_id, db)

    doc = await db.get(DocumentoCliente, doc_id)
    if (
        not doc
        or not doc.ativo
        or doc.cliente_id != cliente_id
        or doc.escritorio_id != escritorio_id
    ):
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    return Response(
        content=doc.conteudo,
        media_type=doc.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{doc.arquivo_nome}"',
            "Content-Length": str(doc.tamanho_bytes),
        },
    )


# ---------------------------------------------------------------------------
# DELETE /clientes/{cliente_id}/documentos/{doc_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/{cliente_id}/documentos/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def deletar_documento_cliente(
    cliente_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
) -> None:
    """Soft delete de um documento do cliente."""
    await _get_cliente_do_escritorio(cliente_id, escritorio_id, db)

    doc = await db.get(DocumentoCliente, doc_id)
    if (
        not doc
        or not doc.ativo
        or doc.cliente_id != cliente_id
        or doc.escritorio_id != escritorio_id
    ):
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    doc.ativo = False
    await db.flush()
    return None
