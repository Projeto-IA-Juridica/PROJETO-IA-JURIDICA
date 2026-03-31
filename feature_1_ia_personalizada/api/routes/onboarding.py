"""
feature_1_ia_personalizada/api/routes/onboarding.py
=====================================================
Módulo de Onboarding Automatizado do Escritório — Feature 4.

Fluxo de 5 etapas:
    0 → POST /onboarding/register           → público — cria escritório + admin
    1 → POST /onboarding/configure-ia       → JWT admin — persona e horários
    2 → POST /onboarding/import-processos   → JWT admin — importa CSV
    3 → POST /onboarding/connect-whatsapp   → JWT admin — cria instância Evolution
    4 → POST /onboarding/configure-templates → JWT admin — templates personalizados
    5 → POST /onboarding/go-live            → JWT admin — ativa monitoramento

    GET /onboarding/status                  → JWT admin — checklist atual
    GET /onboarding/whatsapp-status         → JWT admin — polling QR / conexão
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.import_clientes import processar_csv
from shared.config.settings import settings
from shared.database.session import get_db
from shared.models.escritorio import Escritorio
from shared.models.processo import Processo
from shared.models.usuario import Usuario
from shared.schemas.escritorio import EscritorioResponse
from shared.security.encryption import hash_senha
from shared.security.jwt import criar_refresh_token, criar_token
from shared.utils.validators import normalizar_cnpj, validar_cnpj, validar_oab

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


# ---------------------------------------------------------------------------
# Schemas de entrada
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    nome_escritorio: str = Field(min_length=2, max_length=200)
    cnpj: str = Field(description="CNPJ com ou sem formatação")
    email_admin: EmailStr
    senha: str = Field(min_length=8, description="Senha do admin (mínimo 8 caracteres)")
    nome_responsavel: str = Field(min_length=2, max_length=200)
    oab_responsavel: str = Field(description="OAB do responsável — formato UFNNNNN")

    @field_validator("cnpj")
    @classmethod
    def _validar_cnpj(cls, v: str) -> str:
        if not validar_cnpj(v):
            raise ValueError("CNPJ inválido — verifique os dígitos verificadores")
        return normalizar_cnpj(v)

    @field_validator("oab_responsavel")
    @classmethod
    def _validar_oab(cls, v: str) -> str:
        normalizado = v.upper().strip()
        if not validar_oab(normalizado):
            raise ValueError("OAB inválida — formato esperado: UFNNNNN (ex: SP123456)")
        return normalizado


class RegisterResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    escritorio: EscritorioResponse


class ConfigurarIARequest(BaseModel):
    persona_nome: str = Field(
        default="Assistente Jurídico",
        min_length=2,
        max_length=100,
        description="Nome da IA exibido aos clientes",
    )
    persona_tom: str = Field(
        default="formal",
        description="Tom da IA: formal | amigavel | neutro",
    )
    horario_inicio: str = Field(
        default="08:00",
        pattern=r"^\d{2}:\d{2}$",
        description="Horário de início do atendimento (HH:MM)",
    )
    horario_fim: str = Field(
        default="18:00",
        pattern=r"^\d{2}:\d{2}$",
        description="Horário de fim do atendimento (HH:MM)",
    )

    @field_validator("persona_tom")
    @classmethod
    def _validar_tom(cls, v: str) -> str:
        normalizado = v.lower().strip()
        if normalizado not in {"formal", "amigavel", "neutro"}:
            raise ValueError("Tom inválido — opções: formal, amigavel, neutro")
        return normalizado


class ConfigurarTemplatesRequest(BaseModel):
    template_boas_vindas: str | None = Field(
        default=None,
        max_length=500,
        description="Deve conter {nome_cliente}",
    )
    template_atualizacao: str | None = Field(
        default=None,
        max_length=500,
        description="Deve conter {nome_cliente} e {resumo_andamento}",
    )
    template_sem_novidade: str | None = Field(
        default=None,
        max_length=500,
        description="Deve conter {nome_cliente}",
    )

    @field_validator("template_boas_vindas")
    @classmethod
    def _validar_boas_vindas(cls, v: str | None) -> str | None:
        if v and "{nome_cliente}" not in v:
            raise ValueError("template_boas_vindas deve conter a variável {nome_cliente}")
        return v

    @field_validator("template_atualizacao")
    @classmethod
    def _validar_atualizacao(cls, v: str | None) -> str | None:
        if v and "{resumo_andamento}" not in v:
            raise ValueError("template_atualizacao deve conter a variável {resumo_andamento}")
        return v

    @field_validator("template_sem_novidade")
    @classmethod
    def _validar_sem_novidade(cls, v: str | None) -> str | None:
        if v and "{nome_cliente}" not in v:
            raise ValueError("template_sem_novidade deve conter a variável {nome_cliente}")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _exigir_admin(request: Request) -> dict:
    """Valida que o token pertence a um admin e retorna o payload."""
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Token JWT ausente.")
    payload = request.state.user_payload
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem realizar o onboarding.")
    return payload


async def _obter_escritorio_do_token(
    request: Request, db: AsyncSession
) -> Escritorio:
    """Retorna o escritório do admin autenticado."""
    payload = _exigir_admin(request)
    escritorio_id = payload.get("escritorio_id")
    escritorio = await db.get(Escritorio, escritorio_id)
    if not escritorio:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")
    return escritorio


def _preview_boas_vindas(persona_nome: str, persona_tom: str, nome_escritorio: str) -> str:
    """Gera uma preview do texto de apresentação da IA."""
    if persona_tom == "amigavel":
        return (
            f"Oi! Eu sou {persona_nome}, do {nome_escritorio}. "
            "Estou aqui pra te ajudar com informações sobre seu processo. 😊"
        )
    elif persona_tom == "neutro":
        return (
            f"Olá. Sou {persona_nome}, do {nome_escritorio}. "
            "Estou disponível para informações sobre seu processo."
        )
    else:  # formal
        return (
            f"Prezado(a) cliente, meu nome é {persona_nome} e faço parte do time do {nome_escritorio}. "
            "Estou à sua disposição para esclarecimentos sobre seu processo."
        )


# ---------------------------------------------------------------------------
# Etapa 0 — Registro (público)
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria escritório e usuário admin (público)",
)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Cria o escritório e o usuário admin em uma única transação.
    Retorna JWT pronto para uso nas próximas etapas do onboarding.
    Idempotente: retorna 409 se o CNPJ já estiver cadastrado.
    """
    # Idempotência — CNPJ único
    stmt_cnpj = select(Escritorio).where(Escritorio.cnpj == body.cnpj)
    existente = (await db.execute(stmt_cnpj)).scalars().first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="CNPJ já cadastrado. Faça login em /auth/login.",
        )

    # Cria escritório
    escritorio = Escritorio(
        nome=body.nome_escritorio,
        cnpj=body.cnpj,
        email=body.email_admin,
        oab_responsavel=body.oab_responsavel,
        nome_responsavel=body.nome_responsavel,
        plano="basico",
        onboarding_etapa=0,
        onboarding_completo=False,
    )
    db.add(escritorio)
    await db.flush()  # gera escritorio.id sem commitar

    # Cria usuário admin
    usuario = Usuario(
        escritorio_id=escritorio.id,
        nome=body.nome_responsavel,
        email=body.email_admin,
        senha_hash=hash_senha(body.senha),
        role="admin",
        oab=body.oab_responsavel,
        ativo=True,
    )
    db.add(usuario)
    await db.commit()
    await db.refresh(escritorio)
    await db.refresh(usuario)

    logger.info("onboarding_registro", escritorio_id=escritorio.id, cnpj=body.cnpj)

    # Gera tokens
    access_token = criar_token(
        user_id=usuario.id,
        escritorio_id=escritorio.id,
        role="admin",
    )
    refresh_token = criar_refresh_token(user_id=usuario.id)

    return RegisterResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_EXPIRATION_MINUTES * 60,
        escritorio=EscritorioResponse.model_validate(escritorio),
    )


