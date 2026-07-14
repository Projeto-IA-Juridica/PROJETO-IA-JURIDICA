"""
Ponto ÚNICO de integração com o app principal.

Toda a "contaminação" da máquina de vendas no produto passa por aqui. O app.py
e o celery_app.py fazem apenas UMA chamada guardada cada, dentro de try/except:
se a feature estiver desligada (VENDAS_TENANT_ID ausente) ou se esta pasta for
removida, o produto boota e roda idêntico — nenhuma rota, task ou fluxo de
cliente é tocado.

Princípios do isolamento:
  - as rotas de vendas têm prefixo /vendas e guard de tenant (só o tenant de
    vendas acessa);
  - o webhook do vitrine é /vendas/webhook, separado do /webhook/whatsapp;
  - a conversa da Clara é handler próprio, não passa pelo orquestrador do cliente;
  - o painel é app frontend separado (feature_vendas/painel), fora do hub do cliente.
"""

from __future__ import annotations

import structlog

from feature_vendas import config as vconfig

logger = structlog.get_logger(__name__)


def habilitado() -> bool:
    """A feature só liga com o tenant de vendas configurado."""
    return vconfig.VENDAS_TENANT_ID is not None


def incluir_rotas(app) -> bool:  # noqa: ANN001 — FastAPI
    """
    Registra as rotas de vendas no app. Chamado por app.py atrás de guard.
    Retorna True se registrou. Nunca levanta para o app principal.
    """
    if not habilitado():
        logger.info("vendas_desabilitado_rotas_nao_registradas")
        return False
    try:
        from feature_vendas.api.routes.leads import router as leads_router
        from feature_vendas.api.routes.webhook_vitrine import router as vitrine_router

        app.include_router(leads_router)
        app.include_router(vitrine_router)
        logger.info("vendas_rotas_registradas")
        return True
    except Exception as exc:  # pragma: no cover — isolamento: nunca quebra o app
        logger.error("vendas_falha_registrar_rotas", erro=str(exc))
        return False


def beat_schedule_vendas() -> dict:
    """
    Schedules Celery Beat da máquina de vendas. Vazio se a feature está off.
    O celery_app.py faz {**base, **beat_schedule_vendas()}.
    """
    if not habilitado():
        return {}
    from celery.schedules import crontab

    return {
        "vendas-enriquecer-alvos": {
            "task": "vendas.enriquecer_alvos",
            "schedule": crontab(minute="*/10"),
        },
        "vendas-disparar-frios": {
            "task": "vendas.disparar_frios",
            "schedule": crontab(minute="*/5"),
        },
        "vendas-avancar-cadencia": {
            "task": "vendas.avancar_cadencia",
            "schedule": crontab(minute="*/30"),
        },
    }
