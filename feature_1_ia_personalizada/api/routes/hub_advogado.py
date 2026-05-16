"""
Rotas do Hub do Advogado
=========================
Arquivo: feature_1_ia_personalizada/api/routes/hub_advogado.py

Endpoints REST para o Hub do Advogado — complemento à interface WhatsApp.
Permite que front-ends ou integrações consumam o Hub sem depender do WhatsApp.

Acesso: exclusivo para advogado e admin (require_advogado).
"""

from __future__ import annotations

import functools
import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.api.middleware.auth import (
    _get_payload,
    get_advogado_id,
    get_escritorio_id_advogado,
    require_advogado,
)
from feature_1_ia_personalizada.services.ai.escalation_client import (
    EscalacaoClient,
    EscalacaoIndisponivelError,
)
from feature_1_ia_personalizada.services.ai.prompts import SYSTEM_PROMPT_HUB_ADVOGADO_BASE
from feature_1_ia_personalizada.services.legal_data.data_cleaner import LegalDataCleaner
from feature_1_ia_personalizada.services.rag.ingestion import _extrair_texto_pdf
from shared.database.session import get_db
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio
from shared.models.processo import Processo
from shared.models.sessao_advogado import SessaoAdvogado
from shared.models.usuario import Usuario
from shared.schemas.hub_advogado import (
    AdvogadoAtivo,
    ConsultaHubRequest,
    ConsultaHubResponse,
    IntencaoCount,
    MetricasHubResponse,
    SessaoAdvogadoListItem,
    SessaoAdvogadoResponse,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_CHARS_ANALISE = 15_000         # ~5 000 tokens — limite seguro para Opus
_PDF_MAGIC = b"%PDF-"               # primeiros bytes de qualquer PDF válido

# ---------------------------------------------------------------------------
# Dependency: EscalacaoClient como singleton injetável
#
# Usar Depends() em vez de módulo-level direto garante que testes possam
# sobrescrever o client via app.dependency_overrides[get_escalacao_client].
# lru_cache(1) garante uma única instância compartilhada em produção —
# AsyncAnthropic é thread/async-safe e foi projetado para uso como singleton.
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def get_escalacao_client() -> EscalacaoClient:
    return EscalacaoClient()


# ---------------------------------------------------------------------------
# Router
#
# dependencies=[Depends(require_advogado)] aplica o guard a todos os endpoints.
# get_advogado_id e get_escritorio_id_advogado também dependem de require_advogado
# internamente, mas FastAPI deduplica dependências com o mesmo callable dentro do
# mesmo request — require_advogado é executado uma única vez por requisição.
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/hub",
    tags=["Hub do Advogado"],
    dependencies=[Depends(require_advogado)],
)

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


async def _carregar_usuario_escritorio(
    advogado_id: int,
    escritorio_id: int,
    db: AsyncSession,
) -> tuple[Usuario, Escritorio]:
    usuario = await db.get(Usuario, advogado_id)
    escritorio = await db.get(Escritorio, escritorio_id)
    if not usuario or not escritorio:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou escritório não encontrado.",
        )
    return usuario, escritorio


async def _salvar_sessao(db: AsyncSession, sessao: SessaoAdvogado) -> None:
    """Persiste a sessão com rollback explícito em caso de falha."""
    try:
        db.add(sessao)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("hub_sessao_salvar_falhou", erro=str(exc))
        # Não propaga: a resposta ao advogado já foi produzida com sucesso.


# ---------------------------------------------------------------------------
# POST /hub/analisar-peticao
#
# Rate limiting: o RateLimitMiddleware global cobre este endpoint.
# Para limites por advogado_id (anti-abuse), adicionar decorator específico
# após validar o volume real em produção — TODO Fase 6.
# ---------------------------------------------------------------------------