# ---------------------------------------------------------------------------
# Etapa 1 — Configurar IA (persona e horários)
# ---------------------------------------------------------------------------


@router.post(
    "/configure-ia",
    summary="Configura persona e horários da IA — etapa 1",
)
async def configure_ia(
    body: ConfigurarIARequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Salva nome, tom e horários da IA. Retorna preview da mensagem de apresentação.
    Avança onboarding_etapa para 1.
    """
    from datetime import datetime as _dt

    escritorio = await _obter_escritorio_do_token(request, db)

    # Parseia horários via strptime — mais robusto que split manual
    try:
        h_inicio = _dt.strptime(body.horario_inicio, "%H:%M").time()
        h_fim = _dt.strptime(body.horario_fim, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Horários inválidos — use o formato HH:MM.")

    if h_inicio >= h_fim:
        raise HTTPException(
            status_code=400,
            detail="horario_inicio deve ser anterior a horario_fim (sem suporte overnight).",
        )

    escritorio.persona_nome = body.persona_nome
    escritorio.persona_tom = body.persona_tom
    escritorio.horario_inicio = h_inicio
    escritorio.horario_fim = h_fim
    if (escritorio.onboarding_etapa or 0) < 1:
        escritorio.onboarding_etapa = 1

    await db.commit()

    preview = _preview_boas_vindas(body.persona_nome, body.persona_tom, escritorio.nome)
    logger.info("onboarding_configure_ia", escritorio_id=escritorio.id, tom=body.persona_tom)

    return {
        "etapa": 1,
        "preview": preview,
        "persona_nome": body.persona_nome,
        "persona_tom": body.persona_tom,
    }


# ---------------------------------------------------------------------------
# Etapa 2 — Importar processos via CSV
# ---------------------------------------------------------------------------


@router.post(
    "/import-processos",
    summary="Importa processos via CSV — etapa 2",
)
async def import_processos(
    request: Request,
    file: UploadFile = File(..., description="Arquivo CSV com clientes e processos"),
    preview: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Reutiliza a lógica de admin_import.py para importação em massa.
    Avança onboarding_etapa para 2 após importação bem-sucedida (preview=false).
    """
    payload = _exigir_admin(request)
    escritorio_id: int = payload["escritorio_id"]

    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="O arquivo deve ter extensão .csv.")

    conteudo = await file.read()
    if len(conteudo) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo muito grande. O limite é 5 MB.")

    try:
        resultado = await processar_csv(
            conteudo=conteudo,
            escritorio_id=escritorio_id,
            db=db,
            preview=preview,
        )
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Erro de encoding no arquivo. Salve o CSV com encoding UTF-8.",
        ) from exc

    # Avança etapa somente em importação real
    if not preview:
        escritorio = await db.get(Escritorio, escritorio_id)
        if escritorio and (escritorio.onboarding_etapa or 0) < 2:
            escritorio.onboarding_etapa = 2
            await db.commit()

    logger.info("onboarding_import_processos", escritorio_id=escritorio_id, preview=preview)
    return {"etapa": 2 if not preview else None, **resultado}


