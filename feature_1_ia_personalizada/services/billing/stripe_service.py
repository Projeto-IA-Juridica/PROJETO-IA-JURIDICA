"""
feature_1_ia_personalizada/services/billing/stripe_service.py
==============================================================
Camada de serviço para integração com o Stripe.

Responsabilidades:
  - Criar e gerenciar Customers
  - Criar Checkout Sessions (compra de assinatura)
  - Criar Billing Portal Sessions (auto-serviço do cliente)
  - Verificar e despachar eventos de Webhook

Modo degradado:
  Se STRIPE_SECRET_KEY não estiver configurado, todos os métodos retornam
  valores seguros (None / vazio) sem lançar exceção. Isso mantém o
  onboarding funcional em desenvolvimento sem Stripe configurado.

Mapeamento de planos:
  basico        → STRIPE_PRICE_ID_BASICO        (R$ 497/mês)
  profissional  → STRIPE_PRICE_ID_PROFISSIONAL  (R$ 1.997/mês)
  escritorio    → STRIPE_PRICE_ID_ESCRITORIO    (R$ 4.997/mês)
  enterprise    → sem price_id (contrato manual)
"""

from __future__ import annotations

from typing import Any

import structlog

from shared.config.settings import settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Lazy import do stripe — evita erro de import se o pacote não estiver
# instalado (ambiente mínimo sem requirements-f1.txt).
# ---------------------------------------------------------------------------


def _get_stripe() -> Any:
    try:
        import stripe as _stripe

        return _stripe
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Mapeamento plano → Price ID
# ---------------------------------------------------------------------------


def _price_id_para_plano(plano: str) -> str | None:
    """Retorna o Stripe Price ID para um dado plano interno."""
    mapa = {
        "basico": settings.STRIPE_PRICE_ID_BASICO,
        "profissional": settings.STRIPE_PRICE_ID_PROFISSIONAL,
        "escritorio": settings.STRIPE_PRICE_ID_ESCRITORIO,
    }
    return mapa.get(plano)


def plano_para_price_id(plano: str) -> str | None:
    """Alias público — usado pelo webhook para reverse-map."""
    return _price_id_para_plano(plano)


def price_id_para_plano(price_id: str) -> str | None:
    """Reverse-map: Stripe Price ID → nome do plano interno."""
    mapa = {
        settings.STRIPE_PRICE_ID_BASICO: "basico",
        settings.STRIPE_PRICE_ID_PROFISSIONAL: "profissional",
        settings.STRIPE_PRICE_ID_ESCRITORIO: "escritorio",
    }
    return mapa.get(price_id)


# ---------------------------------------------------------------------------
# Quotas por plano (sincronizadas com migration 015)
# ---------------------------------------------------------------------------

QUOTAS_POR_PLANO: dict[str, int | None] = {
    "basico": 500_000,
    "profissional": 2_000_000,
    "escritorio": 5_000_000,
    "enterprise": None,  # sem limite
}

LIMITES_POR_PLANO: dict[str, dict[str, int]] = {
    "basico": {"max_processos": 30, "max_clientes": 50},
    "profissional": {"max_processos": 300, "max_clientes": 500},
    "escritorio": {"max_processos": 500, "max_clientes": 10_000},
    "enterprise": {"max_processos": 99_999, "max_clientes": 99_999},
}

# Quotas reduzidas durante os 7 dias de trial (~20% do plano pago).
# Protege contra uso abusivo sem prejudicar a experiência de avaliação.
QUOTAS_TRIAL_POR_PLANO: dict[str, int | None] = {
    "basico": 100_000,
    "profissional": 400_000,
    "escritorio": 1_000_000,
    "enterprise": None,
}

LIMITES_TRIAL_POR_PLANO: dict[str, dict[str, int]] = {
    "basico": {"max_processos": 10, "max_clientes": 20},
    "profissional": {"max_processos": 60, "max_clientes": 100},
    "escritorio": {"max_processos": 100, "max_clientes": 500},
    "enterprise": {"max_processos": 99_999, "max_clientes": 99_999},
}


# ---------------------------------------------------------------------------
# Serviço
# ---------------------------------------------------------------------------


