"""
Rotas do Hub do Advogado
=========================
Arquivo: feature_1_ia_personalizada/api/routes/hub_advogado.py

Endpoints REST para o Hub do Advogado — complemento à interface WhatsApp.
Permite que front-ends ou integrações consumam o Hub sem depender do WhatsApp.

Acesso: exclusivo para advogado e admin (require_advogado).
Schemas de request/response serão movidos para shared/schemas/hub_advogado.py na Fase 5.
"""

from __future__ import annotations

import dataclasses
import functools
from datetime import date
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.api.middleware.auth import (
    get_advogado_id,
    get_escritorio_id_advogado,
    require_advogado,
)
from feature_1_ia_personalizada.services.ai.escalation_client import (
    EscalacaoClient,
    EscalacaoIndisponivelError,
    TipoAnalise,
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
# Schemas locais
# Serão movidos para shared/schemas/hub_advogado.py na Fase 5.
# ---------------------------------------------------------------------------


class ConsultaHubRequest(BaseModel):
    pergunta: str
    cliente_id: int | None = None
    processo_id: int | None = None


class ConsultaHubResponse(BaseModel):
    resposta: str
    modelo_ia: str
    tokens_input: int
    tokens_output: int
    custo_estimado: Decimal


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


@router.post("/analisar-peticao", status_code=status.HTTP_200_OK)
async def analisar_peticao(
    arquivo: UploadFile = File(..., description="Arquivo PDF da petição (máx. 10 MB)"),
    advogado_id: int = Depends(get_advogado_id),
    escritorio_id: int = Depends(get_escritorio_id_advogado),
    db: AsyncSession = Depends(get_db),
    escalacao_client: EscalacaoClient = Depends(get_escalacao_client),
):
    """
    Analisa uma petição PDF com Claude Opus e retorna insights estruturados.

    - Aceita apenas `application/pdf` (validado por magic bytes, não apenas MIME)
    - Máximo 10 MB
    - Retorna: tipo_peca, pontos_fortes, vulnerabilidades, argumentos_ausentes,
               precedentes_relevantes, sugestoes, score_geral (0-100),
               texto_truncado (bool), tokens_input, tokens_output, custo_estimado
    """
    conteudo_bytes = await arquivo.read()

    # Validar por magic bytes — MIME type é trivialmente falsificável
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

    # Extrair e limpar texto do PDF
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

    # Analisar com Claude Opus
    try:
        analise = await escalacao_client.analisar_peca(
            conteudo_peca=conteudo_envio,
            tipo_analise=TipoAnalise.ANALISE_COMPLETA,
            contexto_processo="Análise solicitada via API REST.",
        )
    except EscalacaoIndisponivelError as exc:
        logger.error("hub_rest_analise_falhou", erro=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de análise indisponível. Tente novamente.",
        )

    # Salvar sessão (falha silenciosa — resposta já produzida)
    await _salvar_sessao(
        db,
        SessaoAdvogado(
            escritorio_id=escritorio_id,
            usuario_id=advogado_id,
            mensagem_advogado=f"[PDF] {arquivo.filename or 'peticao.pdf'}",
            resposta_hub=str(dataclasses.asdict(analise)),
            intencao="analise_peticao",
            modelo_ia="claude_opus",
            tokens_input=analise.tokens_input,
            tokens_output=analise.tokens_output,
            custo_estimado=analise.custo_estimado,
            metadata_json={
                "filename": arquivo.filename,
                "tamanho_bytes": len(conteudo_bytes),
                "texto_truncado": texto_truncado,
            },
        ),
    )

    return {
        **dataclasses.asdict(analise),
        "texto_truncado": texto_truncado,
        "percentual_analisado": (
            round(min(_MAX_CHARS_ANALISE, len(texto)) / len(texto) * 100, 1)
            if texto else 100.0
        ),
    }


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
