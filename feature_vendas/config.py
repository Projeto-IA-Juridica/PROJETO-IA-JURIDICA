"""
Config da máquina de vendas — env próprio, isolado do produto.

feature_vendas nunca modifica o settings do produto; lê o que precisa daqui.
Todas opcionais: sem as chaves, a máquina de disparo fica desligada de forma
limpa (o vitrine/Clara continua funcionando com a infra normal).

  VENDAS_TENANT_ID            escritório interno que hospeda a pipeline e a Clara
  VENDAS_VITRINE_URL          link wa.me do número-vitrine (CTA dos templates)
  VENDAS_EVOLUTION_INSTANCE   instância Evolution do CHIP DE DISPARO (separada!)
  VENDAS_EVOLUTION_API_KEY    api key dessa instância
  VENDAS_CHIP_INICIADO_EM     YYYY-MM-DD do 1º disparo do chip (para o warm-up)
"""

from __future__ import annotations

import os
from datetime import date


def _env(nome: str) -> str | None:
    v = os.getenv(nome)
    return v.strip() if v else None


_tenant_raw = _env("VENDAS_TENANT_ID")
VENDAS_TENANT_ID: int | None = int(_tenant_raw) if _tenant_raw else None
VENDAS_VITRINE_URL: str = _env("VENDAS_VITRINE_URL") or "https://wa.me/55XXXXXXXXXXX"
VENDAS_EVOLUTION_INSTANCE: str | None = _env("VENDAS_EVOLUTION_INSTANCE")
VENDAS_EVOLUTION_API_KEY: str | None = _env("VENDAS_EVOLUTION_API_KEY")


def instancia_disparo() -> str:
    """Instância Evolution do chip de disparo/vitrine. Assume feature habilitada."""
    assert VENDAS_EVOLUTION_INSTANCE is not None, "VENDAS_EVOLUTION_INSTANCE não configurada"
    return VENDAS_EVOLUTION_INSTANCE


def tenant_id() -> int:
    """Id do tenant de vendas. Assume feature habilitada (checar habilitado() antes)."""
    assert VENDAS_TENANT_ID is not None, "VENDAS_TENANT_ID não configurado"
    return VENDAS_TENANT_ID


def chip_iniciado_em() -> date:
    """Data do 1º disparo do chip. Default = hoje (warm-up começa do zero)."""
    raw = _env("VENDAS_CHIP_INICIADO_EM")
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return date.today()


def disparo_habilitado() -> bool:
    return bool(VENDAS_EVOLUTION_INSTANCE and VENDAS_EVOLUTION_API_KEY and VENDAS_TENANT_ID)
