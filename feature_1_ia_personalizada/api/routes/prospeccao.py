"""
Rotas de Prospecção Inteligente
================================
Arquivo: feature_1_ia_personalizada/api/routes/prospeccao.py

Acesso: exclusivo para advogado e admin (require_advogado).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.api.middleware.auth import (
    get_escritorio_id_advogado,
    require_advogado,
)
from feature_1_ia_personalizada.services.prospeccao.datajud_prospeccao import (
    DataJudProspeccaoClient,
)
from feature_1_ia_personalizada.services.prospeccao.dna_advogado import DNAAdvogadoService
from feature_1_ia_personalizada.services.prospeccao.empresa_intelligence import (
    EmpresaIntelligenceService,
)
from feature_1_ia_personalizada.services.prospeccao.matching import MatchingService
from feature_1_ia_personalizada.services.prospeccao.pessoa_intelligence import (
    PessoaIntelligenceService,
)
from shared.database.session import get_db
from shared.schemas.prospeccao import (
    DescobertaRequest,
    DNAEscritorioResponse,
    LeadProspeccaoResponse,
    LeadStatusUpdate,
    PipelineResponse,
)

router = APIRouter(
    prefix="/prospeccao",
    tags=["prospeccao"],
    dependencies=[Depends(require_advogado)],
)

# ---------------------------------------------------------------------------
# Instâncias dos serviços (stateless — seguro compartilhar)
# ---------------------------------------------------------------------------
_dna_service = DNAAdvogadoService()
_datajud = DataJudProspeccaoClient()
_empresa_svc = EmpresaIntelligenceService()
_pessoa_svc = PessoaIntelligenceService()
_matching_svc = MatchingService()


# ---------------------------------------------------------------------------
# GET /prospeccao/dna
# ---------------------------------------------------------------------------


@router.get("/dna", response_model=DNAEscritorioResponse)
async def get_dna(
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna o DNA atual do escritório.
    Se não houver processos suficientes, retorna dados_insuficientes=True.
    """
    dna = await _dna_service.obter_dna_salvo(escritorio_id=escritorio_id, db=db)
    if dna is None:
        return DNAEscritorioResponse(dados_insuficientes=True)
    return dna


# ---------------------------------------------------------------------------
# POST /prospeccao/dna/atualizar
# ---------------------------------------------------------------------------


@router.post("/dna/atualizar", response_model=DNAEscritorioResponse)
async def atualizar_dna(
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    db: AsyncSession = Depends(get_db),
):
    """
    Força a regeneração do DNA do escritório.
    Lê os processos mais recentes e chama Claude para reclassificar especialidades.
    """
    dna = await _dna_service.gerar_dna(escritorio_id=escritorio_id, db=db)
    await _dna_service.salvar_dna(escritorio_id=escritorio_id, dna=dna, db=db)
    return dna


# ---------------------------------------------------------------------------
# POST /prospeccao/descobrir
# ---------------------------------------------------------------------------


