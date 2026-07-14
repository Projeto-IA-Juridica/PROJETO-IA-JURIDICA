"""
Testes do contexto do lead: a Clara sabe de onde a pessoa veio e o que já viu.
"""

from __future__ import annotations

import pytest

from feature_vendas.services.contexto_lead import detectar_origem, montar_contexto


@pytest.mark.parametrize(
    "msg,esperado",
    [
        ("Olá Clara, recebi seu currículo", "curriculo"),
        ("recebi o curriculum de vocês", "curriculo"),
        ("vi a vaga e quero conversar", "curriculo"),
        ("Olá Clara, fiz a conta do meu escritório", "calculadora"),
        ("o contador me indicou", "indicacao"),
        ("Olá Clara, vim pelo site", "landing"),
        ("oi, tudo bem?", None),
    ],
)
def test_detecta_origem_pela_primeira_mensagem(msg, esperado):
    assert detectar_origem(msg) == esperado


def test_espelho_instrui_a_nao_repetir_demo():
    ctx = montar_contexto(
        origem="planilha",
        template_usado="A",
        processo_cnj="0012345-67.2024.5.02.0001",
        nome_escritorio="Almeida & Rocha",
    )
    assert "JÁ viu a demonstração" in ctx
    assert "0012345-67.2024.5.02.0001" in ctx
    assert "Almeida & Rocha" in ctx


def test_curriculo_entra_na_brincadeira():
    ctx = montar_contexto(origem="curriculo", nome_escritorio="(inbound — vitrine)")
    assert "entrevista" in ctx.lower()
    # nome placeholder de inbound não deve aparecer como "quem é"
    assert "(inbound" not in ctx


def test_template_b_trata_como_frio_generico():
    ctx = montar_contexto(origem="planilha", template_usado="B")
    assert "ainda não viu nada" in ctx


def test_contexto_sempre_proibe_recitar():
    for origem in ("inbound", "curriculo", "landing", "indicacao", "calculadora"):
        ctx = montar_contexto(origem=origem)
        assert "nunca recite" in ctx.lower() or "Nunca diga" in ctx
