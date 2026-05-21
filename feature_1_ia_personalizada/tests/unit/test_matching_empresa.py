"""
Testes unitários — MatchingService (B2B)
=========================================
Verifica que:
- Heurística empresa aplica os componentes corretamente
- Score < 30 não chama Claude (gerado_por_ia=False)
- Score ≥ 30 chama Claude e retorna resultado refinado
- Falha na API Claude retorna score heurístico sem quebrar
- tipo_lead == "empresa" no resultado
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.prospeccao.dna_advogado import DNAEscritorio
from feature_1_ia_personalizada.services.prospeccao.empresa_intelligence import EmpresaInteligencia
from feature_1_ia_personalizada.services.prospeccao.matching import MatchingService

# ---------------------------------------------------------------------------
# Builders de fixture
# ---------------------------------------------------------------------------

def _dna_empresa(
    especialidades: list[str] | None = None,
    setores_alvo: list[str] | None = None,
) -> DNAEscritorio:
    return DNAEscritorio(
        escritorio_id=1,
        especialidades=especialidades or ["direito trabalhista"],
        setores_alvo=setores_alvo or ["indústria", "comércio"],
        tipo_lead_predominante="empresa",
        perfil_cliente_ideal="Empresas com alto volume de processos",
        diferenciais=["Agilidade"],
        top_tipos_acao=[
            {"tipo": "Reclamação Trabalhista", "contagem": 80, "percentual": 80.0},
            {"tipo": "Contrato", "contagem": 20, "percentual": 20.0},
        ],
        dados_insuficientes=False,
    )


def _empresa(
    tipos_acao: list[str] | None = None,
    setor: str = "indústria",
    porte: str = "MEDIA",
    situacao: str = "ATIVA",
    processos: int = 5,
    linkedin_contatos: int = 2,
) -> EmpresaInteligencia:
    contatos = [
        {"nome": "Ana Gerente", "cargo": "Gerente Jurídico", "url_perfil": ""}
    ] * linkedin_contatos
    return EmpresaInteligencia(
        razao_social="Empresa Teste LTDA",
        processos_count=processos,
        tipos_acao_envolvida=tipos_acao or ["reclamação trabalhista"],
        cnpj="11.222.333/0001-81",
        situacao=situacao,
        porte=porte,
        setor_cnae=setor,
        socios=[{"nome": "João Sócio", "qualificacao": "Administrador"}],
        contatos_linkedin=contatos,
        linkedin_disponivel=True,
        enriquecimento_parcial=False,
    )


# ---------------------------------------------------------------------------
# Heurística por componente
# ---------------------------------------------------------------------------

class TestHeuristicaEmpresa:
    def test_score_maximo_todos_componentes(self):
        """Todos os componentes positivos → score = 100 (capped)."""
        # A heurística faz: especialidades_lower & tipos_empresa_lower
        # Portanto os valores devem ser idênticos (case-insensitive)
        dna = _dna_empresa(especialidades=["reclamação trabalhista"], setores_alvo=["indústria"])
        empresa = _empresa(
            tipos_acao=["reclamação trabalhista"],
            setor="indústria",
            porte="GRANDE",
            situacao="ATIVA",
            processos=5,
            linkedin_contatos=3,
        )
        svc = MatchingService(anthropic_api_key="sk-test")
        score, comp = svc._score_heuristico_empresa(dna, empresa)

        assert comp.get("especialidade_match") == 30
        assert comp.get("setor_alvo") == 20
        assert comp.get("demanda_ativa") == 15
        assert comp.get("linkedin_contatos") == 15
        assert comp.get("porte_relevante") == 10
        assert comp.get("situacao_ativa") == 10
        assert score == 100  # sum=100, capped at 100

    def test_sem_match_especialidade_nao_pontua(self):
        # Tipos completamente diferentes — sem interseção
        dna = _dna_empresa(especialidades=["tributário"], setores_alvo=["tecnologia"])
        empresa = _empresa(tipos_acao=["contrato de locação"], setor="agronegócio")
        svc = MatchingService(anthropic_api_key="sk-test")
        score, comp = svc._score_heuristico_empresa(dna, empresa)

        assert "especialidade_match" not in comp

    def test_menos_de_3_processos_nao_pontua_demanda(self):
        dna = _dna_empresa()
        empresa = _empresa(processos=2)
        svc = MatchingService(anthropic_api_key="sk-test")
        _, comp = svc._score_heuristico_empresa(dna, empresa)

        assert "demanda_ativa" not in comp

    def test_empresa_baixada_nao_pontua_situacao(self):
        dna = _dna_empresa()
        empresa = _empresa(situacao="BAIXADA")
        svc = MatchingService(anthropic_api_key="sk-test")
        _, comp = svc._score_heuristico_empresa(dna, empresa)

        assert "situacao_ativa" not in comp

    def test_empresa_mei_nao_pontua_porte(self):
        dna = _dna_empresa()
        empresa = _empresa(porte="MEI")
        svc = MatchingService(anthropic_api_key="sk-test")
        _, comp = svc._score_heuristico_empresa(dna, empresa)

        assert "porte_relevante" not in comp

    def test_sem_linkedin_nao_pontua_contatos(self):
        dna = _dna_empresa()
        empresa = _empresa(linkedin_contatos=0)
        svc = MatchingService(anthropic_api_key="sk-test")
        _, comp = svc._score_heuristico_empresa(dna, empresa)

        assert "linkedin_contatos" not in comp


# ---------------------------------------------------------------------------
# Score abaixo do limiar: sem Claude
# ---------------------------------------------------------------------------

class TestScoreAbaixoLimiar:
    @pytest.mark.asyncio
    async def test_score_29_nao_chama_claude(self):
        """Score heurístico 0: gerado_por_ia=False, Claude não é chamado."""
        dna = _dna_empresa(especialidades=["tributário"], setores_alvo=["finanças"])
        # Empresa sem match algum → score = 0
        empresa = _empresa(
            tipos_acao=["locação de imóvel"],
            setor="agronegócio",
            porte="MEI",
            situacao="BAIXADA",
            processos=1,
            linkedin_contatos=0,
        )
        svc = MatchingService(anthropic_api_key="sk-test")

        resultado = await svc.calcular_score(dna, empresa)

        assert resultado.gerado_por_ia is False
        assert resultado.tipo_lead == "empresa"
        assert resultado.score < 30


# ---------------------------------------------------------------------------
# Score acima do limiar: chama Claude
# ---------------------------------------------------------------------------

class TestScoreAcimaLimiar:
    @pytest.mark.asyncio
    async def test_score_alto_chama_claude_e_retorna_resultado_ia(self):
        """Score ≥ 30: Claude é chamado e resultado usa dados da IA."""
        dna = _dna_empresa()
        empresa = _empresa(
            tipos_acao=["reclamação trabalhista"],
            setor="indústria",
            porte="GRANDE",
            situacao="ATIVA",
            processos=5,
            linkedin_contatos=2,
        )

        resposta_ia = json.dumps({
            "score": 88,
            "motivo": "Empresa com alta demanda trabalhista no setor-alvo.",
            "abordagem_sugerida": "Contatar o diretor jurídico via LinkedIn.",
        })

        resposta_mock = MagicMock()
        resposta_mock.status_code = 200
        resposta_mock.json.return_value = {
            "content": [{"text": resposta_ia}]
        }
        resposta_mock.raise_for_status = MagicMock()

        http_mock = AsyncMock()
        http_mock.post = AsyncMock(return_value=resposta_mock)
        http_mock.__aenter__ = AsyncMock(return_value=http_mock)
        http_mock.__aexit__ = AsyncMock(return_value=None)

        svc = MatchingService(anthropic_api_key="sk-test")

        with patch("feature_1_ia_personalizada.services.prospeccao.matching.httpx.AsyncClient", return_value=http_mock):
            resultado = await svc.calcular_score(dna, empresa)

        assert resultado.gerado_por_ia is True
        assert resultado.score == 88
        assert resultado.tipo_lead == "empresa"
        assert "trabalhista" in resultado.motivo.lower()

    @pytest.mark.asyncio
    async def test_falha_api_claude_retorna_score_heuristico(self):
        """Falha no Claude: retorna score heurístico com gerado_por_ia=False."""
        dna = _dna_empresa()
        empresa = _empresa(processos=5, linkedin_contatos=2, situacao="ATIVA", porte="GRANDE")

        http_mock = AsyncMock()
        http_mock.post = AsyncMock(side_effect=Exception("Timeout"))
        http_mock.__aenter__ = AsyncMock(return_value=http_mock)
        http_mock.__aexit__ = AsyncMock(return_value=None)

        svc = MatchingService(anthropic_api_key="sk-test")

        with patch("feature_1_ia_personalizada.services.prospeccao.matching.httpx.AsyncClient", return_value=http_mock):
            resultado = await svc.calcular_score(dna, empresa)

        assert resultado.gerado_por_ia is False
        assert resultado.score > 0  # score heurístico calculado
