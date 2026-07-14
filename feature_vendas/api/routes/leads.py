"""
Upload da planilha de alvos (etapa 1 do roteiro) + visão do funil.

POST /vendas/leads/importar   → recebe CSV, filtra (ICP), enfileira p/ enriquecer
GET  /vendas/leads/funil      → contagem por status (o painel da máquina)
GET  /vendas/leads/excecao    → alvos em fila_excecao (o humano revisa só estes)
POST /vendas/leads/{id}/aprovar → libera um alvo da exceção para a fila de envio

Tudo atrás de JWT admin do tenant de vendas — rota interna, nunca pública.
O único público do feature_vendas é o webhook do vitrine (a conversa da Clara).

Colunas do CSV (cabeçalho): nome_escritorio, nome_contato, oab, cnpj, whatsapp,
cidade, area, num_advogados, tem_vaga, anuncia, instagram_ativo, whatsapp_publico,
processo_cnj

`processo_cnj` é opcional mas é o que ativa o Template A (espelho com processo
real): se você já fez a descoberta e informa o CNJ, a máquina busca sozinha a
movimentação recente. Sem CNJ, o alvo usa o Template B (genérico).
"""

from __future__ import annotations

import csv
import io
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_vendas.models.alvo_vendas import AlvoVendas
from feature_vendas.services.filtragem import pontuar
from shared.database.session import get_db

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/vendas/leads", tags=["Vendas — Leads"])


def _sales_tenant_id(request: Request) -> int:
    """
    Id do tenant autenticado, com guard de isolamento: só o tenant de vendas
    acessa estas rotas. Um escritório cliente logado que tente bater aqui leva
    403 — os dados de vendas nunca vazam para o multi-tenant de clientes.
    """
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Não autenticado")
    tenant = int(request.state.user_payload["escritorio_id"])
    from feature_vendas import config as vconfig

    if vconfig.VENDAS_TENANT_ID is not None and tenant != vconfig.VENDAS_TENANT_ID:
        raise HTTPException(status_code=403, detail="Rota exclusiva do tenant de vendas")
    return tenant


def _bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "sim", "s", "x", "yes"}


def _int(v: str | None) -> int | None:
    try:
        return int((v or "").strip())
    except ValueError:
        return None


