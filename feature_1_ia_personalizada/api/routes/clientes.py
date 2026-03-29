"""
feature_1_ia_personalizada/api/routes/clientes.py
===================================================
Endpoints LGPD para gestão de dados de clientes.

Implementa os direitos do titular previstos na Lei nº 13.709/2018:
  - Art. 18, V  — Portabilidade: GET  /clientes/{id}/exportar
  - Art. 18, IV — Esquecimento:  DELETE /clientes/{id}

Acesso restrito a roles 'advogado' e 'admin' com isolamento por escritório.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.api.middleware.auth import (
    get_advogado_id,
    get_escritorio_id_advogado,
)
from shared.database.session import get_db
from shared.models.cliente import Cliente
from shared.utils.lgpd import (
    anonimizar_dados_cliente,
    exportar_dados_cliente,
    registrar_acesso,
)

router = APIRouter(prefix="/clientes", tags=["Clientes — LGPD"])


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
):
    """
    Retorna todos os dados pessoais armazenados sobre o cliente em formato JSON.

    Inclui: dados cadastrais, histórico de processos e histórico de interações (mensagens).
    O CPF criptografado não é exposto — apenas sua presença é indicada.

    Conforme LGPD Art. 18, V — direito à portabilidade dos dados a outro fornecedor.

    **Acesso:** advogado ou admin do mesmo escritório.
    """
    # Verifica pertencimento ao escritório antes de exportar
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
            # Sugere download com nome de arquivo baseado no ID do cliente
            "Content-Disposition": f'attachment; filename="lgpd_cliente_{cliente_id}.json"',
        },
    )


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
):
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
    """
    # Verifica pertencimento ao escritório antes de anonimizar
    await _get_cliente_do_escritorio(cliente_id, escritorio_id, db)

    try:
        await anonimizar_dados_cliente(db, cliente_id, solicitado_por=user_id)
        # anonimizar_dados_cliente faz flush mas não commit — commit aqui
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return None
