"""
feature_1_ia_personalizada/services/ai/processo_state.py

Gerencia o estado processual de cada processo judicial monitorado.

Responsabilidades:
  - Ler e inicializar estado_atual do processo (fase, andamentos recentes, próximo passo)
  - Classificar a fase processual a partir do texto do andamento
  - Atualizar estado_atual e fase_processual no banco
  - Gerar contexto histórico formatado para injeção no prompt

Segue o mesmo padrão de worker_queries.py: métodos async internos (_)
encapsulados em métodos síncronos públicos via asyncio.run() — compatível
com workers Celery que não possuem event loop ativo.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import structlog
from sqlalchemy import desc, select, update

from shared.database.connection import async_session_factory
from shared.models.interacao import Interacao
from shared.models.processo import Processo as ProcessoModel

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Mapa de classificação de fase — palavras-chave → fase processual
# Ordem importa: mais específico primeiro.
# ---------------------------------------------------------------------------

_MAPA_FASES: list[tuple[str, list[str]]] = [
    ("encerrado", ["arquivado", "extinto", "baixa definitiva", "trânsito em julgado"]),
    ("execucao", ["execução", "cumprimento de sentença", "penhora", "arresto", "leilão", "hasta"]),
    (
        "recurso",
        ["apelação", "recurso", "agravo", "embargos de declaração", "especial", "extraordinário"],
    ),
    (
        "julgamento",
        [
            "sentença",
            "acórdão",
            "julgamento",
            "improcedente",
            "procedente",
            "provido",
            "desprovido",
        ],
    ),
    (
        "saneamento",
        ["saneamento", "saneado", "audiência de instrução", "prova pericial", "laudo", "perícia"],
    ),
    ("instrucao", ["audiência", "designada", "intimação", "intimado", "testemunha", "depoimento"]),
    ("conhecimento", []),  # fase padrão (fallback)
]

# Próximo passo esperado por fase
_PROXIMO_PASSO: dict[str, str] = {
    "conhecimento": "O juiz vai analisar o pedido inicial. Prazo típico: 15 a 30 dias.",
    "instrucao": "Coleta de provas e depoimentos. Prazo típico: 30 a 90 dias.",
    "saneamento": "Realização de perícia ou audiência de instrução. Prazo típico: 30 a 120 dias.",
    "julgamento": "Publicação da sentença. Prazo típico: 15 a 60 dias.",
    "recurso": "Análise do recurso pelo tribunal. Prazo típico: 3 a 18 meses.",
    "execucao": "Cumprimento da decisão (pagamento, penhora ou acordo). Prazo variável.",
    "encerrado": "Processo finalizado. Nenhum passo adicional previsto.",
}


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _classificar_fase(texto: str) -> str:
    """Retorna a fase processual com base em palavras-chave no texto do andamento."""
    texto_lower = texto.lower()
    for fase, palavras in _MAPA_FASES:
        if not palavras:
            return fase  # fallback: conhecimento
        if any(p in texto_lower for p in palavras):
            return fase
    return "conhecimento"


def _run(coro) -> Any:
    """Executa corrotina bloqueante. Seguro em workers Celery."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Queries assíncronas internas
# ---------------------------------------------------------------------------


async def _get_state(processo_id: int) -> dict[str, Any]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ProcessoModel.estado_atual, ProcessoModel.fase_processual).where(
                ProcessoModel.id == processo_id
            )
        )
        row = result.one_or_none()

    if row is None:
        logger.warning("processo_state_nao_encontrado", processo_id=processo_id)
        return _estado_inicial()

    estado_atual, fase = row
    if estado_atual is None:
        return _estado_inicial()

    return cast(dict[str, Any], estado_atual)


