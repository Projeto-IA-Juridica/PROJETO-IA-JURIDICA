"""
Segurança do webhook e das rotas internas de vendas.

Estes testes existem porque a simulação em nível de serviço NÃO pega o stack de
middleware: um webhook barrado pelo JWT/CSRF do produto passaria despercebido
até a Clara ficar muda em produção.
"""

from __future__ import annotations

from feature_1_ia_personalizada.api.middleware.auth import (
    ROTAS_PUBLICAS,
    ROTAS_PUBLICAS_EXATAS,
)
from feature_1_ia_personalizada.api.middleware.csrf import _rota_isenta

_WEBHOOK = "/vendas/webhook"


def test_webhook_do_vitrine_passa_pelo_jwt():
    """
    Sem isenção, a Evolution levaria 401 antes de chegar na validação de apikey
    e a Clara nunca receberia mensagem nenhuma.
    """
    assert _WEBHOOK in ROTAS_PUBLICAS_EXATAS


def test_webhook_do_vitrine_e_isento_de_csrf():
    """POST de terceiro não carrega cookie de browser."""
    assert _rota_isenta(_WEBHOOK)


def test_rotas_internas_de_vendas_NAO_sao_publicas():
    """
    O painel (leads, funil, exceção, quentes) é interno: só a rota de webhook
    pode ser pública. Se alguém adicionar '/vendas' como prefixo público, isto
    quebra — que é o objetivo.
    """
    internas = [
        "/vendas/leads/funil",
        "/vendas/leads/quentes",
        "/vendas/leads/excecao",
        "/vendas/leads/importar",
    ]
    for rota in internas:
        assert rota not in ROTAS_PUBLICAS_EXATAS
        assert not any(
            rota.startswith(p) for p in ROTAS_PUBLICAS
        ), f"{rota} ficou pública — dados de vendas expostos sem JWT"


def test_isencao_de_csrf_nao_vazou_para_as_rotas_internas():
    assert not _rota_isenta("/vendas/leads/importar")
    assert not _rota_isenta("/vendas/leads/quentes")
