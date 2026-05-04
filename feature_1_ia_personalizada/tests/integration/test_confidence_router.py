# feature_1_ia_personalizada/tests/integration/test_confidence_router.py
"""
Testes de integração do ConfidenceRouter.

O router é stateless (sem I/O, sem DB) — os testes validam o comportamento
funcional completo: score calculado, forçamentos, roteamento por threshold
e controle por feature flag de escritório.

Escritório é mockado com MagicMock (duck typing) para evitar dependência
de banco nos testes do router.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from feature_1_ia_personalizada.services.ai.confidence_router import (
    ConfidenceRouter,
    ConfidenceScore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _escritorio(
    escalacao_habilitada: bool = True,
    threshold: float = 0.70,
    tokens_usados: int = 0,
    quota: int = 500_000,
) -> MagicMock:
    e = MagicMock()
    e.id = 1
    e.escalacao_habilitada = escalacao_habilitada
    e.escalacao_confidence_threshold = threshold
    e.escalacao_tokens_usados_mes = tokens_usados
    e.escalacao_quota_tokens_mes = quota
    return e


def _avaliar(
    router: ConfidenceRouter,
    mensagem: str = "Olá",
    tipo_intencao: str = "status",
    rag_docs: list | None = None,
    fact_check_result: dict | None = None,
    historico: list | None = None,
    tentativas: int = 0,
) -> ConfidenceScore:
    return router.avaliar(
        mensagem=mensagem,
        resposta_claude="Resposta do Claude.",
        tipo_intencao=tipo_intencao,
        rag_docs=rag_docs or [],
        fact_check_result=fact_check_result or {},
        historico_cliente=historico or [],
        tentativas_geracao=tentativas,
        escritorio_id=1,
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def router() -> ConfidenceRouter:
    return ConfidenceRouter()


# ---------------------------------------------------------------------------
# Cenários de roteamento por score
# ---------------------------------------------------------------------------


class TestRoteamentoPorScore:
    def test_status_gera_score_alto_e_roteia_claude(self, router: ConfidenceRouter):
        """Intenção de status tem score base 0.95 — Claude responde sem escalar."""
        score = _avaliar(
            router,
            tipo_intencao="status",
            rag_docs=[{"score": 0.90}],
            fact_check_result={"hallucination_score": 0.0},
            historico=[{"satisfacao": 5}] * 10,
        )

        assert score.valor >= 0.90
        destino = router.rotear(score, _escritorio())
        assert destino == "claude"

    def test_perspectiva_caso_gera_score_baixo_e_roteia_escalacao(self, router: ConfidenceRouter):
        """Perspectiva de caso tem score base 0.30 — deve cair abaixo do threshold."""
        score = _avaliar(
            router,
            tipo_intencao="perspectiva_caso",
            rag_docs=[],                               # sem docs RAG → rag = 0.0
            fact_check_result={"hallucination_score": 0.2},
            historico=[],
        )

        assert score.valor < 0.70
        destino = router.rotear(score, _escritorio())
        assert destino == "escalacao"

    def test_score_acima_threshold_customizado_roteia_claude(self, router: ConfidenceRouter):
        """Escritório com threshold reduzido a 0.40 — score médio já satisfaz."""
        score = _avaliar(
            router,
            tipo_intencao="duvida_termo",              # score base 0.70
            rag_docs=[{"score": 0.75}],
            fact_check_result={"hallucination_score": 0.05},
        )

        destino = router.rotear(score, _escritorio(threshold=0.40))
        assert destino == "claude"

    def test_score_abaixo_threshold_customizado_roteia_escalacao(self, router: ConfidenceRouter):
        """Escritório exigente (threshold=0.85) — score normal não passa."""
        score = _avaliar(
            router,
            tipo_intencao="outro",                     # score base 0.65
            rag_docs=[{"score": 0.60}],
            fact_check_result={"hallucination_score": 0.1},
        )

        destino = router.rotear(score, _escritorio(threshold=0.85))
        assert destino == "escalacao"


# ---------------------------------------------------------------------------
# Forçamentos (override do score)
# ---------------------------------------------------------------------------


class TestForcamentosEscalacao:
    def test_mensagem_com_stj_forca_escalacao(self, router: ConfidenceRouter):
        """Referência ao STJ força escalação independente do score de status."""
        score = _avaliar(
            router,
            mensagem="O STJ tem alguma súmula sobre isso?",
            tipo_intencao="status",                    # seria claude pelo score
            rag_docs=[{"score": 0.95}],
            fact_check_result={"hallucination_score": 0.0},
        )

        assert score.deve_escalar is True
        assert "STJ" in score.motivo
        assert router.rotear(score, _escritorio()) == "escalacao"

    def test_mensagem_com_cpc_art_forca_escalacao(self, router: ConfidenceRouter):
        score = _avaliar(
            router,
            mensagem="Quais os efeitos do CPC art. 485?",
            tipo_intencao="duvida_termo",
        )

        assert score.deve_escalar is True
        assert "CPC" in score.motivo

    def test_mensagem_com_sumula_forca_escalacao(self, router: ConfidenceRouter):
        score = _avaliar(
            router,
            mensagem="A Súmula 331 do TST se aplica aqui?",
            tipo_intencao="duvida_termo",
        )

        assert score.deve_escalar is True

    def test_hallucination_score_alto_forca_escalacao(self, router: ConfidenceRouter):
        """hallucination_score > 0.30 força escalação independente da intenção."""
        score = _avaliar(
            router,
            tipo_intencao="status",                    # normalmente seria claude
            fact_check_result={"hallucination_score": 0.40},
        )

        assert score.deve_escalar is True
        assert "hallucination" in score.motivo
        assert router.rotear(score, _escritorio()) == "escalacao"

    def test_hallucination_no_limite_nao_forca(self, router: ConfidenceRouter):
        """hallucination_score == 0.30 está no limite — não força (apenas > 0.30 força)."""
        score = _avaliar(
            router,
            tipo_intencao="status",
            rag_docs=[{"score": 0.95}],
            fact_check_result={"hallucination_score": 0.30},
        )

        assert score.deve_escalar is False

    def test_multiplas_tentativas_forcam_escalacao(self, router: ConfidenceRouter):
        """Mais de 1 tentativa de geração indica instabilidade — escala Opus."""
        score = _avaliar(
            router,
            tipo_intencao="status",
            tentativas=2,
        )

        assert score.deve_escalar is True
        assert "multiplas_tentativas" in score.motivo

    def test_uma_tentativa_nao_forca(self, router: ConfidenceRouter):
        """1 tentativa é o fluxo normal — não força."""
        score = _avaliar(
            router,
            tipo_intencao="status",
            rag_docs=[{"score": 0.90}],
            fact_check_result={"hallucination_score": 0.0},
            tentativas=1,
        )

        assert score.deve_escalar is False

    def test_intencao_juridica_complexa_forca_escalacao(self, router: ConfidenceRouter):
        score = _avaliar(router, tipo_intencao="juridica_complexa")

        assert score.deve_escalar is True
        assert score.valor == 0.0
        assert router.rotear(score, _escritorio()) == "escalacao"


# ---------------------------------------------------------------------------
# Controle por feature flag e quota
# ---------------------------------------------------------------------------


class TestControleEscritorioEscalacao:
    def test_escalacao_desabilitada_sempre_retorna_claude(self, router: ConfidenceRouter):
        """Com escalacao_habilitada=False, score e forçamentos são ignorados."""
        # Forçamento ativo (STJ na mensagem) mas Escalação desabilitada
        score = _avaliar(
            router,
            mensagem="O STJ decidiu sobre isso?",
            tipo_intencao="status",
        )
        assert score.deve_escalar is True  # forçamento ativado

        destino = router.rotear(score, _escritorio(escalacao_habilitada=False))
        assert destino == "claude"

    def test_escalacao_desabilitada_ignora_score_baixo(self, router: ConfidenceRouter):
        """Score baixo sem escalação habilitada → Claude."""
        score = _avaliar(router, tipo_intencao="perspectiva_caso", rag_docs=[])

        destino = router.rotear(score, _escritorio(escalacao_habilitada=False))
        assert destino == "claude"

    def test_quota_esgotada_retorna_claude(self, router: ConfidenceRouter):
        """Quota mensal atingida → forçar Claude independente de score."""
        score = _avaliar(
            router,
            mensagem="O STJ decidiu sobre isso?",   # forçamento ativo
            tipo_intencao="juridica_complexa",
        )

        # usados == quota → esgotada
        destino = router.rotear(
            score,
            _escritorio(tokens_usados=500_000, quota=500_000),
        )
        assert destino == "claude"

    def test_quota_nao_esgotada_permite_escalacao(self, router: ConfidenceRouter):
        score = _avaliar(router, tipo_intencao="juridica_complexa")

        destino = router.rotear(
            score,
            _escritorio(tokens_usados=499_999, quota=500_000),
        )
        assert destino == "escalacao"


# ---------------------------------------------------------------------------
# Breakdown de componentes do score
# ---------------------------------------------------------------------------


class TestComponentesScore:
    def test_sem_rag_docs_component_rag_zero(self, router: ConfidenceRouter):
        score = _avaliar(router, tipo_intencao="status", rag_docs=[])
        assert score.componentes["rag"] == 0.0

    def test_rag_docs_sem_campo_score_usa_parcial(self, router: ConfidenceRouter):
        """Docs sem campo 'score' → cobertura parcial assumida (0.5)."""
        score = _avaliar(
            router,
            tipo_intencao="status",
            rag_docs=[{"conteudo": "texto"}],           # sem campo 'score'
        )
        assert score.componentes["rag"] == 0.5

    def test_sem_fact_check_usa_score_neutro(self, router: ConfidenceRouter):
        score = _avaliar(router, tipo_intencao="status", fact_check_result={})
        assert score.componentes["fact"] == 0.5

    def test_sem_historico_nps_usa_score_neutro(self, router: ConfidenceRouter):
        score = _avaliar(router, tipo_intencao="status", historico=[])
        assert score.componentes["historico"] == 0.5

    def test_historico_100_pct_satisfeito(self, router: ConfidenceRouter):
        historico = [{"satisfacao": 5}] * 10
        score = _avaliar(router, tipo_intencao="status", historico=historico)
        assert score.componentes["historico"] == 1.0

    def test_historico_sem_nenhum_nps(self, router: ConfidenceRouter):
        """Interações sem campo satisfacao → score neutro 0.5."""
        historico = [{"mensagem": "texto"}] * 5
        score = _avaliar(router, tipo_intencao="status", historico=historico)
        assert score.componentes["historico"] == 0.5

    def test_score_clampado_entre_0_e_1(self, router: ConfidenceRouter):
        """Score nunca deve ultrapassar 1.0 ou ficar abaixo de 0.0."""
        score = _avaliar(
            router,
            tipo_intencao="status",
            rag_docs=[{"score": 1.0}],
            fact_check_result={"hallucination_score": 0.0},
            historico=[{"satisfacao": 5}] * 20,
        )
        assert 0.0 <= score.valor <= 1.0