@router.post("/analisar-peticao", status_code=status.HTTP_202_ACCEPTED)
async def analisar_peticao(
    arquivo: UploadFile = File(..., description="Arquivo PDF da petição (máx. 10 MB)"),
    advogado_id: int = Depends(get_advogado_id),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
):
    """
    Enfileira análise de petição PDF com Claude Opus.

    Responde 202 imediatamente com `job_id`. O cliente faz polling em
    GET /hub/jobs/{job_id} até `status` != "processando".

    Validação de PDF (magic bytes + tamanho + extração de texto) ocorre
    de forma síncrona antes do enfileiramento — falhas retornam 422 rapidamente.
    """
    conteudo_bytes = await arquivo.read()

    if not conteudo_bytes.startswith(_PDF_MAGIC):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Arquivo inválido: os primeiros bytes não correspondem a um PDF (%PDF-).",
        )

    if len(conteudo_bytes) > _MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Arquivo excede o limite de 10 MB "
                f"({len(conteudo_bytes) // (1024 * 1024)} MB recebidos)."
            ),
        )

    try:
        texto = LegalDataCleaner.normalizar_espacos(
            _extrair_texto_pdf(conteudo_bytes) or ""
        )
    except Exception as exc:
        logger.warning("hub_rest_extracao_falhou", erro=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Não foi possível extrair texto do PDF. Verifique se não está protegido ou corrompido.",
        )

    if len(texto.strip()) < 50:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Documento vazio ou apenas com imagens (OCR não suportado).",
        )

    texto_truncado = len(texto) > _MAX_CHARS_ANALISE
    conteudo_envio = texto[:_MAX_CHARS_ANALISE]
    percentual_analisado = (
        round(min(_MAX_CHARS_ANALISE, len(texto)) / len(texto) * 100, 1)
        if texto else 100.0
    )

    job_id = str(uuid.uuid4())

    from feature_1_ia_personalizada.workers.hub_worker import hub_analisar_peticao_task
    hub_analisar_peticao_task.delay(
        job_id=job_id,
        conteudo_texto=conteudo_envio,
        texto_truncado=texto_truncado,
        percentual_analisado=percentual_analisado,
        filename=arquivo.filename or "peticao.pdf",
        escritorio_id=escritorio_id,
        advogado_id=advogado_id,
    )

    logger.info("hub_rest_peticao_enfileirada", job_id=job_id, escritorio_id=escritorio_id)
    return {"job_id": job_id, "status": "processando"}


# ---------------------------------------------------------------------------
# GET /hub/jobs/{job_id}
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}", status_code=status.HTTP_200_OK)
async def status_job_hub(
    job_id: str,
    request: Request,
    advogado_id: int = Depends(get_advogado_id),
):
    """
    Consulta o estado de um job assíncrono de análise de petição.

    Retorna `{"status": "processando"|"concluido"|"erro", "resultado": {...}|null, "erro": "..."|null}`.
    """
    redis_client = getattr(request.app.state, "redis_client", None)
    if redis_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis indisponível.",
        )

    raw = await redis_client.get(f"hub:job:{job_id}")
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job não encontrado ou expirado.",
        )

    return json.loads(raw)


# ---------------------------------------------------------------------------
# POST /hub/consultar
#
# Rate limiting: ver nota em analisar-peticao acima.
# ---------------------------------------------------------------------------


