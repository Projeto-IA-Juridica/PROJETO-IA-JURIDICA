"""
feature_1_ia_personalizada/api/routes/billing.py
=================================================
Endpoints de billing (Feature 5 — Stripe).

Rotas:
  POST /billing/checkout  → Cria Checkout Session e retorna URL do Stripe
  POST /billing/webhook   → Recebe eventos do Stripe (sem JWT / CSRF)
  GET  /billing/portal    → Cria Billing Portal Session e retorna URL
  GET  /billing/status    → Retorna status da assinatura do escritório

Segurança do webhook:
  O endpoint /billing/webhook é exclusivo do Stripe — não carrega sessão
  de browser. Por isso está na lista de isenção do CSRF middleware e do
  JWTAuthMiddleware. A autenticidade é garantida via HMAC (stripe-signature).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.billing.stripe_service import (
    LIMITES_POR_PLANO,
    LIMITES_TRIAL_POR_PLANO,
    QUOTAS_POR_PLANO,
    QUOTAS_TRIAL_POR_PLANO,
    price_id_para_plano,
    stripe_service,
)
from shared.database.session import get_db
from shared.models.escritorio import Escritorio

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing"])


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _get_escritorio_id(request: Request) -> int:
    payload = getattr(request.state, "user_payload", None)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail="Não autenticado.")
    return int(payload["escritorio_id"])


async def _buscar_por_customer_id(db: AsyncSession, customer_id: str) -> Escritorio | None:
    result = await db.execute(
        select(Escritorio).where(Escritorio.stripe_customer_id == customer_id)
    )
    return result.scalars().first()


async def _buscar_por_subscription_id(db: AsyncSession, subscription_id: str) -> Escritorio | None:
    result = await db.execute(
        select(Escritorio).where(Escritorio.stripe_subscription_id == subscription_id)
    )
    return result.scalars().first()


def _atualizar_quotas(escritorio: Escritorio, plano: str, *, em_trial: bool = False) -> None:
    """Atualiza limites e quota de tokens ao mudar de plano ou sair do trial."""
    if em_trial:
        limites = LIMITES_TRIAL_POR_PLANO.get(plano, LIMITES_POR_PLANO.get(plano))
        quota = QUOTAS_TRIAL_POR_PLANO.get(plano, QUOTAS_POR_PLANO.get(plano))
    else:
        limites = LIMITES_POR_PLANO.get(plano)
        quota = QUOTAS_POR_PLANO.get(plano)
    if limites:
        escritorio.max_processos = limites["max_processos"]
        escritorio.max_clientes = limites["max_clientes"]
    escritorio.quota_tokens_mes = quota


# ---------------------------------------------------------------------------
# Dependency — guard de assinatura
# ---------------------------------------------------------------------------


async def require_assinatura_ativa(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    FastAPI dependency que bloqueia endpoints protegidos quando a assinatura
    está inativa (cancelada, inadimplente ou expirada).

    Status permitidos: 'trialing', 'active'
    Status bloqueados: 'past_due', 'canceled', 'unpaid', 'incomplete'

    Uso nos routers em app.py:
        app.include_router(chat, dependencies=[Depends(require_assinatura_ativa)])
    """
    payload = getattr(request.state, "user_payload", None)
    if not isinstance(payload, dict):
        return  # JWT middleware já cuida disso

    escritorio_id = payload.get("escritorio_id")
    if not escritorio_id:
        return

    escritorio: Escritorio | None = await db.get(Escritorio, int(escritorio_id))
    if not escritorio:
        return

    sub_status = escritorio.assinatura_status or "trialing"

    if sub_status in ("trialing", "active"):
        return  # acesso permitido

    # Montamos uma resposta descritiva dependendo do status
    if sub_status == "past_due":
        detail = (
            "Pagamento em atraso. "
            "Acesse /api/v1/billing/portal para atualizar o método de pagamento."
        )
    elif sub_status in ("canceled", "unpaid"):
        detail = "Assinatura inativa. " "Acesse /api/v1/billing/checkout para reativar sua conta."
    else:
        detail = f"Assinatura com status '{sub_status}'. Contate o suporte."

    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "code": "subscription_inactive",
            "assinatura_status": sub_status,
            "message": detail,
        },
    )