async def _update_state(processo_id: int, novo_andamento: str) -> dict[str, Any]:
    fase = _classificar_fase(novo_andamento)

    async with async_session_factory() as session:
        async with session.begin():
            # SELECT FOR UPDATE garante que dois workers Celery não atualizem
            # o mesmo processo simultaneamente. O segundo worker bloqueia até
            # o primeiro commitar, evitando perda de andamentos por race condition.
            result = await session.execute(
                select(ProcessoModel.estado_atual)
                .where(ProcessoModel.id == processo_id)
                .with_for_update()
            )
            row = result.scalar_one_or_none()
            estado = row if isinstance(row, dict) else _estado_inicial()

            # Mantém os últimos 5 andamentos
            ultimos: list[str] = estado.get("ultimos_andamentos", [])
            ultimos.append(novo_andamento)
            ultimos = ultimos[-5:]

            novo_estado: dict[str, Any] = {
                "fase": fase,
                "ultimos_andamentos": ultimos,
                "proximo_passo_esperado": _PROXIMO_PASSO.get(fase, ""),
            }

            await session.execute(
                update(ProcessoModel)
                .where(ProcessoModel.id == processo_id)
                .values(estado_atual=novo_estado, fase_processual=fase)
            )
        # session.begin() commita automaticamente ao sair do bloco

    logger.info(
        "processo_state_atualizado",
        processo_id=processo_id,
        fase=fase,
        andamento=novo_andamento[:80],
    )
    return novo_estado


async def _gerar_contexto_historico(processo_id: int, n_ultimos: int) -> str:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Interacao.mensagem_ia)
            .where(
                Interacao.processo_id == processo_id,
                Interacao.tipo == "notificacao",
                Interacao.mensagem_ia.isnot(None),
            )
            .order_by(desc(Interacao.created_at))
            .limit(n_ultimos)
        )
        mensagens = [row[0] for row in result.all()]

    if not mensagens:
        return "Nenhum andamento anterior registrado."

    linhas = [f"{i + 1}. {msg}" for i, msg in enumerate(reversed(mensagens))]
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# API pública síncrona
# ---------------------------------------------------------------------------


def _estado_inicial() -> dict[str, Any]:
    return {
        "fase": "conhecimento",
        "ultimos_andamentos": [],
        "proximo_passo_esperado": _PROXIMO_PASSO["conhecimento"],
    }


class ProcessoStateManager:
    """
    Gerencia o estado processual de um processo judicial.

    Dois conjuntos de métodos públicos:
    - Síncronos (get_state, update_state, gerar_contexto_historico):
      para workers Celery que não possuem event loop ativo.
    - Assíncronos (async_get_state, async_update_state, async_gerar_contexto_historico):
      para uso direto em FastAPI routes e no orchestrator.py.
    """

    # ------------------------------------------------------------------
    # Síncronos — uso em workers Celery
    # ------------------------------------------------------------------

    @staticmethod
    def get_state(processo_id: int) -> dict[str, Any]:
        """
        Lê estado_atual do banco (síncrono — para Celery).
        Se nulo, retorna estado inicial com fase 'conhecimento'.
        """
        return _run(_get_state(processo_id))  # type: ignore[no-any-return]

    @staticmethod
    def update_state(processo_id: int, novo_andamento: str) -> dict[str, Any]:
        """
        Classifica a fase, atualiza fase_processual e estado_atual no banco (síncrono — para Celery).
        Mantém histórico dos últimos 5 andamentos no JSONB.
        """
        return _run(_update_state(processo_id, novo_andamento))  # type: ignore[no-any-return]

    @staticmethod
    def gerar_contexto_historico(processo_id: int, n_ultimos: int = 5) -> str:
        """
        Retorna string enumerada das últimas notificações para injeção no prompt (síncrono — para Celery).
        """
        return _run(_gerar_contexto_historico(processo_id, n_ultimos))  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Assíncronos — uso em FastAPI routes e orchestrator.py
    # ------------------------------------------------------------------

    @staticmethod
    async def async_get_state(processo_id: int) -> dict[str, Any]:
        """Versão async de get_state — para uso em contextos com event loop ativo."""
        return await _get_state(processo_id)

    @staticmethod
    async def async_update_state(processo_id: int, novo_andamento: str) -> dict[str, Any]:
        """Versão async de update_state — para uso em contextos com event loop ativo."""
        return await _update_state(processo_id, novo_andamento)

    @staticmethod
    async def async_gerar_contexto_historico(processo_id: int, n_ultimos: int = 5) -> str:
        """Versão async de gerar_contexto_historico — para uso em contextos com event loop ativo."""
        return await _gerar_contexto_historico(processo_id, n_ultimos)

    # ------------------------------------------------------------------
    # Utilitário puro (sem I/O)
    # ------------------------------------------------------------------

    @staticmethod
    def classificar_fase(texto: str) -> str:
        """Classifica a fase processual a partir do texto do andamento (sem I/O)."""
        return _classificar_fase(texto)
