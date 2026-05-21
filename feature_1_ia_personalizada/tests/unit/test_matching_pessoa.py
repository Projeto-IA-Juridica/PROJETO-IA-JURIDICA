"""
Testes unitários — MatchingService (B2C)
=========================================
Verifica que:
- Heurística pessoa aplica os componentes corretamente
- Score < 30 não chama Claude
- abordagem_sugerida B2C não menciona cold call nem dados pessoais
- tipo_lead == "pessoa" no resultado
- TypeError para tipo de inteligência inválido
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.prospeccao.dna_advogado import DNAEscritorio
from feature_1_ia_personalizada.services.prospeccao.matching import MatchingService
from feature_1_ia_personalizada.services.prospeccao.pessoa_intelligence import PessoaInteligencia

# ---------------------------------------------------------------------------
# Builders de fixture
# ---------------------------------------------------------------------------


def _dna_pessoa(
    especialidades: list[str] | None = None,
    top_tipos_acao: list[dict] | None = None,
) -> DNAEscritorio:
    return DNAEscritorio(
        escritorio_id=2,
        especialidades=especialidades or ["direito de família", "divórcio"],
        setores_alvo=["pessoas físicas em litígio"],
        tipo_lead_predominante="pessoa",
        perfil_cliente_ideal="Pessoas em processos de família",
        diferenciais=["Mediação"],
        top_tipos_acao=top_tipos_acao
        or [
            {"tipo": "Divórcio", "contagem": 40, "percentual": 40.0},
            {"tipo": "Alimentos", "contagem": 30, "percentual": 30.0},
            {"tipo": "Guarda", "contagem": 30, "percentual": 30.0},
        ],
        dados_insuficientes=False,
    )


def _pessoa(
    tipo_acao: str = "Ação de Divórcio",
    polo: str = "ativo",
    fase: str = "Conhecimento",
) -> PessoaInteligencia:
    return PessoaInteligencia(
        nome="Maria da Silva",
        polo=polo,
        tipo_acao=tipo_acao,
        tribunal="TJSP",
        fase_processual=fase,
        numero_cnj_exemplo="0001234-56.2024.8.26.0100",
    )


# ---------------------------------------------------------------------------
# Heurística por componente
# ---------------------------------------------------------------------------


class TestHeuristicaPessoa:
    def test_especialidade_match_pontua_35(self):
        dna = _dna_pessoa(especialidades=["divórcio"])
        pessoa = _pessoa(tipo_acao="Ação de Divórcio Consensual")
        svc = MatchingService(anthropic_api_key="sk-test")
        score, comp = svc._score_heuristico_pessoa(dna, pessoa)

        assert comp.get("especialidade_match") == 35

    def test_polo_ativo_compativel_pontua_25(self):
        dna = _dna_pessoa()
        pessoa = _pessoa(polo="ativo")
        svc = MatchingService(anthropic_api_key="sk-test")
        score, comp = svc._score_heuristico_pessoa(dna, pessoa)

        assert comp.get("polo_compativel") == 25

    def test_fase_inicial_pontua_20(self):
        dna = _dna_pessoa()
        pessoa = _pessoa(fase="Conhecimento")
        svc = MatchingService(anthropic_api_key="sk-test")
        _, comp = svc._score_heuristico_pessoa(dna, pessoa)

        assert comp.get("fase_inicial") == 20

    def test_fase_execucao_nao_pontua_fase_inicial(self):
        dna = _dna_pessoa()
        pessoa = _pessoa(fase="Execução")
        svc = MatchingService(anthropic_api_key="sk-test")
        _, comp = svc._score_heuristico_pessoa(dna, pessoa)

        assert "fase_inicial" not in comp

    def test_alta_recorrencia_pontua_20(self):
        """Tipo de ação com > 30% nos processos do escritório → alta_recorrencia."""
        dna = _dna_pessoa(
            top_tipos_acao=[
                {"tipo": "Divórcio", "contagem": 50, "percentual": 50.0},
            ]
        )
        pessoa = _pessoa(tipo_acao="Divórcio Litigioso")
        svc = MatchingService(anthropic_api_key="sk-test")
        _, comp = svc._score_heuristico_pessoa(dna, pessoa)

        assert comp.get("alta_recorrencia") == 20

    def test_tipo_acao_sem_recorrencia_nao_pontua(self):
        """Tipo de ação com percentual ≤ 30% não pontua alta_recorrencia."""
        dna = _dna_pessoa(
            top_tipos_acao=[
                {"tipo": "Divórcio", "contagem": 20, "percentual": 20.0},
            ]
        )
        pessoa = _pessoa(tipo_acao="Divórcio Consensual")
        svc = MatchingService(anthropic_api_key="sk-test")
        _, comp = svc._score_heuristico_pessoa(dna, pessoa)

        assert "alta_recorrencia" not in comp

    def test_score_maximo_capped_100(self):
        """Todos os componentes (35+25+20+20=100) → score = 100."""
        dna = _dna_pessoa(
            especialidades=["divórcio"],
            top_tipos_acao=[{"tipo": "Divórcio", "contagem": 60, "percentual": 60.0}],
        )
        pessoa = _pessoa(tipo_acao="Divórcio Consensual", polo="ativo", fase="Conhecimento")
        svc = MatchingService(anthropic_api_key="sk-test")
        score, comp = svc._score_heuristico_pessoa(dna, pessoa)

        assert score <= 100
        assert sum(comp.values()) == score


# ---------------------------------------------------------------------------
# Score abaixo do limiar: sem Claude
# ---------------------------------------------------------------------------


class TestB2CScoreAbaixoLimiar:
    @pytest.mark.asyncio
    async def test_score_zero_nao_chama_claude(self):
        """Sem match nenhum → score = 0, gerado_por_ia=False."""
        dna = _dna_pessoa(
            especialidades=["tributário"],
            top_tipos_acao=[{"tipo": "Execução Fiscal", "contagem": 100, "percentual": 100.0}],
        )
        pessoa = _pessoa(tipo_acao="Contrato de Locação", polo="passivo", fase="Execução")
        svc = MatchingService(anthropic_api_key="sk-test")

        resultado = await svc.calcular_score(dna, pessoa)

        assert resultado.gerado_por_ia is False
        assert resultado.tipo_lead == "pessoa"
        assert resultado.score < 30


# ---------------------------------------------------------------------------
# abordagem_sugerida B2C — restrições de compliance
# ---------------------------------------------------------------------------


class TestAbordagemB2C:
    @pytest.mark.asyncio
    async def test_abordagem_nao_menciona_cold_call(self):
        """Claude B2C não deve sugerir cold call nem 'vi que você tem um processo'."""
        dna = _dna_pessoa()
        pessoa = _pessoa(tipo_acao="Divórcio", polo="ativo", fase="Conhecimento")

        resposta_ia = json.dumps(
            {
                "score": 75,
                "motivo": "Pessoa em fase inicial de divórcio — especialidade do escritório.",
                "abordagem_sugerida": (
                    "Publicar no processo uma petição de apresentação profissional, "
                    "indicando experiência em mediação familiar."
                ),
            }
        )

        resposta_mock = MagicMock()
        resposta_mock.status_code = 200
        resposta_mock.json.return_value = {"content": [{"text": resposta_ia}]}
        resposta_mock.raise_for_status = MagicMock()

        http_mock = AsyncMock()
        http_mock.post = AsyncMock(return_value=resposta_mock)
        http_mock.__aenter__ = AsyncMock(return_value=http_mock)
        http_mock.__aexit__ = AsyncMock(return_value=None)

        svc = MatchingService(anthropic_api_key="sk-test")

        with patch(
            "feature_1_ia_personalizada.services.prospeccao.matching.httpx.AsyncClient",
            return_value=http_mock,
        ):
            resultado = await svc.calcular_score(dna, pessoa)

        abordagem = resultado.abordagem_sugerida.lower()
        # A abordagem sugerida não deve conter indicações de cold call
        cold_call_keywords = ["ligue", "telefone", "whatsapp", "email", "vi que você tem"]
        for keyword in cold_call_keywords:
            assert keyword not in abordagem, f"Abordagem B2C não deve mencionar '{keyword}'"

        assert resultado.tipo_lead == "pessoa"
        assert resultado.gerado_por_ia is True


# ---------------------------------------------------------------------------
# TypeError para tipo inválido
# ---------------------------------------------------------------------------


class TestTipoInvalido:
    @pytest.mark.asyncio
    async def test_tipo_invalido_levanta_type_error(self):
        dna = _dna_pessoa()
        svc = MatchingService(anthropic_api_key="sk-test")

        with pytest.raises(TypeError, match="Tipo de inteligência não suportado"):
            await svc.calcular_score(dna, "isso não é uma inteligência")