# ---------------------------------------------------------------------------
# POST /billing/checkout
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    plano: str = "basico"


class CheckoutResponse(BaseModel):
    checkout_url: str | None
    stripe_habilitado: bool


@router.post("/checkout", response_model=CheckoutResponse)
async def criar_checkout(
    body: CheckoutRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Cria uma Checkout Session no Stripe e retorna a URL para redirecionamento.

    Se o Stripe não estiver configurado (modo dev), retorna
    `stripe_habilitado: false` e `checkout_url: null`.
    """
    escritorio_id = _get_escritorio_id(request)
    escritorio: Escritorio | None = await db.get(Escritorio, escritorio_id)
    if not escritorio:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")

    planos_validos = {"basico", "profissional", "escritorio"}
    if body.plano not in planos_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Plano inválido. Opções: {', '.join(sorted(planos_validos))}",
        )

    if not stripe_service.habilitado:
        return CheckoutResponse(checkout_url=None, stripe_habilitado=False)

    # Garante que o escritório tem um Customer no Stripe
    if not escritorio.stripe_customer_id:
        customer_id = await asyncio.to_thread(
            stripe_service.criar_customer,
            email=escritorio.email,
            nome=escritorio.nome,
            escritorio_id=escritorio.id,
            cnpj=escritorio.cnpj,
        )
        escritorio.stripe_customer_id = customer_id
        await db.commit()
        await db.refresh(escritorio)

    # Cria a Checkout Session
    assert escritorio.stripe_customer_id is not None
    checkout_url = await asyncio.to_thread(
        stripe_service.criar_checkout_session,
        stripe_customer_id=escritorio.stripe_customer_id,
        plano=body.plano,
    )

    logger.info("billing.checkout_criado", escritorio_id=escritorio_id, plano=body.plano)
    return CheckoutResponse(checkout_url=checkout_url, stripe_habilitado=True)


# ---------------------------------------------------------------------------
# POST /billing/webhook  (sem JWT, sem CSRF — autenticado via stripe-signature)
# ---------------------------------------------------------------------------


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Recebe eventos do Stripe via webhook.

    Autenticado via HMAC (header stripe-signature). Não usa JWT nem CSRF.
    O path /api/v1/billing/webhook está na lista de isenção de ambos os
    middlewares (ver auth.py e csrf.py).

    Eventos tratados:
      checkout.session.completed     → ativa assinatura (trialing ou active)
      invoice.payment_succeeded      → confirma pagamento → active
      invoice.payment_failed         → marca past_due
      customer.subscription.updated  → sync de plano e status
      customer.subscription.deleted  → cancela assinatura
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_service.construir_evento(payload=payload, sig_header=sig_header)
    except ValueError as exc:
        # Stripe não configurado — aceita mas ignora
        logger.warning("billing.webhook_stripe_nao_configurado", detalhe=str(exc))
        return {"received": True, "processed": False}
    except Exception as exc:
        logger.warning("billing.webhook_assinatura_invalida", erro=str(exc))
        raise HTTPException(status_code=400, detail="Assinatura do webhook inválida.") from exc

    event_type: str = event["type"]
    data = event["data"]["object"]

    logger.info("billing.webhook_recebido", event_type=event_type, event_id=event.get("id"))

    try:
        await _processar_evento(event_type=event_type, data=data, db=db)
    except Exception as exc:
        # Log e retorna 200 — o Stripe não precisa de reprocessamento por erros internos.
        # Em caso de erro crítico, o evento pode ser retentado manualmente via
        # Stripe Dashboard → Developers → Webhooks → Event.
        logger.error(
            "billing.webhook_processamento_erro",
            event_type=event_type,
            erro=str(exc),
            exc_info=True,
        )

    return {"received": True}


async def _processar_evento(*, event_type: str, data: dict, db: AsyncSession) -> None:
    """Despacha e processa um evento do Stripe."""

    if event_type == "checkout.session.completed":
        await _on_checkout_completed(data=data, db=db)

    elif event_type == "invoice.payment_succeeded":
        await _on_payment_succeeded(data=data, db=db)

    elif event_type == "invoice.payment_failed":
        await _on_payment_failed(data=data, db=db)

    elif event_type == "customer.subscription.updated":
        await _on_subscription_updated(data=data, db=db)

    elif event_type == "customer.subscription.deleted":
        await _on_subscription_deleted(data=data, db=db)

    else:
        logger.debug("billing.webhook_evento_ignorado", event_type=event_type)


async def _on_checkout_completed(*, data: dict, db: AsyncSession) -> None:
    """
    Evento disparado quando o cliente conclui o checkout.

    Se o plano tem trial, a assinatura começa como 'trialing'.
    Se não tem trial, começa como 'active' imediatamente.
    """
    customer_id: str | None = data.get("customer")
    subscription_id: str | None = data.get("subscription")

    if not customer_id:
        logger.warning("billing.checkout_sem_customer_id")
        return

    escritorio = await _buscar_por_customer_id(db, customer_id)
    if not escritorio:
        logger.warning("billing.escritorio_nao_encontrado_para_customer", customer_id=customer_id)
        return

    if subscription_id:
        escritorio.stripe_subscription_id = subscription_id

        # Busca detalhes da subscription para saber se está em trial
        try:
            import stripe as _stripe

            sub = await asyncio.to_thread(_stripe.Subscription.retrieve, subscription_id)
            sub_status: str = sub.get("status", "active")
            escritorio.assinatura_status = sub_status

            if sub_status == "trialing" and sub.get("trial_end"):
                escritorio.trial_expira_em = datetime.fromtimestamp(sub["trial_end"], tz=UTC)
            if sub.get("current_period_end"):
                escritorio.assinatura_expira_em = datetime.fromtimestamp(
                    sub["current_period_end"], tz=UTC
                )

            # Atualiza plano se detectado via price_id; sempre sincroniza quotas
            items = sub.get("items", {}).get("data", [])
            if items:
                price_id = items[0].get("price", {}).get("id")
                if price_id:
                    novo_plano = price_id_para_plano(price_id)
                    if novo_plano:
                        if novo_plano != escritorio.plano:
                            escritorio.plano = novo_plano
                            escritorio.stripe_price_id = price_id
                        _atualizar_quotas(
                            escritorio, novo_plano, em_trial=(sub_status == "trialing")
                        )

        except Exception as exc:
            logger.warning("billing.checkout_sub_fetch_erro", erro=str(exc))
            # Fallback seguro: marca como ativo
            escritorio.assinatura_status = "active"

    else:
        # Sessão sem subscription (ex: pagamento único) — não esperado, mas seguro
        escritorio.assinatura_status = "active"

    await db.commit()
    logger.info(
        "billing.checkout_concluido",
        escritorio_id=escritorio.id,
        status=escritorio.assinatura_status,
    )


async def _on_payment_succeeded(*, data: dict, db: AsyncSession) -> None:
    """Pagamento confirmado → assinatura ativa."""
    subscription_id: str | None = data.get("subscription")
    if not subscription_id:
        return

    escritorio = await _buscar_por_subscription_id(db, subscription_id)
    if not escritorio:
        return

    escritorio.assinatura_status = "active"

    if data.get("lines", {}).get("data"):
        period_end = data["lines"]["data"][0].get("period", {}).get("end")
        if period_end:
            escritorio.assinatura_expira_em = datetime.fromtimestamp(period_end, tz=UTC)

    await db.commit()
    logger.info("billing.pagamento_confirmado", escritorio_id=escritorio.id)


async def _on_payment_failed(*, data: dict, db: AsyncSession) -> None:
    """Pagamento falhou → marca past_due."""
    subscription_id: str | None = data.get("subscription")
    if not subscription_id:
        return

    escritorio = await _buscar_por_subscription_id(db, subscription_id)
    if not escritorio:
        return

    escritorio.assinatura_status = "past_due"
    await db.commit()
    logger.warning("billing.pagamento_falhou", escritorio_id=escritorio.id)


async def _on_subscription_updated(*, data: dict, db: AsyncSession) -> None:
    """
    Assinatura atualizada — sincroniza status e plano.
    Disparado em: upgrade/downgrade, reativação, mudança de período, etc.
    """
    subscription_id: str | None = data.get("id")
    if not subscription_id:
        return

    escritorio = await _buscar_por_subscription_id(db, subscription_id)
    if not escritorio:
        return

    novo_status: str = data.get("status", escritorio.assinatura_status)
    escritorio.assinatura_status = novo_status

    # Atualiza trial_expira_em se trial
    if novo_status == "trialing" and data.get("trial_end"):
        escritorio.trial_expira_em = datetime.fromtimestamp(data["trial_end"], tz=UTC)

    # Atualiza período corrente
    if data.get("current_period_end"):
        escritorio.assinatura_expira_em = datetime.fromtimestamp(data["current_period_end"], tz=UTC)

    # Atualiza plano e quotas; sempre sincroniza para refletir trial/active
    plano_atual = escritorio.plano
    items = data.get("items", {}).get("data", [])
    if items:
        price_id: str | None = items[0].get("price", {}).get("id")
        if price_id:
            novo_plano = price_id_para_plano(price_id)
            if novo_plano:
                if novo_plano != escritorio.plano:
                    escritorio.plano = novo_plano
                    escritorio.stripe_price_id = price_id
                    plano_atual = novo_plano
                    logger.info(
                        "billing.plano_alterado",
                        escritorio_id=escritorio.id,
                        plano=novo_plano,
                    )
    _atualizar_quotas(escritorio, plano_atual, em_trial=(novo_status == "trialing"))

    await db.commit()
    logger.info(
        "billing.assinatura_atualizada",
        escritorio_id=escritorio.id,
        status=novo_status,
    )


async def _on_subscription_deleted(*, data: dict, db: AsyncSession) -> None:
    """Assinatura cancelada → marca como canceled."""
    subscription_id: str | None = data.get("id")
    if not subscription_id:
        return

    escritorio = await _buscar_por_subscription_id(db, subscription_id)
    if not escritorio:
        return

    escritorio.assinatura_status = "canceled"
    await db.commit()
    logger.warning("billing.assinatura_cancelada", escritorio_id=escritorio.id)


# ---------------------------------------------------------------------------
# GET /billing/portal
# ---------------------------------------------------------------------------


class PortalResponse(BaseModel):
    portal_url: str | None
    stripe_habilitado: bool


@router.get("/portal", response_model=PortalResponse)
async def criar_portal(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Cria uma Billing Portal Session e retorna a URL para o cliente
    gerenciar sua assinatura (cartão, plano, cancelamento, faturas).
    """
    escritorio_id = _get_escritorio_id(request)
    escritorio: Escritorio | None = await db.get(Escritorio, escritorio_id)
    if not escritorio:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")

    if not stripe_service.habilitado:
        return PortalResponse(portal_url=None, stripe_habilitado=False)

    if not escritorio.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Este escritório ainda não tem conta Stripe. "
                "Complete o checkout em /api/v1/billing/checkout primeiro."
            ),
        )

    portal_url = await asyncio.to_thread(
        stripe_service.criar_portal_session,
        stripe_customer_id=escritorio.stripe_customer_id,
    )

    logger.info("billing.portal_acessado", escritorio_id=escritorio_id)
    return PortalResponse(portal_url=portal_url, stripe_habilitado=True)


