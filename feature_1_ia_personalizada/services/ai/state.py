"""
Tipos, constantes e utilitários compartilhados pelo orquestrador e seus nós.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from prometheus_client import Counter
from typing_extensions import TypedDict

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
    from feature_1_ia_personalizada.services.ai.confidence_router import ConfidenceRouter
    from feature_1_ia_personalizada.services.ai.escalation_client import EscalacaoClient
    from feature_1_ia_personalizada.services.ai.fact_checker import FactChecker
    from feature_1_ia_personalizada.services.ai.memory import ConversationMemory
    from feature_1_ia_personalizada.services.ai.translator import JuridicalTranslator
    from feature_1_ia_personalizada.services.escalacao.manager import EscalacaoManager
    from feature_1_ia_personalizada.services.legal_data.cache_manager import LegalDataCacheManager
    from feature_1_ia_personalizada.services.legal_data.datajud_client import DataJudClient
    from feature_1_ia_personalizada.services.messaging.evolution_client import EvolutionClient
    from feature_1_ia_personalizada.services.rag.retriever import RAGRetriever

# ---------------------------------------------------------------------------
# Erros de domínio
# ---------------------------------------------------------------------------


class QuotaExcedidaError(Exception):
    """Lançado quando o escritório atingiu o limite mensal de tokens Claude."""

    def __init__(self, escritorio_id: int, usados: int, limite: int) -> None:
        self.escritorio_id = escritorio_id
        self.usados = usados
        self.limite = limite
        super().__init__(
            f"Escritório {escritorio_id} atingiu quota mensal: {usados}/{limite} tokens"
        )


# ---------------------------------------------------------------------------
# State do fluxo LangGraph
# ---------------------------------------------------------------------------


class ConversationState(TypedDict):
    escritorio_id: int
    cliente_id: int
    processo_id: int | None
    mensagem_original: str
    tipo_mensagem: str
    historico: list[dict]
    intencao: str
    dados_processo: dict | None
    contexto_rag: str | None
    resposta_ia: str | None
    resposta_verificada: str | None
    tokens_usados: dict
    erro: str | None
    tentativas_correcao: int
    usando_fallback: bool
    precisa_regenerar: bool
    requer_escalacao: bool
    motivo_escalacao: str | None
    confidence_score: float | None
    modelo_ia_usado: str
    _escalar_para_opus: bool
    rag_docs_com_score: list[dict]
    fact_check_result: dict


# ---------------------------------------------------------------------------
# Container de dependências para os nós
# ---------------------------------------------------------------------------


@dataclass
class NodeDeps:
    claude: ClaudeClient
    memory: ConversationMemory
    translator: JuridicalTranslator
    datajud: DataJudClient
    cache: LegalDataCacheManager
    redis: Redis
    evolution: EvolutionClient
    session_factory: async_sessionmaker[AsyncSession]
    escalacao_manager: EscalacaoManager
    rag: RAGRetriever | None
    confidence_router: ConfidenceRouter
    escalacao_client: EscalacaoClient
    fact_checker: FactChecker


# ---------------------------------------------------------------------------
# Constantes de timeout
# ---------------------------------------------------------------------------

TIMEOUT_FLUXO_SEGUNDOS = 120.0
TIMEOUT_CLAUDE_SEGUNDOS = 25.0
TIMEOUT_DATAJUD_SEGUNDOS = 20.0

MSG_QUOTA_CLIENTE = (
    "No momento não consigo processar sua mensagem. "
    "Por favor, entre em contato diretamente com o escritório."
)

# ---------------------------------------------------------------------------
# Métricas Prometheus compartilhadas pelos nós
# ---------------------------------------------------------------------------

erros_total = Counter(
    "ia_orchestrator_errors_total",
    "Total de erros no orchestrator por nó",
    labelnames=["no"],
)

# ---------------------------------------------------------------------------
# Humanização — fragmentação de mensagens para WhatsApp
# ---------------------------------------------------------------------------


def fragmentar_resposta(texto: str) -> list[str]:
    """
    Divide a resposta em até 4 bolhas para envio em sequência no WhatsApp,
    agrupando parágrafos curtos com o seguinte.
    """
    partes_raw = [p.strip() for p in texto.split("\n\n") if p.strip()]
    if len(partes_raw) <= 1:
        return [texto.strip()] if texto.strip() else [texto]

    resultado: list[str] = []
    acumulado = ""
    for parte in partes_raw:
        if not acumulado:
            acumulado = parte
        elif len(acumulado) < 80:
            acumulado = acumulado + "\n\n" + parte
        else:
            resultado.append(acumulado)
            acumulado = parte
    if acumulado:
        resultado.append(acumulado)

    if len(resultado) > 4:
        meio = "\n\n".join(resultado[1:-1])
        resultado = [resultado[0], meio, resultado[-1]]

    return resultado


def delay_digitacao_whatsapp(texto: str) -> float:
    """Calcula delay realista entre mensagens (~45 palavras/min), entre 1.5s e 4.0s."""
    palavras = len(texto.split())
    return max(1.5, min(4.0, palavras * 0.10))


# ---------------------------------------------------------------------------
# Classificação por keywords — fallback quando Claude falha
# ---------------------------------------------------------------------------

_KEYWORDS: list[tuple[str, re.Pattern[str]]] = [
    (
        "status",
        re.compile(
            r"\b(status|andamento|situa[çc][aã]o|processo|como est[aá]|o que aconteceu|movimenta[çc][aã]o)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "perspectivas",
        re.compile(
            r"\b(chance|chances|probabilidade|vencer|ganhar|perder|procedente|improcedente|"
            r"vai dar certo|vale a pena|perspectiva|expectativa|resultado|prognóstico)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "duvida_termo",
        re.compile(
            r"\b(significa|quer dizer|o que [eé]|o que significa|defini[çc][aã]o|explica|me explica)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "saudacao",
        re.compile(
            r"\b(oi|ol[aá]|boa tarde|bom dia|boa noite|tudo bem|hey|hi)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "reclamacao",
        re.compile(
            r"\b(reclama[çc][aã]o|insatisfeito|demora|p[eé]ssimo|terr[ií]vel|problema|absurdo)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "duvida_geral",
        re.compile(
            r"\b(como funciona|quanto tempo|o que acontece|o que [eé] uma|o que [eé] um|"
            r"quando [eé]|posso|preciso|tenho direito|qual [eé] o prazo|fases do processo|"
            r"etapas|procedimento|como [eé] feito|pode acontecer|o que muda)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "desabafo",
        re.compile(
            r"\b(ansioso|ansiosa|preocupado|preocupada|medo|angustia|angustiado|sofrendo|"
            r"cansado|cansada|desesperado|desesperada|n[aã]o aguento|n[aã]o consigo|"
            r"estou mal|t[aã]o dif[ií]cil|muito dif[ií]cil|desabafo|chorar|chorando)\b",
            re.IGNORECASE,
        ),
    ),
]


def classificar_por_keywords(mensagem: str) -> str:
    for intencao, pattern in _KEYWORDS:
        if pattern.search(mensagem):
            return intencao
    return "outro"