# ---------------------------------------------------------------------------
# Etapa 3 — Conectar WhatsApp
# ---------------------------------------------------------------------------


@router.post(
    "/connect-whatsapp",
    summary="Cria instância WhatsApp e retorna QR Code — etapa 3",
)
async def connect_whatsapp(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Cria a instância na Evolution API e retorna o QR Code base64 para o cliente escanear.
    Ao conectar, o frontend deve fazer polling em GET /onboarding/whatsapp-status.
    """
    escritorio = await _obter_escritorio_do_token(request, db)

    instance_name = f"escritorio_{escritorio.id}"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # 1. Cria a instância
            resp = await client.post(
                f"{settings.EVOLUTION_API_URL}/instance/create",
                headers={"apikey": settings.EVOLUTION_API_KEY},
                json={
                    "instanceName": instance_name,
                    "qrcode": True,
                    "integration": "WHATSAPP-BAILEYS",
                },
            )

            if resp.status_code in (200, 201):
                data = resp.json()
            elif resp.status_code == 409:
                # Instância já existe — reconecta e busca QR atual
                resp_connect = await client.get(
                    f"{settings.EVOLUTION_API_URL}/instance/connect/{instance_name}",
                    headers={"apikey": settings.EVOLUTION_API_KEY},
                )
                if resp_connect.status_code not in (200, 201):
                    detail = f"Instância já existe mas falhou ao reconectar (HTTP {resp_connect.status_code})."
                    try:
                        raw = resp_connect.text
                        if raw:
                            detail = f"{detail} Resposta: {raw[:400]}"
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=502,
                        detail=detail,
                    )
                data = resp_connect.json()
            else:
                detail = f"Evolution API retornou erro inesperado (HTTP {resp.status_code})."
                try:
                    raw = resp.text
                    if raw:
                        detail = f"{detail} Resposta: {raw[:400]}"
                except Exception:
                    pass
                raise HTTPException(
                    status_code=502,
                    detail=detail,
                )

    except HTTPException:
        # Preserva detalhes de erro já preparados acima.
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504, detail="Evolution API não respondeu a tempo."
        ) from exc
    except httpx.HTTPError as exc:
        logger.error("evolution_connect_http_error", erro=str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"Falha de comunicação com Evolution API: {str(exc)[:300]}",
        ) from exc
    except Exception as exc:
        logger.error("evolution_connect_error", erro=str(exc))
        raise HTTPException(status_code=502, detail="Erro ao conectar com a Evolution API.")

    # Persiste o nome da instância no escritório
    escritorio.webhook_whatsapp_instance = instance_name
    if (escritorio.onboarding_etapa or 0) < 3:
        escritorio.onboarding_etapa = 3
    await db.commit()

    qr_code = data.get("qrcode", {})
    logger.info("onboarding_connect_whatsapp", escritorio_id=escritorio.id)

    return {
        "etapa": 3,
        "instance_name": instance_name,
        "qr_code": qr_code,
        "status": data.get("instance", {}).get("state", "qr"),
    }


@router.get(
    "/whatsapp-status",
    summary="Verifica status da conexão WhatsApp (polling)",
)
async def whatsapp_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint de polling para o frontend verificar se o WhatsApp foi conectado.
    Retorna `connected=true` quando a instância estiver online.
    """
    escritorio = await _obter_escritorio_do_token(request, db)

    if not escritorio.webhook_whatsapp_instance:
        return {"connected": False, "state": "not_configured"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.EVOLUTION_API_URL}/instance/connectionState/{escritorio.webhook_whatsapp_instance}",
                headers={"apikey": settings.EVOLUTION_API_KEY},
            )
            data = resp.json()
    except Exception:
        return {"connected": False, "state": "error"}

    state = data.get("instance", {}).get("state", "unknown")
    connected = state == "open"

    if connected and (escritorio.onboarding_etapa or 0) < 3:
        escritorio.onboarding_etapa = 3
        await db.commit()

    return {"connected": connected, "state": state}


