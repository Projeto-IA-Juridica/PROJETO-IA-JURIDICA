"""
Webhook do número-vitrine — SEPARADO do webhook do produto.

O chip-vitrine tem instância Evolution própria e aponta para /vendas/webhook,
nunca para /webhook/whatsapp. Assim a conversa da Clara e o atendimento dos
clientes dos advogados jamais se cruzam: são chips, instâncias e rotas distintas.

Fluxo:
  1. valida a apikey da instância de vendas (não a do produto)
  2. extrai número + texto do payload Evolution (parser lean e tolerante)
  3. resolve/cria o AlvoVendas daquele número no tenant de vendas
     - número novo (scaneou o QR) → cria alvo origem=inbound, já 'respondeu'
     - número em cadência/abordado → marca 'respondeu' (sai da cadência)
  4. enfileira a task da conversa (buffer + Clara + humanização)

Sem JWT (recebe de terceiro), como o webhook do produto. Guardado por apikey.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_vendas import config as vconfig
from feature_vendas.models.alvo_vendas import AlvoVendas
from shared.database.session import get_db

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/vendas", tags=["Vendas — Vitrine"])


def _extrair(body: dict[str, Any]) -> tuple[str, str, str | None] | None:
    """Devolve (numero, texto, message_id) ou None se não for mensagem de terceiro."""
    if body.get("event") != "messages.upsert":
        return None
    data = body.get("data") or {}
    msg = data[0] if isinstance(data, list) and data else data
    if not isinstance(msg, dict):
        return None

    key = msg.get("key", {})
    if key.get("fromMe"):
        return None  # não responde a si mesmo (loop)

    remote = key.get("remoteJid", "") or ""
    remote_alt = key.get("remoteJidAlt", "") or ""
    if "@g.us" in remote:
        return None  # ignora grupos
    jid = remote_alt if "@lid" in remote and remote_alt else remote
    numero = jid.split("@")[0]
    if not numero.isdigit():
        return None

    conteudo = msg.get("message", {}) or {}
    texto = (
        conteudo.get("conversation") or conteudo.get("extendedTextMessage", {}).get("text") or ""
    ).strip()
    if not texto:
        return None

    return numero, texto, key.get("id")


@router.post("/webhook", include_in_schema=False)
async def webhook_vitrine(
    request: Request,
    apikey: str | None = Header(default=None),
) -> dict[str, Any]:
    import hmac

    esperado = vconfig.VENDAS_EVOLUTION_API_KEY
    if not esperado or not apikey or not hmac.compare_digest(apikey, esperado):
        raise HTTPException(status_code=401, detail="Unauthorized")

    if vconfig.VENDAS_TENANT_ID is None:
        raise HTTPException(status_code=503, detail="Tenant de vendas não configurado")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido") from None

    extraido = _extrair(body)
    if extraido is None:
        return {"status": "ignored"}
    numero, texto, message_id = extraido

    # Instância que RECEBEU a mensagem: a Clara responde por ela (o mesmo chip
    # em que o lead escreveu), não pela instância de disparo.
    instancia = str(body.get("instance") or vconfig.VENDAS_EVOLUTION_INSTANCE or "")

    async for db in get_db():
        alvo = await _resolver_alvo(db, numero, texto)

    # Enfileira a conversa (buffer + Clara + humanização) — import tardio para
    # não acoplar a rota ao Celery quando a feature está desligada.
    from feature_vendas.workers.conversa_worker import responder_conversa

    responder_conversa.delay(
        alvo_id=alvo,
        numero=numero,
        texto=texto,
        message_id=message_id,
        instancia=instancia,
    )
    return {"status": "enfileirado"}


async def _resolver_alvo(db: AsyncSession, numero: str, primeira_msg: str) -> int:
    """
    Acha (ou cria) o alvo daquele número. Para inbound cru, tenta inferir a
    origem pela primeira mensagem (texto pré-preenchido do link wa.me de cada
    canal): currículo, calculadora, indicação, site.
    """
    from feature_vendas.services.contexto_lead import detectar_origem

    tenant = vconfig.VENDAS_TENANT_ID
    alvo = (
        await db.execute(
            select(AlvoVendas).where(
                AlvoVendas.escritorio_id == tenant, AlvoVendas.whatsapp == numero
            )
        )
    ).scalar_one_or_none()

    if alvo is None:
        origem = detectar_origem(primeira_msg) or "inbound"
        alvo = AlvoVendas(
            escritorio_id=tenant,
            nome_escritorio="(inbound — vitrine)",
            whatsapp=numero,
            origem=origem,
            status="respondeu",
        )
        db.add(alvo)
    elif alvo.status in {"abordado", "em_cadencia", "fila_envio", "fila_excecao"}:
        # Respondeu à abordagem: sai da cadência, a Clara assume.
        alvo.status = "respondeu"
        from datetime import UTC, datetime

        alvo.respondeu_em = datetime.now(UTC)
        alvo.proximo_toque_em = None

    await db.commit()
    await db.refresh(alvo)
    return alvo.id
