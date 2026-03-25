"""
Testes unitários — EmpresaIntelligenceService (B2B)
=====================================================
Verifica que:
- Com Receita + LinkedIn: inteligência completa
- Sem CNPJ no nome: enriquecimento_parcial=True, sem erro
- Sócios armazenados sem CPF (LGPD)
- LinkedIn indisponível: contatos = [], linkedin_disponivel = False
- Cache Redis é utilizado quando disponível
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from feature_1_ia_personalizada.services.prospeccao.datajud_prospeccao import (
    LitiganteEncontrado,
)
from feature_1_ia_personalizada.services.prospeccao.empresa_intelligence import (
    EmpresaIntelligenceService,
    EmpresaInteligencia,
)
from feature_1_ia_personalizada.services.prospeccao.receita_federal_client import EmpresaDados
from feature_1_ia_personalizada.services.prospeccao.linkedin_client import ContatoLinkedIn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _litigante_pj(nome: str = "EMPRESA TESTE LTDA (11.222.333/0001-81)") -> LitiganteEncontrado:
    return LitiganteEncontrado(
        nome=nome,
        polo="passivo",
        tipo_acao="Reclamação Trabalhista",
        tribunal="TRT-2",
        fase_processual="Conhecimento",
        numero_cnj="0001234-56.2024.5.02.0100",
        processos_count=5,
        sem_advogado=False,
    )


def _empresa_dados() -> EmpresaDados:
    return EmpresaDados(
        cnpj="11222333000181",
        razao_social="EMPRESA TESTE LTDA",
        nome_fantasia="Empresa Teste",
        situacao="ATIVA",
        porte="MEDIA",
        cnae_codigo="6911-7/01",
        cnae_descricao="Atividades jurídicas, exceto cartórios",
        uf="SP",
        municipio="São Paulo",
        socios=[
            {"nome": "João Sócio", "cpf": "111.222.333-44", "qualificacao": "Administrador"},
            {"nome": "Maria Sócia", "cpf": "555.666.777-88", "qualificacao": "Sócio-Cotista"},
        ],
    )


def _make_receita_mock(dados: EmpresaDados | None) -> MagicMock:
    mock = MagicMock()
    mock.buscar_cnpj = AsyncMock(return_value=dados)
    return mock


def _make_linkedin_mock(
    contatos: list[ContatoLinkedIn] | None = None,
    disponivel: bool = True,
) -> MagicMock:
    mock = MagicMock()
    mock.disponivel = disponivel
    mock.buscar_funcionarios = AsyncMock(return_value=contatos or [])
    return mock


def _make_redis_mock(cached_data: str | None = None) -> MagicMock:
    mock = MagicMock()
    mock.get = AsyncMock(return_value=cached_data)
    mock.setex = AsyncMock(return_value=True)
    return mock


# ---------------------------------------------------------------------------
# Enriquecimento completo (Receita + LinkedIn)
# ---------------------------------------------------------------------------

class TestEnriquecimentoCompleto:
    @pytest.mark.asyncio
    async def test_enriquece_com_receita_e_linkedin(self):
        receita = _make_receita_mock(_empresa_dados())
        linkedin = _make_linkedin_mock([
            ContatoLinkedIn(nome="Ana Gerente", cargo="Gerente Jurídico", url_perfil=None, empresa="Empresa Teste"),
        ])
        svc = EmpresaIntelligenceService(receita=receita, linkedin=linkedin)

        intel = await svc.enriquecer(_litigante_pj())

        assert intel.razao_social == "EMPRESA TESTE LTDA"
        assert intel.cnpj is not None
        assert intel.situacao == "ATIVA"
        assert intel.porte == "MEDIA"
        assert len(intel.contatos_linkedin) == 1
        assert intel.linkedin_disponivel is True
        assert intel.enriquecimento_parcial is False

    @pytest.mark.asyncio
    async def test_socios_nao_tem_cpf(self):
        """Sócios armazenados apenas com nome e qualificação — LGPD."""
        receita = _make_receita_mock(_empresa_dados())
        linkedin = _make_linkedin_mock([])
        svc = EmpresaIntelligenceService(receita=receita, linkedin=linkedin)

        intel = await svc.enriquecer(_litigante_pj())

        for socio in intel.socios:
            assert "cpf" not in socio, "CPF não deve ser armazenado em sócios"
            assert "nome" in socio
            assert "qualificacao" in socio


# ---------------------------------------------------------------------------
# Sem CNPJ no nome
# ---------------------------------------------------------------------------

class TestSemCNPJ:
    @pytest.mark.asyncio
    async def test_sem_cnpj_enriquecimento_parcial(self):
        """Nome sem CNPJ → enriquecimento_parcial=True, sem erro."""
        receita = _make_receita_mock(None)  # nunca chamado na prática
        linkedin = _make_linkedin_mock([])
        svc = EmpresaIntelligenceService(receita=receita, linkedin=linkedin)

        litigante_sem_cnpj = _litigante_pj(nome="EMPRESA SEM CNPJ LTDA")
        intel = await svc.enriquecer(litigante_sem_cnpj)

        assert intel.enriquecimento_parcial is True
        assert intel.razao_social == "EMPRESA SEM CNPJ LTDA"
        assert intel.cnpj is None


# ---------------------------------------------------------------------------
# LinkedIn indisponível
# ---------------------------------------------------------------------------

class TestLinkedInIndisponivel:
    @pytest.mark.asyncio
    async def test_linkedin_indisponivel_contatos_vazio(self):
        receita = _make_receita_mock(_empresa_dados())
        linkedin = _make_linkedin_mock([], disponivel=False)
        svc = EmpresaIntelligenceService(receita=receita, linkedin=linkedin)

        intel = await svc.enriquecer(_litigante_pj())

        assert intel.contatos_linkedin == []
        assert intel.linkedin_disponivel is False


# ---------------------------------------------------------------------------
# Cache Redis
# ---------------------------------------------------------------------------

class TestCacheEmpresa:
    @pytest.mark.asyncio
    async def test_cache_hit_nao_chama_receita(self):
        """Se há cache Redis, Receita Federal não é consultada."""
        cached = EmpresaInteligencia(
            razao_social="EMPRESA CACHED",
            processos_count=3,
            cnpj="11222333000181",
            situacao="ATIVA",
            porte="MEDIA",
            setor_cnae="Comércio",
            socios=[],
            contatos_linkedin=[],
            linkedin_disponivel=False,
            enriquecimento_parcial=False,
        )
        payload = {
            "cnpj": cached.cnpj,
            "razao_social": cached.razao_social,
            "situacao": cached.situacao,
            "porte": cached.porte,
            "setor_cnae": cached.setor_cnae,
            "socios": cached.socios,
            "processos_count": cached.processos_count,
            "tipos_acao_envolvida": [],
            "contatos_linkedin": [],
            "linkedin_disponivel": False,
            "enriquecimento_parcial": False,
            "tribunal": "",
            "polo": "",
            "sem_advogado": False,
        }
        redis = _make_redis_mock(json.dumps(payload))
        receita = _make_receita_mock(_empresa_dados())
        linkedin = _make_linkedin_mock([])
        svc = EmpresaIntelligenceService(receita=receita, linkedin=linkedin, redis=redis)

        intel = await svc.enriquecer(_litigante_pj())

        assert intel.razao_social == "EMPRESA CACHED"
        receita.buscar_cnpj.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_falha_receita_retorna_parcial_sem_excecao(self):
        """Receita Federal falhando não deve levantar exceção."""
        receita = _make_receita_mock(None)  # retorna None = falha
        receita.buscar_cnpj = AsyncMock(side_effect=Exception("Timeout"))
        linkedin = _make_linkedin_mock([])
        svc = EmpresaIntelligenceService(receita=receita, linkedin=linkedin)

        intel = await svc.enriquecer(_litigante_pj())

        assert intel.enriquecimento_parcial is True
