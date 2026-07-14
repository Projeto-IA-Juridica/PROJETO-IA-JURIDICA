"""
Testes do funil: filtragem, enriquecimento, validação, lead scoring, handoff.
Valida que o código segue o script do playbook.
"""

from __future__ import annotations

import pytest

from feature_vendas.services.enriquecimento import Enriquecedor, _primeiro_nome
from feature_vendas.services.filtragem import pontuar
from feature_vendas.services.handoff import Socio, escolher_socio, montar_briefing
from feature_vendas.services.lead_scoring import Qualificacao, avaliar_lead
from feature_vendas.services.validacao import validar_espelho

# ---------------------------------------------------------------------------
# Filtragem ICP (etapa 2)
# ---------------------------------------------------------------------------


def test_escritorio_ideal_e_classe_a():
    r = pontuar(num_advogados=8, area="trabalhista", tem_vaga_aberta=True, whatsapp_publicado=True)
    assert r.classe == "A" and not r.desqualificado


def test_solo_sem_carteira_desqualificado():
    r = pontuar(num_advogados=0, area="cível")
    assert r.desqualificado


def test_area_massificada_desqualificada():
    r = pontuar(num_advogados=10, area="telefonia massa")
    assert r.desqualificado


# ---------------------------------------------------------------------------
# Enriquecimento (etapa 2/3)
# ---------------------------------------------------------------------------


class _LeitorOk:
    async def movimentacao_recente(self, cnj):  # noqa: ANN001
        return "Intimação da parte contrária para contestação no prazo de 15 dias"


class _LeitorVazio:
    async def movimentacao_recente(self, cnj):  # noqa: ANN001
        return None


@pytest.mark.asyncio
async def test_cnj_na_planilha_gera_template_a():
    enr = Enriquecedor("https://wa.me/55", leitor=_LeitorOk())
    msg = await enr.enriquecer("Dr. Marcos", processo_cnj="0012345-67.2024.5.02.0001")
    assert msg.template == "A"
    assert "0012345-67.2024.5.02.0001" in msg.texto
    assert "Gabriel" in msg.texto  # assinatura humana


@pytest.mark.asyncio
async def test_datajud_vazio_cai_para_template_b():
    """Cobertura de tribunal falha → não manda espelho errado, usa genérico."""
    enr = Enriquecedor("https://wa.me/55", leitor=_LeitorVazio())
    msg = await enr.enriquecer("Dra. Ana", processo_cnj="0012345-67.2024.5.02.0001")
    assert msg.template == "B"


@pytest.mark.asyncio
async def test_sem_cnj_usa_template_b():
    enr = Enriquecedor("https://wa.me/55", leitor=_LeitorOk())
    msg = await enr.enriquecer("Dr. João")
    assert msg.template == "B"


def test_titulo_removido_do_primeiro_nome():
    assert _primeiro_nome("Dr. Marcos Almeida") == "Marcos"
    assert _primeiro_nome("Dra. Ana") == "Ana"
    assert _primeiro_nome("Marcos") == "Marcos"


# ---------------------------------------------------------------------------
# Validação (etapa 3) — a rede anti-vexame
# ---------------------------------------------------------------------------


def test_espelho_valido_vai_para_envio():
    r = validar_espelho(
        template="A",
        processo_cnj="0012345-67.2024.5.02.0001",
        movimentacao_bruta="Sentença de procedência publicada no diário",
        mensagem="... 0012345-67.2024.5.02.0001 ...",
    )
    assert r.fila == "fila_envio"


def test_materia_sensivel_nunca_dispara():
    r = validar_espelho(
        template="A",
        processo_cnj="0012345-67.2024.8.26.0100",
        movimentacao_bruta="Pedido de curatela e interdição do requerido",
        mensagem="0012345-67.2024.8.26.0100",
    )
    assert r.fila == "fila_excecao"


def test_cnj_ausente_na_mensagem_vira_excecao():
    r = validar_espelho(
        template="A",
        processo_cnj="0012345-67.2024.5.02.0001",
        movimentacao_bruta="Despacho ordinário publicado no diário oficial",
        mensagem="mensagem sem o número citado",
    )
    assert r.fila == "fila_excecao"


# ---------------------------------------------------------------------------
# Lead scoring + handoff (etapa 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "msg,gatilho",
    [
        ("quanto custa?", "pediu_preco"),
        ("como faço pra testar?", "pediu_trial"),
        ("pode me ligar?", "pediu_reuniao"),
        ("quero uma proposta", "pediu_proposta"),
    ],
)
def test_sinais_explicitos_esquentam(msg, gatilho):
    r = avaliar_lead(ultima_mensagem=msg, total_interacoes=1, qualificacao=Qualificacao())
    assert r.quente and r.gatilho == gatilho


def test_conversa_morna_nao_esquenta():
    r = avaliar_lead(
        ultima_mensagem="interessante", total_interacoes=1, qualificacao=Qualificacao()
    )
    assert not r.quente


def test_escritorio_grande_engajado_esquenta():
    r = avaliar_lead(
        ultima_mensagem="somos 8 aqui",
        total_interacoes=4,
        qualificacao=Qualificacao(num_advogados=8, area="cível", quem_responde="secretaria"),
    )
    assert r.quente


def test_escritorio_grande_mas_sem_engajamento_ainda_nao():
    """5+ advogados mas só 1 troca: cedo demais para o sócio gastar tempo."""
    r = avaliar_lead(
        ultima_mensagem="oi",
        total_interacoes=1,
        qualificacao=Qualificacao(num_advogados=8),
    )
    assert not r.quente


def test_indicacao_vai_para_gabriel():
    socios = [Socio("Gabriel", "551", 1), Socio("Sócia", "552", 2)]
    assert escolher_socio(socios, "indicacao", 99).nome == "Gabriel"


def test_briefing_tem_o_essencial():
    b = montar_briefing(
        nome_escritorio="Almeida & Rocha",
        nome_contato="Dr. Marcos",
        cidade="Uberlândia",
        gatilho="pediu_preco",
        qualificacao=Qualificacao(num_advogados=8, area="trabalhista", quem_responde="secretaria"),
        trilhas_testadas=["processo real"],
    )
    assert "Almeida & Rocha" in b
    assert "preço" in b.lower()
    assert "8 advogado" in b