@router.post("/consultar", response_model=ConsultaHubResponse, status_code=status.HTTP_200_OK)
async def consultar(
    body: ConsultaHubRequest,
    advogado_id: int = Depends(get_advogado_id),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    db: AsyncSession = Depends(get_db),
    escalacao_client: EscalacaoClient = Depends(get_escalacao_client),
):
    """
    Consulta jurídica livre com Claude Opus.

    Opcionalmente vincula a um cliente ou processo para enriquecer o contexto.
    `cliente_id` e `processo_id` são validados contra o escritório do advogado
    (isolamento multi-tenant — IDs de outros escritórios são silenciosamente ignorados).
    """
    usuario, escritorio = await _carregar_usuario_escritorio(advogado_id, escritorio_id, db)

    # Montar contexto adicional com dados reais do banco
    contexto_partes: list[str] = []
    ref_cliente_id: int | None = None
    ref_processo_id: int | None = None

    if body.cliente_id:
        cliente = await db.get(Cliente, body.cliente_id)
        if cliente and cliente.escritorio_id == escritorio_id:
            contexto_partes.append(f"Cliente: {cliente.nome}")
            ref_cliente_id = cliente.id

    if body.processo_id:
        processo = await db.get(Processo, body.processo_id)
        if processo and processo.escritorio_id == escritorio_id:
            partes = [f"Processo: {processo.numero_cnj}"]
            if processo.tipo_acao:
                partes.append(processo.tipo_acao)
            if processo.fase_processual:
                partes.append(f"Fase: {processo.fase_processual}")
            contexto_partes.append(" — ".join(partes))
            ref_processo_id = processo.id

    system_prompt = SYSTEM_PROMPT_HUB_ADVOGADO_BASE.format(
        nome_usuario=usuario.nome,
        nome_escritorio=escritorio.nome,
        data_hoje=date.today().strftime("%d/%m/%Y"),
    )

    mensagem = body.pergunta
    if contexto_partes:
        mensagem = "Contexto:\n" + "\n".join(contexto_partes) + f"\n\nPergunta: {body.pergunta}"

    try:
        resultado = await escalacao_client.gerar_resposta(
            system_prompt=system_prompt,
            mensagem_usuario=mensagem,
            escritorio_id=escritorio_id,
        )
    except EscalacaoIndisponivelError as exc:
        logger.error("hub_rest_consulta_falhou", erro=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de consulta indisponível. Tente novamente.",
        )

    await _salvar_sessao(
        db,
        SessaoAdvogado(
            escritorio_id=escritorio_id,
            usuario_id=advogado_id,
            mensagem_advogado=body.pergunta,
            resposta_hub=resultado.conteudo,
            intencao="duvida_juridica",
            modelo_ia="claude_opus",
            tokens_input=resultado.tokens_input,
            tokens_output=resultado.tokens_output,
            custo_estimado=resultado.custo_estimado,
            cliente_referenciado_id=ref_cliente_id,
            processo_referenciado_id=ref_processo_id,
            metadata_json={},
        ),
    )

    return ConsultaHubResponse(
        resposta=resultado.conteudo,
        modelo_ia="claude_opus",
        tokens_input=resultado.tokens_input,
        tokens_output=resultado.tokens_output,
        custo_estimado=resultado.custo_estimado,
    )


# ---------------------------------------------------------------------------
# GET /hub/historico
# ---------------------------------------------------------------------------