# ---------------------------------------------------------------------------
# Etapa 4 — Configurar Templates
# ---------------------------------------------------------------------------


@router.post(
    "/configure-templates",
    summary="Salva templates personalizados de mensagem — etapa 4",
)
async def configure_templates(
    body: ConfigurarTemplatesRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Salva os templates personalizados. Se não informados, o sistema usará os defaults.
    Avança onboarding_etapa para 4.
    """
    escritorio = await _obter_escritorio_do_token(request, db)

    if body.template_boas_vindas:
        escritorio.template_boas_vindas = body.template_boas_vindas
    if body.template_atualizacao:
        escritorio.template_atualizacao = body.template_atualizacao
    if body.template_sem_novidade:
        escritorio.template_sem_novidade = body.template_sem_novidade

    if (escritorio.onboarding_etapa or 0) < 4:
        escritorio.onboarding_etapa = 4
    await db.commit()

    logger.info("onboarding_configure_templates", escritorio_id=escritorio.id)
    return {"etapa": 4, "mensagem": "Templates salvos com sucesso."}


# ---------------------------------------------------------------------------
# Etapa 5 — Go Live
# ---------------------------------------------------------------------------


@router.post(
    "/go-live",
    summary="Ativa monitoramento e conclui onboarding — etapa 5",
)
async def go_live(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    - Ativa `monitoramento_ativo=True` para todos os processos importados.
    - Dispara task Celery de ingestão de jurisprudência pública (RAG).
    - Marca `onboarding_completo=True`.
    """
    escritorio = await _obter_escritorio_do_token(request, db)

    # Ativa monitoramento de todos os processos do escritório
    stmt = select(Processo).where(Processo.escritorio_id == escritorio.id)
    result = await db.execute(stmt)
    processos = result.scalars().all()
    processos_ativados = 0
    for processo in processos:
        if not processo.monitoramento_ativo:
            processo.monitoramento_ativo = True
            processos_ativados += 1

    # Conclui onboarding
    escritorio.onboarding_etapa = 5
    escritorio.onboarding_completo = True
    escritorio.onboarding_at = datetime.now(timezone.utc)
    await db.commit()

    # Dispara ingestão RAG de jurisprudência pública (Feature 1)
    try:
        from feature_1_ia_personalizada.workers.ingest_documentos import (
            ingest_jurisprudencia_publica,
        )
        # Coleta tipos de ação únicos dos processos
        tipos_acao = list({
            p.tipo_acao for p in processos if p.tipo_acao
        })[:5]  # máx 5 tipos para não sobrecarregar
        for tipo in tipos_acao:
            ingest_jurisprudencia_publica.delay(tipo, None, escritorio.id)
    except Exception as exc:
        # RAG é opcional — não bloqueia o go-live
        logger.warning("go_live_rag_skip", erro=str(exc))

    logger.info(
        "onboarding_go_live",
        escritorio_id=escritorio.id,
        processos_ativados=processos_ativados,
    )

    return {
        "etapa": 5,
        "onboarding_completo": True,
        "processos_ativados": processos_ativados,
        "mensagem": (
            f"Parabéns! O {escritorio.nome} está operacional. "
            f"{processos_ativados} processo(s) com monitoramento ativado."
        ),
    }


# ---------------------------------------------------------------------------
# GET /onboarding/status — checklist
# ---------------------------------------------------------------------------


@router.get(
    "/status",
    summary="Retorna checklist do onboarding",
)
async def onboarding_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna a etapa atual e o checklist completo do onboarding.
    """
    escritorio = await _obter_escritorio_do_token(request, db)

    etapa = escritorio.onboarding_etapa or 0
    total_etapas = 5

    etapas = [
        {
            "numero": 0,
            "nome": "Registro",
            "concluida": etapa >= 0,
            "descricao": "Escritório e usuário admin criados",
        },
        {
            "numero": 1,
            "nome": "Configuração da IA",
            "concluida": etapa >= 1,
            "descricao": "Persona, tom e horários configurados",
        },
        {
            "numero": 2,
            "nome": "Importação de Processos",
            "concluida": etapa >= 2,
            "descricao": "Clientes e processos importados",
        },
        {
            "numero": 3,
            "nome": "Conexão WhatsApp",
            "concluida": etapa >= 3,
            "descricao": "Instância WhatsApp conectada",
        },
        {
            "numero": 4,
            "nome": "Templates de Mensagem",
            "concluida": etapa >= 4,
            "descricao": "Templates personalizados configurados",
        },
        {
            "numero": 5,
            "nome": "Go Live",
            "concluida": etapa >= 5,
            "descricao": "Monitoramento ativo para todos os processos",
        },
    ]

    percentual = int((etapa / total_etapas) * 100)

    return {
        "onboarding_completo": escritorio.onboarding_completo or False,
        "etapa_atual": etapa,
        "percentual_completo": percentual,
        "proxima_etapa": etapa + 1 if etapa < total_etapas else None,
        "etapas": etapas,
        "escritorio": {
            "id": escritorio.id,
            "nome": escritorio.nome,
            "persona_nome": escritorio.persona_nome,
            "persona_tom": escritorio.persona_tom,
            "whatsapp_conectado": bool(escritorio.webhook_whatsapp_instance),
        },
    }
