"""
Orquestrador da IA — Cérebro do Concierge Jurídico Digital.

Fluxo LangGraph:
  classificar_intencao
    ├─ (outro) ─────────────────────────────────────► gerar_resposta → mensagem fixa
    ├─ (saudacao) ──────────────────────────────────► gerar_resposta → boas-vindas
    └─ (status/duvida_termo/reclamacao/perspectivas) ► buscar_dados
                                                            │
                                            ┌───────────────┴───────────────┐
                                            │ (dados ok)                    │ (sem processos)
                                            ▼                               ▼
                                      gerar_resposta                 enviar_resposta
                                            │
                                            ▼
                                      avaliar_confianca
                                            │
                               ┌───────────┴──────────────┐
                               │ (ok)                      │ (escalar Opus)
                               ▼                           ▼
                         verificar_resposta       gerar_resposta_escalacao
                               │                           │
                               └─────────┬─────────────────┘
                                         ▼
                                   enviar_resposta → END

  tratar_erro ◄─── qualquer nó com exceção não recuperável → END
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import structlog
from prometheus_client import Counter
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

try:
    from langgraph.graph import END, StateGraph

    _LANGGRAPH_OK = True
except Exception:
    _LANGGRAPH_OK = False

from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
from feature_1_ia_personalizada.services.ai.confidence_router import ConfidenceRouter
from feature_1_ia_personalizada.services.ai.escalation_client import EscalacaoClient
from feature_1_ia_personalizada.services.ai.fact_checker import FactChecker
from feature_1_ia_personalizada.services.ai.memory import ConversationMemory
from feature_1_ia_personalizada.services.ai.nodes import (
    node_agendamento,
    node_avaliar_confianca,
    node_avaliar_escalacao,
    node_buscar_dados,
    node_classificar_intencao,
    node_enviar_resposta,
    node_gerar_resposta,
    node_gerar_resposta_escalacao,
    node_preparar_escalacao,
    node_tratar_erro,
    node_verificar_resposta,
)
from feature_1_ia_personalizada.services.ai.state import (
    MSG_QUOTA_CLIENTE,
    TIMEOUT_FLUXO_SEGUNDOS,
    ConversationState,
    NodeDeps,
    QuotaExcedidaError,
    classificar_por_keywords,
    erros_total,
)
from feature_1_ia_personalizada.services.ai.translator import JuridicalTranslator
from feature_1_ia_personalizada.services.escalacao.manager import EscalacaoManager
from feature_1_ia_personalizada.services.legal_data.cache_manager import LegalDataCacheManager
from feature_1_ia_personalizada.services.legal_data.datajud_client import DataJudClient
from feature_1_ia_personalizada.services.messaging.evolution_client import EvolutionClient
from feature_1_ia_personalizada.services.messaging.templates import TEMPLATE_ERRO_GENERICO
from feature_1_ia_personalizada.services.rag.retriever import RAGRetriever
from shared.config.constants import MENSAGENS_FALLBACK
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio
from shared.models.processo import Processo

# Alias de retrocompatibilidade para testes que importam o nome privado
_classificar_por_keywords = classificar_por_keywords

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Métricas Prometheus do orchestrator
# ---------------------------------------------------------------------------

_fluxo_total = Counter(
    "ia_orchestrator_flow_total",
    "Total de fluxos processados pelo orchestrator",
    labelnames=["intencao", "status"],
)
_ia_requests_total = Counter(
    "ia_requests_total",
    "Total de requisições processadas pela IA",
    labelnames=["intencao", "sucesso"],
)
_ia_fallback_used_total = Counter(
    "ia_fallback_used_total",
    "Total de vezes que o fallback foi ativado",
)


# ---------------------------------------------------------------------------
# Orquestrador principal
# ---------------------------------------------------------------------------


class ConversationOrchestrator:
    """
    Coordena o fluxo de conversa via LangGraph.

    Instanciado uma vez e reutilizado. Cada chamada a `processar()` cria
    um estado independente.
    """

    def __init__(
        self,
        claude_client: ClaudeClient,
        memory: ConversationMemory,
        translator: JuridicalTranslator,
        datajud_client: DataJudClient,
        cache_manager: LegalDataCacheManager,
        evolution_client: EvolutionClient,
        session_factory: async_sessionmaker[AsyncSession],
        rag_retriever: RAGRetriever | None = None,
    ) -> None:
        escalacao_manager = EscalacaoManager(
            claude_client=claude_client,
            evolution_client=evolution_client,
            session_factory=session_factory,
        )
        fact_checker = FactChecker(
            buscar_dados_processo=self._buscar_resumo_processo,
        )

        self._deps = NodeDeps(
            claude=claude_client,
            memory=memory,
            translator=translator,
            datajud=datajud_client,
            cache=cache_manager,
            redis=cache_manager._redis,
            evolution=evolution_client,
            session_factory=session_factory,
            escalacao_manager=escalacao_manager,
            rag=rag_retriever,
            confidence_router=ConfidenceRouter(),
            escalacao_client=EscalacaoClient(),
            fact_checker=fact_checker,
        )
        self._session_factory = session_factory

        if _LANGGRAPH_OK:
            self._graph = self._build_graph()
            logger.info("orchestrator_iniciado", modo="langgraph")
        else:
            self._graph = None
            logger.warning("orchestrator_iniciado", modo="fallback_simples_sem_langgraph")

    # -----------------------------------------------------------------------
    # API pública
    # -----------------------------------------------------------------------

    async def processar(
        self,
        escritorio_id: int,
        cliente_id: int,
        mensagem: str,
        tipo: str = "texto",
    ) -> dict[str, Any]:
        """
        Executa o fluxo completo: classifica → busca → gera → verifica → envia.

        Returns:
            {
                "resposta":        str,
                "intencao":        str,
                "usando_fallback": bool,
                "tokens_usados":   dict,
                "processo_id":     int | None,
            }
        """
        t_inicio = time.perf_counter()

        # Agendamento: se o cliente tem proposta de horários pendente e esta
        # mensagem escolhe uma opção (1/2/3 ou texto livre), o fluxo é resolvido
        # aqui — sem RAG e, na maioria dos casos, sem gastar tokens Claude.
        resposta_selecao = await self._tentar_selecao_agendamento(
            escritorio_id, cliente_id, mensagem, tipo
        )
        if resposta_selecao is not None:
            return resposta_selecao

        try:
            await self._verificar_quota_tokens(escritorio_id)
        except QuotaExcedidaError:
            try:
                async with self._session_factory() as session:
                    escritorio = await session.get(Escritorio, escritorio_id)
                    cliente = await session.get(Cliente, cliente_id)
                    if (
                        escritorio
                        and cliente
                        and escritorio.webhook_whatsapp_instance
                        and cliente.telefone_whatsapp
                    ):
                        await self._deps.evolution.enviar_texto(
                            escritorio.webhook_whatsapp_instance,
                            cliente.telefone_whatsapp,
                            MSG_QUOTA_CLIENTE,
                        )
            except Exception:
                pass
            return {
                "resposta": MSG_QUOTA_CLIENTE,
                "intencao": "outro",
                "usando_fallback": True,
                "tokens_usados": {},
                "processo_id": None,
            }

        historico = await self._deps.memory.buscar_historico(escritorio_id, cliente_id)

        initial_state: ConversationState = {
            "escritorio_id": escritorio_id,
            "cliente_id": cliente_id,
            "processo_id": None,
            "mensagem_original": mensagem,
            "tipo_mensagem": tipo,
            "historico": historico,
            "intencao": "outro",
            "dados_processo": None,
            "contexto_rag": None,
            "resposta_ia": None,
            "resposta_verificada": None,
            "tokens_usados": {"input": 0, "output": 0},
            "erro": None,
            "tentativas_correcao": 0,
            "usando_fallback": False,
            "precisa_regenerar": False,
            "requer_escalacao": False,
            "motivo_escalacao": None,
            "confidence_score": None,
            "modelo_ia_usado": "claude",
            "_escalar_para_opus": False,
            "rag_docs_com_score": [],
            "fact_check_result": {},
        }

        try:
            coro = (
                self._graph.ainvoke(initial_state)
                if self._graph is not None
                else self._fluxo_sequencial(initial_state)
            )
            final_state = await asyncio.wait_for(coro, timeout=TIMEOUT_FLUXO_SEGUNDOS)
        except TimeoutError:
            log = logger.bind(escritorio_id=escritorio_id, cliente_id=cliente_id)
            log.error("fluxo_timeout", timeout_s=TIMEOUT_FLUXO_SEGUNDOS)
            erros_total.labels(no="timeout_global").inc()
            return {
                "resposta": MENSAGENS_FALLBACK.get("timeout", TEMPLATE_ERRO_GENERICO),
                "intencao": "outro",
                "usando_fallback": True,
                "tokens_usados": {},
                "processo_id": None,
            }

        resposta_final = (
            final_state.get("resposta_verificada")
            or final_state.get("resposta_ia")
            or TEMPLATE_ERRO_GENERICO
        )
        _usando_fallback = final_state.get("usando_fallback", False)
        _intencao_final = final_state.get("intencao", "outro")

        _fluxo_total.labels(
            intencao=_intencao_final,
            status="fallback" if _usando_fallback else "ok",
        ).inc()
        _ia_requests_total.labels(
            intencao=_intencao_final,
            sucesso="false" if _usando_fallback else "true",
        ).inc()
        if _usando_fallback:
            _ia_fallback_used_total.inc()

        _elapsed_ms = (time.perf_counter() - t_inicio) * 1000
        _tokens_finais = final_state.get("tokens_usados") or {}
        _label_esc = str(escritorio_id)
        try:
            from feature_1_ia_personalizada.api.routes.metrics import (
                ia_custo_por_interacao_usd,
                ia_latencia_ms,
                ia_tokens_input_total,
                ia_tokens_output_total,
            )

            ia_latencia_ms.labels(intencao=_intencao_final).observe(_elapsed_ms)
            _tok_in = int(_tokens_finais.get("input", 0))
            _tok_out = int(_tokens_finais.get("output", 0))
            if _tok_in:
                ia_tokens_input_total.labels(
                    escritorio_id=_label_esc, intencao=_intencao_final
                ).inc(_tok_in)
            if _tok_out:
                ia_tokens_output_total.labels(
                    escritorio_id=_label_esc, intencao=_intencao_final
                ).inc(_tok_out)
            _custo = float(_tokens_finais.get("custo_str", "0") or "0")
            if _custo > 0:
                ia_custo_por_interacao_usd.labels(intencao=_intencao_final).observe(_custo)
        except Exception:
            pass

        _tok_in_final = int(_tokens_finais.get("input", 0))
        _tok_out_final = int(_tokens_finais.get("output", 0))
        if _tok_in_final + _tok_out_final > 0:
            asyncio.create_task(
                self._atualizar_uso_tokens(escritorio_id, _tok_in_final + _tok_out_final)
            )

        return {
            "resposta": resposta_final,
            "intencao": final_state.get("intencao", "outro"),
            "usando_fallback": final_state.get("usando_fallback", False),
            "tokens_usados": final_state.get("tokens_usados", {}),
            "processo_id": final_state.get("processo_id"),
        }

    # -----------------------------------------------------------------------
    # Agendamento — seleção de horário pelo cliente (early-exit)
    # -----------------------------------------------------------------------

    async def _tentar_selecao_agendamento(
        self,
        escritorio_id: int,
        cliente_id: int,
        mensagem: str,
        tipo: str,
    ) -> dict[str, Any] | None:
        """
        Se houver Agendamento `aguardando_cliente` e a mensagem escolher uma das
        opções, efetiva a escolha (notifier notifica o advogado nos 2 canais) e
        entrega a resposta ao cliente via node_enviar_resposta (WhatsApp +
        Interacao + memória). Retorna None para seguir o fluxo normal.
        """
        try:
            from feature_1_ia_personalizada.services.agendamento.notifier import (
                AgendamentoNotifier,
            )

            async with self._session_factory() as session:
                notifier = AgendamentoNotifier(
                    session=session,
                    evolution=self._deps.evolution,
                    redis=self._deps.redis,
                    claude=self._deps.claude,
                )
                resposta = await notifier.processar_resposta_cliente(
                    escritorio_id, cliente_id, mensagem
                )
        except Exception as exc:
            logger.warning(
                "agendamento_selecao_falhou",
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                erro=str(exc),
            )
            return None

        if resposta is None:
            return None

        state_entrega: ConversationState = {
            "escritorio_id": escritorio_id,
            "cliente_id": cliente_id,
            "processo_id": None,
            "mensagem_original": mensagem,
            "tipo_mensagem": tipo,
            "historico": [],
            "intencao": "agendar_reuniao",
            "dados_processo": None,
            "contexto_rag": None,
            "resposta_ia": resposta,
            "resposta_verificada": resposta,
            "tokens_usados": {"input": 0, "output": 0},
            "erro": None,
            "tentativas_correcao": 0,
            "usando_fallback": False,
            "precisa_regenerar": False,
            "requer_escalacao": False,
            "motivo_escalacao": None,
            "confidence_score": None,
            "modelo_ia_usado": "claude",
            "_escalar_para_opus": False,
            "rag_docs_com_score": [],
            "fact_check_result": {},
        }
        try:
            await node_enviar_resposta(state_entrega, self._deps)
        except Exception as exc:
            logger.warning("agendamento_entrega_selecao_falhou", erro=str(exc))

        _fluxo_total.labels(intencao="agendar_reuniao", status="ok").inc()
        _ia_requests_total.labels(intencao="agendar_reuniao", sucesso="true").inc()

        return {
            "resposta": resposta,
            "intencao": "agendar_reuniao",
            "usando_fallback": False,
            "tokens_usados": {},
            "processo_id": None,
        }

    # -----------------------------------------------------------------------
    # Construção do grafo LangGraph
    # -----------------------------------------------------------------------

    def _build_graph(self) -> Any:
        d = self._deps  # alias para closures

        def _wrap(fn: Any) -> Any:
            async def _node(state: ConversationState) -> dict[str, Any]:
                return await fn(state, d)  # type: ignore[no-any-return]

            return _node

        graph = StateGraph(ConversationState)
        graph.add_node("classificar_intencao", _wrap(node_classificar_intencao))
        graph.add_node("avaliar_escalacao", _wrap(node_avaliar_escalacao))
        graph.add_node("preparar_escalacao", _wrap(node_preparar_escalacao))
        graph.add_node("agendamento", _wrap(node_agendamento))
        graph.add_node("buscar_dados", _wrap(node_buscar_dados))
        graph.add_node("gerar_resposta", _wrap(node_gerar_resposta))
        graph.add_node("avaliar_confianca", _wrap(node_avaliar_confianca))
        graph.add_node("gerar_resposta_escalacao", _wrap(node_gerar_resposta_escalacao))
        graph.add_node("verificar_resposta", _wrap(node_verificar_resposta))
        graph.add_node("enviar_resposta", _wrap(node_enviar_resposta))
        graph.add_node("tratar_erro", _wrap(node_tratar_erro))

        graph.set_entry_point("classificar_intencao")
        graph.add_edge("classificar_intencao", "avaliar_escalacao")
        graph.add_conditional_edges(
            "avaliar_escalacao",
            self._rota_apos_avaliar_escalacao,
            {
                "preparar_escalacao": "preparar_escalacao",
                "agendamento": "agendamento",
                "buscar_dados": "buscar_dados",
                "gerar_resposta": "gerar_resposta",
                "tratar_erro": "tratar_erro",
            },
        )
        graph.add_edge("preparar_escalacao", "enviar_resposta")
        # Agendamento vai direto à entrega — propor horários não passa pelo RAG
        graph.add_conditional_edges(
            "agendamento",
            lambda state: "tratar_erro" if state.get("erro") else "enviar_resposta",
            {"enviar_resposta": "enviar_resposta", "tratar_erro": "tratar_erro"},
        )
        graph.add_conditional_edges(
            "buscar_dados",
            self._rota_apos_busca_dados,
            {
                "gerar_resposta": "gerar_resposta",
                "enviar_resposta": "enviar_resposta",
                "tratar_erro": "tratar_erro",
            },
        )
        graph.add_conditional_edges(
            "gerar_resposta",
            self._rota_apos_gerar_resposta,
            {"avaliar_confianca": "avaliar_confianca", "tratar_erro": "tratar_erro"},
        )
        graph.add_conditional_edges(
            "avaliar_confianca",
            self._rota_apos_avaliar_confianca,
            {
                "verificar_resposta": "verificar_resposta",
                "gerar_resposta_escalacao": "gerar_resposta_escalacao",
                "tratar_erro": "tratar_erro",
            },
        )
        graph.add_edge("gerar_resposta_escalacao", "verificar_resposta")
        graph.add_conditional_edges(
            "verificar_resposta",
            self._rota_apos_verificacao,
            {
                "enviar_resposta": "enviar_resposta",
                "gerar_resposta": "gerar_resposta",
                "tratar_erro": "tratar_erro",
            },
        )
        graph.add_edge("enviar_resposta", END)
        graph.add_edge("tratar_erro", END)
        return graph.compile()

    # -----------------------------------------------------------------------
    # Proxy methods para os nós (mantidos para retrocompatibilidade com testes)
    # -----------------------------------------------------------------------

    async def _node_classificar_intencao(self, state: ConversationState) -> dict[str, Any]:
        return await node_classificar_intencao(state, self._deps)

    async def _node_buscar_dados(self, state: ConversationState) -> dict[str, Any]:
        return await node_buscar_dados(state, self._deps)

    async def _node_gerar_resposta(self, state: ConversationState) -> dict[str, Any]:
        return await node_gerar_resposta(state, self._deps)

    async def _node_verificar_resposta(self, state: ConversationState) -> dict[str, Any]:
        return await node_verificar_resposta(state, self._deps)

    async def _node_enviar_resposta(self, state: ConversationState) -> dict[str, Any]:
        return await node_enviar_resposta(state, self._deps)

    async def _node_tratar_erro(self, state: ConversationState) -> dict[str, Any]:
        return await node_tratar_erro(state, self._deps)

    # -----------------------------------------------------------------------
    # Routing functions
    # -----------------------------------------------------------------------

    def _rota_apos_avaliar_escalacao(self, state: ConversationState) -> str:
        if state.get("erro"):
            return "tratar_erro"
        if state.get("requer_escalacao"):
            return "preparar_escalacao"
        if state.get("intencao") == "agendar_reuniao":
            return "agendamento"
        if state.get("intencao") in (
            "status",
            "duvida_termo",
            "duvida_geral",
            "reclamacao",
            "perspectivas",
            "saudacao",
        ):
            return "buscar_dados"
        return "gerar_resposta"

    def _rota_apos_busca_dados(self, state: ConversationState) -> str:
        if state.get("erro"):
            return "tratar_erro"
        if state.get("resposta_verificada"):
            return "enviar_resposta"
        return "gerar_resposta"

    def _rota_apos_gerar_resposta(self, state: ConversationState) -> str:
        return "tratar_erro" if state.get("erro") else "avaliar_confianca"

    def _rota_apos_avaliar_confianca(self, state: ConversationState) -> str:
        if state.get("erro"):
            return "tratar_erro"
        if state.get("_escalar_para_opus"):
            return "gerar_resposta_escalacao"
        return "verificar_resposta"

    def _rota_apos_verificacao(self, state: ConversationState) -> str:
        if state.get("erro"):
            return "tratar_erro"
        if state.get("precisa_regenerar") and (state.get("tentativas_correcao") or 0) < 2:
            return "gerar_resposta"
        return "enviar_resposta"

    # -----------------------------------------------------------------------
    # Quota de tokens
    # -----------------------------------------------------------------------

    async def _verificar_quota_tokens(self, escritorio_id: int) -> None:
        now = datetime.now(tz=UTC)
        async with self._session_factory() as session:
            escritorio = await session.get(Escritorio, escritorio_id)
            if escritorio is None or escritorio.quota_tokens_mes is None:
                return

            reset_em = escritorio.tokens_reset_em
            precisa_reset = reset_em is None or (
                reset_em.year != now.year or reset_em.month != now.month
            )
            if precisa_reset:
                await session.execute(
                    update(Escritorio)
                    .where(Escritorio.id == escritorio_id)
                    .values(tokens_usados_mes=0, tokens_reset_em=now)
                )
                await session.commit()
                return

            if escritorio.tokens_usados_mes >= escritorio.quota_tokens_mes:
                logger.warning(
                    "quota_tokens_excedida",
                    escritorio_id=escritorio_id,
                    tokens_usados=escritorio.tokens_usados_mes,
                    quota_tokens_mes=escritorio.quota_tokens_mes,
                    plano=escritorio.plano,
                )
                raise QuotaExcedidaError(
                    escritorio_id=escritorio_id,
                    usados=escritorio.tokens_usados_mes,
                    limite=escritorio.quota_tokens_mes,
                )

    async def _atualizar_uso_tokens(self, escritorio_id: int, tokens_total: int) -> None:
        if tokens_total <= 0:
            return
        try:
            async with self._session_factory() as session:
                await session.execute(
                    update(Escritorio)
                    .where(Escritorio.id == escritorio_id)
                    .values(tokens_usados_mes=Escritorio.tokens_usados_mes + tokens_total)
                )
                await session.commit()
        except Exception as exc:
            logger.warning(
                "quota_update_falhou",
                escritorio_id=escritorio_id,
                tokens=tokens_total,
                erro=str(exc),
            )

    # -----------------------------------------------------------------------
    # Adapter para FactChecker (precisa de self para usar session_factory)
    # -----------------------------------------------------------------------

    async def _buscar_resumo_processo(self, processo_id: str) -> dict[str, Any]:
        try:
            async with self._session_factory() as session:
                processo = await session.get(Processo, int(processo_id))
                if not processo:
                    return {}
                return {
                    "numero_cnj": processo.numero_cnj or "",
                    "tribunal": processo.tribunal or "",
                    "ultimo_andamento": processo.ultimo_andamento or "",
                    "prazo": None,
                }
        except Exception:
            return {}

    # -----------------------------------------------------------------------
    # Fluxo sequencial (fallback sem LangGraph)
    # -----------------------------------------------------------------------

    async def _fluxo_sequencial(self, state: ConversationState) -> ConversationState:
        d = self._deps
        s: dict[str, Any] = dict(state)

        async def _run(fn: Any, st: Any) -> Any:
            return await fn(st, d)

        s.update(await _run(node_classificar_intencao, s))
        if s.get("erro"):
            await _run(node_tratar_erro, s)
            return s  # type: ignore[return-value]

        s.update(await _run(node_avaliar_escalacao, s))
        if s.get("erro"):
            await _run(node_tratar_erro, s)
            return s  # type: ignore[return-value]

        if s.get("requer_escalacao"):
            s.update(await _run(node_preparar_escalacao, s))
            if s.get("erro"):
                await _run(node_tratar_erro, s)
                return s  # type: ignore[return-value]
            s.update(await _run(node_enviar_resposta, s))
            if s.get("erro"):
                await _run(node_tratar_erro, s)
            return s  # type: ignore[return-value]

        if s["intencao"] == "agendar_reuniao":
            s.update(await _run(node_agendamento, s))
            if s.get("erro"):
                await _run(node_tratar_erro, s)
                return s  # type: ignore[return-value]
            s.update(await _run(node_enviar_resposta, s))
            if s.get("erro"):
                await _run(node_tratar_erro, s)
            return s  # type: ignore[return-value]

        if s["intencao"] in (
            "status",
            "duvida_termo",
            "duvida_geral",
            "reclamacao",
            "perspectivas",
            "saudacao",
        ):
            s.update(await _run(node_buscar_dados, s))
            if s.get("erro"):
                await _run(node_tratar_erro, s)
                return s  # type: ignore[return-value]
            if s.get("resposta_verificada"):
                await _run(node_enviar_resposta, s)
                return s  # type: ignore[return-value]

        s.update(await _run(node_gerar_resposta, s))
        if s.get("erro"):
            await _run(node_tratar_erro, s)
            return s  # type: ignore[return-value]

        s.update(await _run(node_avaliar_confianca, s))
        if s.get("_escalar_para_opus"):
            s.update(await _run(node_gerar_resposta_escalacao, s))
            if s.get("erro"):
                await _run(node_tratar_erro, s)
                return s  # type: ignore[return-value]

        for _ in range(2):
            s.update(await _run(node_verificar_resposta, s))
            if s.get("erro"):
                await _run(node_tratar_erro, s)
                return s  # type: ignore[return-value]
            if not s.get("precisa_regenerar"):
                break
            s.update(await _run(node_gerar_resposta, s))
            if s.get("erro"):
                await _run(node_tratar_erro, s)
                return s  # type: ignore[return-value]

        s.update(await _run(node_enviar_resposta, s))
        if s.get("erro"):
            await _run(node_tratar_erro, s)
        return s  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def criar_orchestrador(
    api_key_anthropic: str,
    redis_client: Redis,
    session_factory: async_sessionmaker[AsyncSession],
    api_key_datajud: str | None = None,
    api_key_evolution: str | None = None,
    evolution_base_url: str = "http://localhost:8080",
) -> ConversationOrchestrator:
    return ConversationOrchestrator(
        claude_client=ClaudeClient(api_key=api_key_anthropic),
        memory=ConversationMemory(redis=redis_client),
        translator=JuridicalTranslator(),
        datajud_client=DataJudClient(api_key=api_key_datajud),
        cache_manager=LegalDataCacheManager(redis_client=redis_client),
        evolution_client=EvolutionClient(
            base_url=evolution_base_url,
            api_key=api_key_evolution or "",
        ),
        session_factory=session_factory,
    )


# ---------------------------------------------------------------------------
# Singleton para workers Celery
# ---------------------------------------------------------------------------

_translator_singleton: JuridicalTranslator | None = None


def _criar_translator() -> JuridicalTranslator:
    return _translator_singleton if _translator_singleton is not None else JuridicalTranslator()


def inicializar_orchestrador_worker() -> None:
    global _translator_singleton
    _translator_singleton = JuridicalTranslator()
    logger.info(
        "orchestrador_worker_inicializado",
        total_termos=_translator_singleton.total_termos,
    )


# ---------------------------------------------------------------------------
# Entry point síncrono para Celery workers
# ---------------------------------------------------------------------------


def executar_fluxo_orquestrador(
    id_escritorio: int,
    id_cliente: int,
    mensagem: str,
    tipo: str = "texto",
) -> dict[str, Any]:
    import redis.asyncio as aioredis

    from shared.config.settings import settings
    from shared.database.connection import async_session_factory

    async def _run() -> dict[str, Any]:
        redis_client = aioredis.from_url(settings.REDIS_URL)
        assert settings.EVOLUTION_API_URL and settings.EVOLUTION_API_KEY
        try:
            orchestrador = ConversationOrchestrator(
                claude_client=ClaudeClient(api_key=settings.ANTHROPIC_API_KEY),
                memory=ConversationMemory(redis=redis_client),
                translator=_criar_translator(),
                datajud_client=DataJudClient(api_key=settings.DATAJUD_API_KEY),
                cache_manager=LegalDataCacheManager(redis_client=redis_client),
                evolution_client=EvolutionClient(
                    base_url=settings.EVOLUTION_API_URL,
                    api_key=settings.EVOLUTION_API_KEY,
                ),
                session_factory=async_session_factory,
            )
            return await orchestrador.processar(id_escritorio, id_cliente, mensagem, tipo)
        finally:
            await redis_client.close()

    return asyncio.run(_run())