@router.get(
    "/historico",
    response_model=list[SessaoAdvogadoListItem],
    status_code=status.HTTP_200_OK,
)
async def listar_historico(
    page: int = Query(1, ge=1, description="Página (começa em 1)"),
    limit: int = Query(25, ge=1, le=100, description="Itens por página (máx. 100)"),
    advogado_id: int = Depends(get_advogado_id),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    db: AsyncSession = Depends(get_db),
):
    """
    Lista o histórico de sessões do Hub do advogado autenticado.

    Retorna apenas as sessões do próprio usuário — nunca de outros advogados
    do mesmo escritório (isolamento por `usuario_id`).
    Paginação via `page` e `limit`.
    """
    offset = (page - 1) * limit
    stmt = (
        select(SessaoAdvogado)
        .where(
            SessaoAdvogado.usuario_id == advogado_id,
            SessaoAdvogado.escritorio_id == escritorio_id,
        )
        .order_by(SessaoAdvogado.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    resultado = await db.execute(stmt)
    sessoes = resultado.scalars().all()

    return [
        SessaoAdvogadoListItem(
            id=s.id,
            intencao=s.intencao,
            modelo_ia=s.modelo_ia,
            mensagem_preview=s.mensagem_advogado[:100],
            created_at=s.created_at,
        )
        for s in sessoes
    ]


# ---------------------------------------------------------------------------
# GET /hub/historico/{sessao_id}
# ---------------------------------------------------------------------------


@router.get(
    "/historico/{sessao_id}",
    response_model=SessaoAdvogadoResponse,
    status_code=status.HTTP_200_OK,
)
async def detalhar_sessao(
    sessao_id: int,
    advogado_id: int = Depends(get_advogado_id),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna uma sessão do Hub em detalhe completo.

    Valida que a sessão pertence ao escritório do usuário autenticado —
    IDs de outros escritórios resultam em 403, não 404 (evita enumeração).
    """
    sessao = await db.get(SessaoAdvogado, sessao_id)

    if not sessao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada.",
        )

    # Isolamento multi-tenant: escritorio_id deve bater — nunca expor IDs alheios
    if sessao.escritorio_id != escritorio_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado.",
        )

    return SessaoAdvogadoResponse(
        id=sessao.id,
        intencao=sessao.intencao,
        modelo_ia=sessao.modelo_ia,
        mensagem_advogado=sessao.mensagem_advogado,
        resposta_hub=sessao.resposta_hub,
        tokens_input=sessao.tokens_input,
        tokens_output=sessao.tokens_output,
        custo_estimado=sessao.custo_estimado,
        cliente_referenciado_id=sessao.cliente_referenciado_id,
        processo_referenciado_id=sessao.processo_referenciado_id,
        metadata_json=sessao.metadata_json or {},
        created_at=sessao.created_at,
    )


# ---------------------------------------------------------------------------
# GET /hub/metricas
#
# Restrito a admin — require_advogado já garante advogado|admin, então só
# precisamos checar se o role é estritamente "admin".
# ---------------------------------------------------------------------------


def _require_admin(payload: dict = Depends(_get_payload)) -> dict:
    """Guard adicional: apenas role 'admin' pode acessar métricas agregadas."""
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return payload


@router.get(
    "/metricas",
    response_model=MetricasHubResponse,
    status_code=status.HTTP_200_OK,
)
async def metricas_hub(
    payload: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Métricas agregadas do Hub do Advogado para o mês atual.

    Role: exclusivo para `admin`.
    Agrega por `escritorio_id` do token — nunca retorna dados de outros escritórios.
    """
    escritorio_id: int = int(payload["escritorio_id"])
    agora = datetime.now(timezone.utc)
    inicio_mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    base = (
        SessaoAdvogado.escritorio_id == escritorio_id,
        SessaoAdvogado.created_at >= inicio_mes,
    )

    # Totais
    stmt_totais = select(
        func.count().label("total_sessoes"),
        func.coalesce(func.sum(SessaoAdvogado.tokens_input), 0).label("tokens_input_total"),
        func.coalesce(func.sum(SessaoAdvogado.tokens_output), 0).label("tokens_output_total"),
        func.coalesce(func.sum(SessaoAdvogado.custo_estimado), 0).label("custo_total"),
    ).where(*base)
    row_totais = (await db.execute(stmt_totais)).one()

    # Top 5 intenções
    stmt_intencoes = (
        select(SessaoAdvogado.intencao, func.count().label("total"))
        .where(*base)
        .group_by(SessaoAdvogado.intencao)
        .order_by(func.count().desc())
        .limit(5)
    )
    rows_intencoes = (await db.execute(stmt_intencoes)).all()

    # Advogados mais ativos (top 5)
    stmt_advogados = (
        select(SessaoAdvogado.usuario_id, func.count().label("total_sessoes"))
        .where(*base)
        .group_by(SessaoAdvogado.usuario_id)
        .order_by(func.count().desc())
        .limit(5)
    )
    rows_advogados = (await db.execute(stmt_advogados)).all()

    return MetricasHubResponse(
        mes_atual=agora.strftime("%Y-%m"),
        total_sessoes=row_totais.total_sessoes,
        tokens_input_total=row_totais.tokens_input_total,
        tokens_output_total=row_totais.tokens_output_total,
        custo_total_usd=Decimal(str(row_totais.custo_total)),
        intencoes_top5=[
            IntencaoCount(intencao=r.intencao, total=r.total)
            for r in rows_intencoes
        ],
        advogados_mais_ativos=[
            AdvogadoAtivo(usuario_id=r.usuario_id, total_sessoes=r.total_sessoes)
            for r in rows_advogados
        ],
    )