@router.post("/importar")
async def importar_planilha(
    request: Request,
    arquivo: UploadFile,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    tenant = _sales_tenant_id(request)
    conteudo = (await arquivo.read()).decode("utf-8-sig")
    leitor = csv.DictReader(io.StringIO(conteudo))

    importados = 0
    desqualificados = 0
    classe_c = 0

    for linha in leitor:
        whatsapp = (linha.get("whatsapp") or "").strip()
        nome = (linha.get("nome_escritorio") or "").strip()
        if not whatsapp or not nome:
            continue

        resultado = pontuar(
            num_advogados=_int(linha.get("num_advogados")),
            area=linha.get("area"),
            tem_vaga_aberta=_bool(linha.get("tem_vaga")),
            anuncia_online=_bool(linha.get("anuncia")),
            instagram_ativo=_bool(linha.get("instagram_ativo")),
            whatsapp_publicado=_bool(linha.get("whatsapp_publico")),
        )

        # Desqualificado e classe C nem entram na fila de enriquecimento —
        # não gastam busca de processo nem token. Ficam registrados como
        # descartados, com o motivo, para não reimportar.
        if resultado.desqualificado:
            desqualificados += 1
            status_inicial = "descartado"
        elif resultado.classe == "C":
            classe_c += 1
            status_inicial = "descartado"
        else:
            status_inicial = "novo"

        alvo = AlvoVendas(
            escritorio_id=tenant,
            nome_escritorio=nome,
            nome_contato=(linha.get("nome_contato") or "").strip() or None,
            oab=(linha.get("oab") or "").strip() or None,
            cnpj=(linha.get("cnpj") or "").strip() or None,
            whatsapp=whatsapp,
            cidade=(linha.get("cidade") or "").strip() or None,
            area=(linha.get("area") or "").strip() or None,
            processo_cnj=(linha.get("processo_cnj") or "").strip() or None,
            score_icp=resultado.score,
            classe_icp=resultado.classe,
            origem=(linha.get("origem") or "planilha").strip(),
            status=status_inicial,
            metadados=(
                {"motivo_descarte": resultado.motivo} if status_inicial == "descartado" else None
            ),
        )
        db.add(alvo)
        importados += 1

    await db.commit()
    logger.info(
        "vendas_planilha_importada",
        tenant=tenant,
        importados=importados,
        desqualificados=desqualificados,
        classe_c=classe_c,
    )
    return {
        "importados": importados,
        "para_enriquecer": importados - desqualificados - classe_c,
        "desqualificados": desqualificados,
        "classe_c_ignorados": classe_c,
    }


@router.get("/funil")
async def funil(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    tenant = _sales_tenant_id(request)
    rows = (
        await db.execute(
            select(AlvoVendas.status, func.count())
            .where(AlvoVendas.escritorio_id == tenant)
            .group_by(AlvoVendas.status)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


@router.get("/excecao")
async def fila_excecao(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    tenant = _sales_tenant_id(request)
    rows = (
        (
            await db.execute(
                select(AlvoVendas)
                .where(AlvoVendas.escritorio_id == tenant, AlvoVendas.status == "fila_excecao")
                .order_by(AlvoVendas.confianca_validacao.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": a.id,
            "escritorio": a.nome_escritorio,
            "cnj": a.processo_cnj,
            "confianca": a.confianca_validacao,
            "mensagem": a.mensagem_espelho,
            "observacao": (a.metadados or {}).get("validacao_obs"),
        }
        for a in rows
    ]


@router.get("/quentes")
async def leads_quentes(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    """Leads que bateram critério de handoff — o que o sócio precisa ver primeiro."""
    tenant = _sales_tenant_id(request)
    rows = (
        (
            await db.execute(
                select(AlvoVendas)
                .where(AlvoVendas.escritorio_id == tenant, AlvoVendas.status == "quente")
                .order_by(AlvoVendas.respondeu_em.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": a.id,
            "escritorio": a.nome_escritorio,
            "contato": a.nome_contato,
            "cidade": a.cidade,
            "whatsapp": a.whatsapp,
            "gatilho": (a.metadados or {}).get("gatilho_handoff"),
            "socio": (a.metadados or {}).get("socio_responsavel"),
            "respondeu_em": a.respondeu_em.isoformat() if a.respondeu_em else None,
        }
        for a in rows
    ]


class EditarMensagem(BaseModel):
    mensagem_espelho: str


@router.patch("/{alvo_id}")
async def editar_mensagem(
    alvo_id: int,
    body: EditarMensagem,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Humano edita a mensagem de um alvo na fila de exceção antes de aprovar."""
    tenant = _sales_tenant_id(request)
    alvo = (
        await db.execute(
            select(AlvoVendas).where(AlvoVendas.id == alvo_id, AlvoVendas.escritorio_id == tenant)
        )
    ).scalar_one_or_none()
    if not alvo:
        raise HTTPException(status_code=404, detail="Alvo não encontrado")
    alvo.mensagem_espelho = body.mensagem_espelho.strip()
    await db.commit()
    return {"id": alvo.id, "mensagem_espelho": alvo.mensagem_espelho}


@router.post("/{alvo_id}/aprovar")
async def aprovar_excecao(
    alvo_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Humano revisou um alvo da exceção e libera para envio (pode ter editado a mensagem via PATCH antes)."""
    tenant = _sales_tenant_id(request)
    alvo = (
        await db.execute(
            select(AlvoVendas).where(
                AlvoVendas.id == alvo_id,
                AlvoVendas.escritorio_id == tenant,
                AlvoVendas.status == "fila_excecao",
            )
        )
    ).scalar_one_or_none()
    if not alvo:
        raise HTTPException(status_code=404, detail="Alvo não encontrado na fila de exceção")

    alvo.status = "fila_envio"
    await db.commit()
    return {"id": alvo.id, "status": alvo.status}