# ---------------------------------------------------------------------------
# GET /billing/status
# ---------------------------------------------------------------------------


class StatusAssinaturaResponse(BaseModel):
    plano: str
    assinatura_status: str
    stripe_habilitado: bool
    stripe_customer_id: str | None
    trial_expira_em: datetime | None
    assinatura_expira_em: datetime | None
    acesso_ativo: bool  # True se o escritório pode usar as features pagas


@router.get("/status", response_model=StatusAssinaturaResponse)
async def status_assinatura(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna o status atual da assinatura do escritório autenticado.
    Usado pelo frontend para exibir banners de pagamento pendente.
    """
    escritorio_id = _get_escritorio_id(request)
    escritorio: Escritorio | None = await db.get(Escritorio, escritorio_id)
    if not escritorio:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")

    sub_status = escritorio.assinatura_status or "trialing"
    acesso_ativo = sub_status in ("trialing", "active")

    return StatusAssinaturaResponse(
        plano=escritorio.plano,
        assinatura_status=sub_status,
        stripe_habilitado=stripe_service.habilitado,
        stripe_customer_id=escritorio.stripe_customer_id,
        trial_expira_em=escritorio.trial_expira_em,
        assinatura_expira_em=escritorio.assinatura_expira_em,
        acesso_ativo=acesso_ativo,
    )