@router.post("/descobrir", response_model=PipelineResponse, status_code=status.HTTP_201_CREATED)
async def descobrir_leads(
    body: DescobertaRequest,
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    db: AsyncSession = Depends(get_db),
):
    """
    Motor principal de prospecção.

    Fluxo:
    1. Carrega o DNA do escritório
    2. Resolve o tipo_lead ("auto" → usa DNA)
    3. Busca litigantes no DataJud pelo tipo_acao
    4. Enriquece cada litigante (empresa ou pessoa)
    5. Calcula score via MatchingService
    6. Salva leads com score ≥ score_minimo
    7. Injeta aviso_lgpd se houver leads B2C
    """
    # 1. DNA
    dna = await _dna_service.obter_dna_salvo(escritorio_id=escritorio_id, db=db)
    dna_disponivel = dna is not None and not dna.dados_insuficientes

    # 2. Resolver tipo_lead
    tipo_lead = body.tipo_lead
    if tipo_lead == "auto":
        if not dna_disponivel:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="DNA do escritório não disponível. Use POST /prospeccao/dna/atualizar primeiro ou informe tipo_lead explicitamente.",
            )
        tipo_lead = dna.tipo_lead_predominante or "empresa"

    # 3. Buscar litigantes no DataJud
    litigantes = await _datajud.buscar_litigantes(
        tipo_acao=body.tipo_acao,
        tribunal=body.tribunal,
        limite=body.limite,
        tipo_lead=tipo_lead,
    )

    # 4 + 5. Enriquecer e calcular score
    leads_salvos: list[LeadProspeccaoResponse] = []

    for litigante in litigantes:
        try:
            if tipo_lead == "empresa":
                inteligencia = await _empresa_svc.enriquecer(litigante)
            else:
                # Valida compliance LGPD antes de enriquecer pessoa
                if not _pessoa_svc.validar_compliance(litigante):
                    continue
                inteligencia = await _pessoa_svc.enriquecer(litigante)

            resultado = await _matching_svc.calcular_score(dna=dna, inteligencia=inteligencia)

            if resultado.score < body.score_minimo:
                continue

            # 6. Salvar lead no banco
            lead_salvo = await _salvar_lead(
                escritorio_id=escritorio_id,
                litigante=litigante,
                inteligencia=inteligencia,
                resultado=resultado,
                tipo_lead=tipo_lead,
                fonte=body.tipo_acao,
                db=db,
            )
            leads_salvos.append(lead_salvo)

        except (ValueError, Exception):
            # Lead inválido ou erro de enriquecimento — pula silenciosamente
            continue

    # 7. Montar response com aviso_lgpd automático
    linkedin_disponivel = await _empresa_svc.linkedin_disponivel()
    return PipelineResponse.montar(
        leads=leads_salvos,
        dna_disponivel=dna_disponivel,
        linkedin_disponivel=linkedin_disponivel,
    )


# ---------------------------------------------------------------------------
# GET /prospeccao/pipeline
# ---------------------------------------------------------------------------


@router.get("/pipeline", response_model=PipelineResponse)
async def listar_pipeline(
    tipo_lead: str | None = Query(default=None, description="Filtrar por 'empresa' ou 'pessoa'"),
    status_filtro: str | None = Query(
        default=None, alias="status", description="Filtrar por status"
    ),
    score_minimo: int = Query(default=0, ge=0, le=100),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=20, ge=1, le=100),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    db: AsyncSession = Depends(get_db),
):
    """Lista leads salvos com filtros opcionais."""
    from sqlalchemy import select

    from shared.models.lead_prospeccao import LeadProspeccao

    query = select(LeadProspeccao).where(LeadProspeccao.escritorio_id == escritorio_id)

    if tipo_lead:
        query = query.where(LeadProspeccao.tipo_lead == tipo_lead)
    if status_filtro:
        query = query.where(LeadProspeccao.status == status_filtro)
    if score_minimo > 0:
        query = query.where(LeadProspeccao.score_match >= score_minimo)

    query = query.order_by(LeadProspeccao.score_match.desc())
    query = query.offset((pagina - 1) * por_pagina).limit(por_pagina)

    result = await db.execute(query)
    leads_db = result.scalars().all()
    leads = [LeadProspeccaoResponse.model_validate(lead) for lead in leads_db]

    dna = await _dna_service.obter_dna_salvo(escritorio_id=escritorio_id, db=db)
    linkedin_disponivel = await _empresa_svc.linkedin_disponivel()

    return PipelineResponse.montar(
        leads=leads,
        dna_disponivel=dna is not None and not dna.dados_insuficientes,
        linkedin_disponivel=linkedin_disponivel,
    )


# ---------------------------------------------------------------------------
# PATCH /prospeccao/{id}/status
# ---------------------------------------------------------------------------


