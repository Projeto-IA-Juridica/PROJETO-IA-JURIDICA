# feature_1_ia_personalizada/services/ai/confidence_router.py
"""
Roteador de Confiança — decide se a resposta Claude é suficiente ou se
deve ser escalada para Harvey AI.

Lógica em duas camadas:
1. Condições de forçamento (override do score): certas situações sempre vão
   para Harvey independente do score calculado.
2. Score ponderado (0.0-1.0): se o score ficar abaixo do threshold do
   escritório, roteia para Harvey.

O roteador é stateless — recebe todos os dados necessários como parâmetros
e retorna um ConfidenceScore imutável.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from shared.models.escritorio import Escritorio

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Termos jurídicos que forçam roteamento para Harvey (independente do score)
# ---------------------------------------------------------------------------

_TERMOS_HARVEY_FORCADO: list[re.Pattern] = [
    re.compile(r"\bCPC\s+art\.?\s*\d+", re.IGNORECASE),
    re.compile(r"\bCLT\s+art\.?\s*\d+", re.IGNORECASE),
    re.compile(r"\bSTJ\b", re.IGNORECASE),
    re.compile(r"\bSTF\b", re.IGNORECASE),
    re.compile(r"\bS[uú]mula\b", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Score base por tipo de intenção (componente de 25% da fórmula)
# Intenções simples têm score alto (Claude consegue responder bem).
# Intenções jurídicas complexas têm score baixo (Harvey é melhor).
# ---------------------------------------------------------------------------

_SCORE_INTENCAO: dict[str, float] = {
    "status": 0.95,
    "saudacao": 0.90,
    "reclamacao": 0.75,
    "duvida_termo": 0.70,
    "outro": 0.65,
    "pergunta_juridica": 0.45,
    "perspectivas": 0.35,
    "perspectiva_caso": 0.30,
    "juridica_complexa": 0.0,   # sempre Harvey via forçamento abaixo
}

# Pesos da fórmula de score ponderado
_PESO_RAG = 0.35
_PESO_FACT = 0.25
_PESO_INTENCAO = 0.25
_PESO_HISTORICO = 0.15


# ---------------------------------------------------------------------------
# Dataclasses públicos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfidenceScore:
    valor: float                        # 0.0 → 1.0
    componentes: dict[str, float]       # breakdown por dimensão
    deve_escalar_harvey: bool           # True se valor < threshold ou forçamento
    motivo: str                         # log interno — razão do roteamento


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class ConfidenceRouter:
    """
    Avalia a confiança da resposta Claude e decide se deve escalar para Harvey.

    Uso típico no nó LangGraph `avaliar_confianca`:

        router = ConfidenceRouter()
        score = router.avaliar(
            mensagem=state["mensagem_original"],
            resposta_claude=state["resposta_ia"],
            tipo_intencao=state["intencao"],
            rag_docs=state.get("rag_docs_com_score", []),
            fact_check_result=state.get("fact_check_result", {}),
            historico_cliente=state.get("historico", []),
            tentativas_geracao=state.get("tentativas_correcao", 0),
            escritorio_id=state["escritorio_id"],
        )
        destino = router.rotear(score, escritorio)
    """

    THRESHOLD = 0.70  # default; sobrescrito por escritorio.harvey_confidence_threshold

    def avaliar(
        self,
        mensagem: str,
        resposta_claude: str | None,
        tipo_intencao: str,
        rag_docs: list[dict[str, Any]],
        fact_check_result: dict[str, Any],
        historico_cliente: list[dict[str, Any]],
        tentativas_geracao: int = 0,
        escritorio_id: int | None = None,
    ) -> ConfidenceScore:
        """
        Calcula o ConfidenceScore da resposta Claude.

        Args:
            mensagem: Mensagem original do cliente.
            resposta_claude: Texto gerado pelo Claude (pode ser None se ainda não gerado).
            tipo_intencao: Intenção classificada (ex: "status", "pergunta_juridica").
            rag_docs: Lista de dicts com chave 'score' (similaridade coseno 0-1).
                      Lista vazia → score_rag = 0.0.
            fact_check_result: Dict retornado pelo FactChecker.
                               Chave relevante: "hallucination_score" (float 0-1).
            historico_cliente: Histórico de interações do cliente (últimas N).
                               Cada item pode ter chave "satisfacao" (NPS 1-5).
            tentativas_geracao: Quantas tentativas de geração já ocorreram.
            escritorio_id: Para log estruturado.

        Returns:
            ConfidenceScore com breakdown completo.
        """
        # ------------------------------------------------------------------
        # 1. Verificar condições de forçamento (bypass do score)
        # ------------------------------------------------------------------
        motivo_forcado = self._verificar_forcamento(
            mensagem, tipo_intencao, fact_check_result, tentativas_geracao
        )
        if motivo_forcado:
            logger.info(
                "confidence_harvey_forcado",
                motivo=motivo_forcado,
                escritorio_id=escritorio_id,
                tipo_intencao=tipo_intencao,
            )
            return ConfidenceScore(
                valor=0.0,
                componentes={
                    "rag": 0.0,
                    "fact": 0.0,
                    "intencao": 0.0,
                    "historico": 0.0,
                },
                deve_escalar_harvey=True,
                motivo=motivo_forcado,
            )

        # ------------------------------------------------------------------
        # 2. Calcular componentes do score ponderado
        # ------------------------------------------------------------------
        score_rag = self._score_rag(rag_docs)
        score_fact = self._score_fact(fact_check_result)
        score_intencao = _SCORE_INTENCAO.get(tipo_intencao, 0.65)
        score_historico = self._score_historico(historico_cliente)

        valor = (
            _PESO_RAG * score_rag
            + _PESO_FACT * score_fact
            + _PESO_INTENCAO * score_intencao
            + _PESO_HISTORICO * score_historico
        )
        # Clamp entre 0 e 1
        valor = max(0.0, min(1.0, valor))

        componentes = {
            "rag": round(score_rag, 4),
            "fact": round(score_fact, 4),
            "intencao": round(score_intencao, 4),
            "historico": round(score_historico, 4),
        }

        logger.debug(
            "confidence_score_calculado",
            valor=round(valor, 4),
            componentes=componentes,
            escritorio_id=escritorio_id,
            tipo_intencao=tipo_intencao,
        )

        return ConfidenceScore(
            valor=round(valor, 4),
            componentes=componentes,
            deve_escalar_harvey=False,  # rotear() decide com base no threshold
            motivo="score_calculado",
        )

    def rotear(self, score: ConfidenceScore, escritorio: "Escritorio") -> str:
        """
        Decide o destino da mensagem: "claude" ou "harvey".

        Verifica (em ordem):
        1. Harvey desabilitado no escritório → sempre claude
        2. Quota Harvey esgotada → força claude com log de aviso
        3. Forçamento (score.deve_escalar_harvey=True) → harvey
        4. Score abaixo do threshold do escritório → harvey
        5. Caso contrário → claude

        Returns:
            "claude" ou "harvey"
        """
        # Regra 1: feature flag global do escritório
        if not escritorio.harvey_habilitado:
            return "claude"

        # Regra 2: quota mensal esgotada
        if escritorio.harvey_tokens_usados_mes >= escritorio.harvey_quota_tokens_mes:
            logger.warning(
                "harvey_quota_esgotada",
                escritorio_id=escritorio.id,
                usados=escritorio.harvey_tokens_usados_mes,
                limite=escritorio.harvey_quota_tokens_mes,
            )
            return "claude"

        # Regra 3: forçamento (independente de score)
        if score.deve_escalar_harvey:
            return "harvey"

        # Regra 4: score abaixo do threshold configurado por escritório
        threshold = escritorio.harvey_confidence_threshold
        if score.valor < threshold:
            logger.info(
                "confidence_abaixo_threshold",
                score=score.valor,
                threshold=threshold,
                escritorio_id=escritorio.id,
            )
            return "harvey"

        return "claude"

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    @staticmethod
    def _verificar_forcamento(
        mensagem: str,
        tipo_intencao: str,
        fact_check_result: dict[str, Any],
        tentativas_geracao: int,
    ) -> str | None:
        """
        Retorna o motivo do forçamento se Harvey deve responder independente
        do score, ou None se a avaliação ponderada deve prosseguir.
        """
        # Intenção explicitamente jurídica-complexa
        if tipo_intencao == "juridica_complexa":
            return "intencao_juridica_complexa"

        # Alto risco de alucinação detectado pelo FactChecker
        hallucination_score = float(fact_check_result.get("hallucination_score", 0.0))
        if hallucination_score > 0.30:
            return f"hallucination_score_alto:{hallucination_score:.2f}"

        # Múltiplas tentativas de geração indicam resposta instável
        if tentativas_geracao > 1:
            return f"multiplas_tentativas:{tentativas_geracao}"

        # Mensagem contém referências legais específicas
        for padrao in _TERMOS_HARVEY_FORCADO:
            match = padrao.search(mensagem)
            if match:
                return f"termo_legal_detectado:{match.group(0)}"

        return None

    @staticmethod
    def _score_rag(rag_docs: list[dict[str, Any]]) -> float:
        """
        Score baseado na similaridade dos documentos RAG recuperados.

        Usa o max da similaridade coseno dos docs retornados.
        Sem docs → 0.0 (Claude está respondendo sem base documental).
        """
        if not rag_docs:
            return 0.0
        scores = [float(doc.get("score", 0.0)) for doc in rag_docs if "score" in doc]
        if not scores:
            # Docs presentes mas sem campo score — assumir cobertura parcial
            return 0.5
        return max(scores)

    @staticmethod
    def _score_fact(fact_check_result: dict[str, Any]) -> float:
        """
        Score baseado no resultado do FactChecker.

        `hallucination_score` 0.0 = sem alucinações (score_fact = 1.0).
        `hallucination_score` 1.0 = alucinação certa (score_fact = 0.0).
        Sem fact_check_result → score neutro 0.5.
        """
        if not fact_check_result:
            return 0.5
        hallucination = float(fact_check_result.get("hallucination_score", 0.5))
        return max(0.0, 1.0 - hallucination)

    @staticmethod
    def _score_historico(historico: list[dict[str, Any]]) -> float:
        """
        Score baseado na taxa de NPS ≥ 4 nas últimas 20 interações do cliente.

        Indica se Claude historicamente satisfez este cliente.
        Sem histórico com NPS → score neutro 0.5.
        """
        interacoes_com_nps = [
            h for h in historico[-20:] if h.get("satisfacao") is not None
        ]
        if not interacoes_com_nps:
            return 0.5
        satisfeitas = sum(1 for h in interacoes_com_nps if h["satisfacao"] >= 4)
        return satisfeitas / len(interacoes_com_nps)