class StripeService:
    """
    Wrapper sobre o SDK do Stripe.

    Todos os métodos são síncronos (o Stripe SDK é síncrono).
    O FastAPI chama-os em endpoints async via `await asyncio.to_thread(...)`.
    """

    def __init__(self) -> None:
        self._stripe = _get_stripe()
        if self._stripe and settings.STRIPE_SECRET_KEY:
            self._stripe.api_key = settings.STRIPE_SECRET_KEY
            self._habilitado = True
        else:
            self._habilitado = False
            if not self._stripe:
                logger.warning("stripe.sdk_nao_instalado")
            else:
                logger.warning("stripe.secret_key_ausente — billing desabilitado")

    @property
    def habilitado(self) -> bool:
        return self._habilitado

    # ------------------------------------------------------------------
    # Customer
    # ------------------------------------------------------------------

    def criar_customer(self, *, email: str, nome: str, escritorio_id: int, cnpj: str) -> str | None:
        """
        Cria um Customer no Stripe e retorna o ID (cus_xxx).
        Retorna None em modo degradado.
        """
        if not self._habilitado:
            return None
        try:
            customer = self._stripe.Customer.create(
                email=email,
                name=nome,
                metadata={
                    "escritorio_id": str(escritorio_id),
                    "cnpj": cnpj,
                },
                preferred_locales=["pt-BR"],
            )
            logger.info(
                "stripe.customer_criado", customer_id=customer.id, escritorio_id=escritorio_id
            )
            return str(customer.id)
        except Exception as exc:
            logger.error("stripe.criar_customer_erro", erro=str(exc), escritorio_id=escritorio_id)
            raise

    # ------------------------------------------------------------------
    # Checkout Session
    # ------------------------------------------------------------------

    def criar_checkout_session(
        self,
        *,
        stripe_customer_id: str,
        plano: str,
        trial_days: int | None = None,
    ) -> str | None:
        """
        Cria uma Checkout Session para assinatura e retorna a URL hospedada pelo Stripe.

        Args:
            stripe_customer_id: ID do Customer no Stripe.
            plano: Nome do plano interno (basico | profissional | escritorio).
            trial_days: Dias de trial gratuito. None = usa STRIPE_TRIAL_DAYS das settings.

        Returns:
            URL do checkout ou None em modo degradado.
        """
        if not self._habilitado:
            return None

        price_id = _price_id_para_plano(plano)
        if not price_id:
            raise ValueError(
                f"Plano '{plano}' não tem Price ID configurado. "
                "Defina STRIPE_PRICE_ID_<PLANO> no .env."
            )

        dias_trial = trial_days if trial_days is not None else settings.STRIPE_TRIAL_DAYS

        session_kwargs: dict = {
            "customer": stripe_customer_id,
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": settings.STRIPE_SUCCESS_URL,
            "cancel_url": settings.STRIPE_CANCEL_URL,
            "locale": "pt-BR",
            "payment_method_types": ["card"],
            # Permite PIX como método de pagamento alternativo (Stripe Brazil)
            # Descomente quando PIX estiver habilitado na sua conta Stripe:
            # "payment_method_types": ["card", "pix"],
            "subscription_data": {
                "metadata": {"plano": plano},
            },
        }

        if dias_trial > 0:
            session_kwargs["subscription_data"]["trial_period_days"] = dias_trial

        try:
            session = self._stripe.checkout.Session.create(**session_kwargs)
            logger.info(
                "stripe.checkout_session_criada",
                session_id=session.id,
                customer_id=stripe_customer_id,
                plano=plano,
            )
            return str(session.url) if session.url is not None else None
        except Exception as exc:
            logger.error("stripe.checkout_session_erro", erro=str(exc))
            raise

    # ------------------------------------------------------------------
    # Billing Portal
    # ------------------------------------------------------------------

    def criar_portal_session(
        self, *, stripe_customer_id: str, return_url: str | None = None
    ) -> str | None:
        """
        Cria uma Billing Portal Session para auto-serviço do cliente.

        O Portal Stripe permite ao cliente:
          - Atualizar cartão de crédito
          - Fazer upgrade/downgrade de plano
          - Cancelar a assinatura
          - Ver histórico de faturas

        Returns:
            URL do portal ou None em modo degradado.
        """
        if not self._habilitado:
            return None
        try:
            session = self._stripe.billing_portal.Session.create(
                customer=stripe_customer_id,
                return_url=return_url or settings.STRIPE_SUCCESS_URL,
            )
            logger.info("stripe.portal_session_criada", customer_id=stripe_customer_id)
            return str(session.url) if session.url is not None else None
        except Exception as exc:
            logger.error("stripe.portal_session_erro", erro=str(exc))
            raise

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------

    def construir_evento(self, *, payload: bytes, sig_header: str) -> Any:
        """
        Valida a assinatura do webhook e retorna o objeto Event do Stripe.

        Lança stripe.error.SignatureVerificationError se a assinatura for inválida.
        Lança ValueError se STRIPE_WEBHOOK_SECRET não estiver configurado.
        """
        if not self._habilitado:
            raise ValueError("Stripe não está configurado (STRIPE_SECRET_KEY ausente).")

        if not settings.STRIPE_WEBHOOK_SECRET:
            raise ValueError(
                "STRIPE_WEBHOOK_SECRET não configurado. "
                "Defina no .env ou via variável de ambiente."
            )

        return self._stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.STRIPE_WEBHOOK_SECRET,
        )


# ---------------------------------------------------------------------------
# Singleton — instanciado uma vez ao importar o módulo
# ---------------------------------------------------------------------------

stripe_service = StripeService()