@router.patch("/{lead_id}/status", response_model=LeadProspeccaoResponse)
async def atualizar_status(
    lead_id: int,
    body: LeadStatusUpdate,
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza status e notas de um lead. Rejeita leads de outro escritório."""
    lead = await _get_lead_ou_403(lead_id=lead_id, escritorio_id=escritorio_id, db=db)
    lead.status = body.status
    if body.notas_advogado is not None:
        lead.notas_advogado = body.notas_advogado
    await db.commit()
    await db.refresh(lead)
    return LeadProspeccaoResponse.model_validate(lead)


# ---------------------------------------------------------------------------
# DELETE /prospeccao/{id}
# ---------------------------------------------------------------------------


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deletar_lead(
    lead_id: int,
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    db: AsyncSession = Depends(get_db),
):
    """Remove um lead. Rejeita leads de outro escritório."""
    lead = await _get_lead_ou_403(lead_id=lead_id, escritorio_id=escritorio_id, db=db)
    await db.delete(lead)
    await db.commit()


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


async def _get_lead_ou_403(lead_id: int, escritorio_id: int, db: AsyncSession):
    """Busca o lead e verifica propriedade. Levanta 403 se não pertencer ao escritório."""
    from sqlalchemy import select

    from shared.models.lead_prospeccao import LeadProspeccao

    result = await db.execute(select(LeadProspeccao).where(LeadProspeccao.id == lead_id))
    lead = result.scalar_one_or_none()

    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead não encontrado")
    if lead.escritorio_id != escritorio_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    return lead


async def _salvar_lead(
    escritorio_id: int,
    litigante,
    inteligencia,
    resultado,
    tipo_lead: str,
    fonte: str,
    db: AsyncSession,
) -> LeadProspeccaoResponse:
    """
    Salva ou atualiza um lead no banco.
    Deduplicação: mesmo CNPJ (empresa) ou mesmo número CNJ (pessoa) → atualiza.
    """
    from sqlalchemy import select

    from shared.models.lead_prospeccao import LeadProspeccao

    # Chave de deduplicação
    if tipo_lead == "empresa":
        chave = getattr(inteligencia, "cnpj", None)
        filtro = LeadProspeccao.cnpj == chave if chave else None
    else:
        chave = getattr(inteligencia, "numero_cnj_exemplo", None)
        filtro = LeadProspeccao.numero_cnj_exemplo == chave if chave else None

    lead_existente = None
    if filtro is not None:
        result = await db.execute(
            select(LeadProspeccao).where(
                LeadProspeccao.escritorio_id == escritorio_id,
                filtro,
            )
        )
        lead_existente = result.scalar_one_or_none()

    if lead_existente:
        # Atualiza score e abordagem
        lead_existente.score_match = resultado.score
        lead_existente.score_motivo = resultado.motivo
        lead_existente.abordagem_sugerida = resultado.abordagem_sugerida
        await db.commit()
        await db.refresh(lead_existente)
        return LeadProspeccaoResponse.model_validate(lead_existente)

    # Cria novo lead
    novo = LeadProspeccao(
        escritorio_id=escritorio_id,
        tipo_lead=tipo_lead,
        nome=getattr(inteligencia, "razao_social", None) or getattr(inteligencia, "nome", ""),
        score_match=resultado.score,
        score_motivo=resultado.motivo,
        abordagem_sugerida=resultado.abordagem_sugerida,
        status="novo",
        fonte_descoberta=fonte,
        # Campos empresa
        cnpj=getattr(inteligencia, "cnpj", None),
        empresa_setor=getattr(inteligencia, "setor_cnae", None),
        empresa_porte=getattr(inteligencia, "porte", None),
        socios=getattr(inteligencia, "socios", []),
        contatos_linkedin=getattr(inteligencia, "contatos_linkedin", []),
        linkedin_disponivel=getattr(inteligencia, "linkedin_disponivel", False),
        # Campos pessoa — sem CPF, telefone ou email (proibido por design)
        polo_processo=getattr(inteligencia, "polo", None),
        tipo_acao_origem=getattr(inteligencia, "tipo_acao", None),
        numero_cnj_exemplo=getattr(inteligencia, "numero_cnj_exemplo", None),
        processos_publicos_count=getattr(inteligencia, "processos_count", 1),
    )
    db.add(novo)
    await db.commit()
    await db.refresh(novo)
    return LeadProspeccaoResponse.model_validate(novo)
