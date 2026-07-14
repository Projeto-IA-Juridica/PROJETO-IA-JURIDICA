"""
Opt-out: quem pede para parar, para. Para sempre.

O prompt da Clara PROMETE parar. Estes testes garantem que o sistema CUMPRE —
a promessa sem o código é o comportamento de um spammer educado.
"""

from __future__ import annotations

import pytest

from feature_vendas.services.opt_out import pediu_para_parar


@pytest.mark.parametrize(
    "texto",
    [
        "não me mande mais mensagens",
        "pare de me mandar isso",
        "não tenho interesse",
        "não quero receber nada",
        "me tire dessa lista",
        "quero sair da lista",
        "remover meu contato",
        "descadastrar",
        "isso é spam",
        "vou denunciar vocês",
        "me deixe em paz",
        "para de me perturbar",
    ],
)
def test_reconhece_pedido_de_parar(texto):
    assert pediu_para_parar(texto), f"não reconheceu opt-out: {texto!r}"


@pytest.mark.parametrize(
    "texto",
    [
        "não quero agendar hoje, pode ser semana que vem?",
        "quanto custa?",
        "interessante, me conta mais",
        "não entendi, pode explicar?",
        "agora não posso falar",
    ],
)
def test_nao_confunde_conversa_normal_com_opt_out(texto):
    """
    Falso positivo custa um lead morno. 'não quero agendar hoje' NÃO é opt-out —
    matar essa conversa seria perder venda por excesso de zelo.
    """
    assert not pediu_para_parar(texto), f"falso positivo de opt-out: {texto!r}"
