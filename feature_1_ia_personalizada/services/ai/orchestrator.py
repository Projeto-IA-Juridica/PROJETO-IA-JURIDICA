# feature_1_ia_personalizada/services/ai/orchestrator.py
"""
Orquestrador da IA — Cérebro do Concierge Jurídico Digital.

Fluxo LangGraph:
  classificar_intencao
    ├─ (outro) ───────────────────────────────────────► gerar_resposta → mensagem fixa (fora do escopo)
    ├─ (saudacao) ────────────────────────────────────► gerar_resposta → boas-vindas / recorrente
    └─ (status/duvida_termo/reclamacao/perspectivas) ─► buscar_dados
                                                              │
                                              ┌───────────────┴───────────────┐
                                              │ (dados ok)                    │ (sem processos)
                                              ▼                               ▼
                                        gerar_resposta                 enviar_resposta
                                              │
                                              ▼
                                        verificar_resposta
                                              │
                               ┌─────────────┴──────────────┐
                               │ (ok / fallback)             │ (corrigir, <2x)
                               ▼                             ▼
                         enviar_resposta             gerar_resposta (retry)
                               │
                               ▼
                              END

  tratar_erro ◄─── qualquer nó com exceção não recuperável
       │
       ▼
      END 
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
import time

from prometheus_client import Counter
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing_extensions import TypedDict

try:
    from langgraph.graph import END, StateGraph

    _LANGGRAPH_OK = True
except Exception:  # ImportError ou TypeError (pydantic v1 + Python 3.12)
    _LANGGRAPH_OK = False

from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
from feature_1_ia_personalizada.services.ai.fact_checker import FactChecker
from feature_1_ia_personalizada.services.ai.memory import ConversationMemory
from feature_1_ia_personalizada.services.ai.prompts import (
    SYSTEM_PROMPT_BASE,
    SYSTEM_PROMPT_BOAS_VINDAS,
    SYSTEM_PROMPT_CLASSIFICAR_INTENCAO,
    SYSTEM_PROMPT_DESABAFO,
    SYSTEM_PROMPT_DUVIDA_GERAL,
    SYSTEM_PROMPT_PERSPECTIVAS,
    SYSTEM_PROMPT_SAUDACAO_RECORRENTE,
    SYSTEM_PROMPT_STATUS_PROCESSO,
    SYSTEM_PROMPT_TRADUZIR_TERMO,
    gerar_instrucao_persona,
)
from feature_1_ia_personalizada.services.ai.translator import JuridicalTranslator
from feature_1_ia_personalizada.services.escalacao.manager import EscalacaoManager
from feature_1_ia_personalizada.services.legal_data.cache_manager import (
    LegalDataCacheManager,
)
from feature_1_ia_personalizada.services.legal_data.jusbrasil_client import (
    JusbrasilClient,
)
from feature_1_ia_personalizada.services.messaging.evolution_client import (
    EvolutionClient,
)
from feature_1_ia_personalizada.services.messaging.templates import (
    TEMPLATE_CLIENTE_SEM_PROCESSO,
    TEMPLATE_ERRO_GENERICO,
)
from feature_1_ia_personalizada.services.rag.retriever import RAGRetriever
from shared.config.constants import MENSAGENS_FALLBACK
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio
from shared.models.interacao import Interacao
from shared.models.processo import Processo

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Quota de tokens
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


# Fallback genérico exibido ao CLIENTE quando a quota está esgotada.
# Não expõe informações de billing — aviso real vai para o escritório via log/alerta.
_MSG_QUOTA_CLIENTE = (
    "No momento não consigo processar sua mensagem. "
    "Por favor, entre em contato diretamente com o escritório."
)

_TIMEOUT_FLUXO_SEGUNDOS = 120.0   # guard absoluto de último recurso (não deve ser atingido)
_TIMEOUT_CLAUDE_SEGUNDOS = 25.0   # timeout por chamada ao Claude
_TIMEOUT_JUSBRASIL_SEGUNDOS = 20.0  # timeout por chamada ao Jusbrasil/cache

# ---------------------------------------------------------------------------
# Humanização — fragmentação de mensagens para WhatsApp
# ---------------------------------------------------------------------------

def _fragmentar_resposta(texto: str) -> list[str]:
    """
    Divide a resposta em partes menores para envio em múltiplas mensagens WhatsApp.

    Simula o comportamento humano de enviar várias mensagens em sequência:
    divide por parágrafos (\\n\\n), agrupa partes muito curtas com a seguinte
    e limita a no máximo 4 bolhas para não fragmentar demais.
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


def _delay_digitacao_whatsapp(texto: str) -> float:
    """
    Calcula delay realista entre mensagens WhatsApp.
    Simula ~45 palavras/min (velocidade de digitação humana).
    Limitado entre 1.5s e 4.0s para ser perceptível mas não lento demais.
    """
    palavras = len(texto.split())
    return max(1.5, min(4.0, palavras * 0.10))

# ---------------------------------------------------------------------------
# Métricas Prometheus
# ---------------------------------------------------------------------------

_fluxo_total = Counter(
    "ia_orchestrator_flow_total",
    "Total de fluxos processados pelo orchestrator",
    labelnames=["intencao", "status"],
)
_erros_total = Counter(
    "ia_orchestrator_errors_total",
    "Total de erros no orchestrator por nó",
    labelnames=["no"],
)
_ia_requests_total = Counter(
    "ia_requests_total",
    "Total de requisições processadas pela IA (orquestrador)",
    labelnames=["intencao", "sucesso"],
)
_ia_fallback_used_total = Counter(
    "ia_fallback_used_total",
    "Total de vezes que o fallback foi ativado (Claude indisponível ou erro)",
)

# ---------------------------------------------------------------------------
# State Schema — CÉREBRO do fluxo
# ---------------------------------------------------------------------------


class ConversationState(TypedDict):
    escritorio_id: int
    cliente_id: int
    processo_id: int | None
    mensagem_original: str
    tipo_mensagem: str  # texto | audio_transcrito
    historico: list[dict]
    intencao: str  # status | duvida_termo | saudacao | reclamacao | perspectivas | outro
    dados_processo: dict | None
    contexto_rag: str | None  # bloco XML injetado no prompt; None = RAG sem resultado
    resposta_ia: str | None
    resposta_verificada: str | None
    tokens_usados: dict
    erro: str | None
    tentativas_correcao: int
    usando_fallback: bool
    precisa_regenerar: bool  # sinal interno: verificar_resposta → gerar_resposta
    requer_escalacao: bool
    motivo_escalacao: str | None


# ---------------------------------------------------------------------------
# Classificação por keywords — fallback quando Claude falha
# ---------------------------------------------------------------------------

_KEYWORDS: list[tuple[str, re.Pattern]] = [
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


def _classificar_por_keywords(mensagem: str) -> str:
    for intencao, pattern in _KEYWORDS:
        if pattern.search(mensagem):
            return intencao
    return "outro"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class ConversationOrchestrator:
    """
    Orquestrador LangGraph que coordena todo o fluxo de conversa.

    Instanciado uma vez via `criar_orchestrador()` e reutilizado.
    Cada chamada a `processar()` cria um estado independente e imutável.
    """

    def __init__(
        self,
        claude_client: ClaudeClient,
        memory: ConversationMemory,
        translator: JuridicalTranslator,
        jusbrasil_client: JusbrasilClient,
        cache_manager: LegalDataCacheManager,
        evolution_client: EvolutionClient,
        session_factory: async_sessionmaker[AsyncSession],
        rag_retriever: RAGRetriever | None = None,
    ) -> None:
        self._claude = claude_client
        self._memory = memory
        self._translator = translator
        self._jusbrasil = jusbrasil_client
        self._cache = cache_manager
        self._redis: Redis = cache_manager._redis  # reutiliza conexão já existente
        self._evolution = evolution_client
        self._session_factory = session_factory
        self._escalacao_manager = EscalacaoManager(
            claude_client=claude_client,
            evolution_client=evolution_client,
            session_factory=session_factory,
        )
        self._rag = rag_retriever  # None = RAG desativado (graceful degradation)

        # FactChecker usa DB via adapter
        self._fact_checker = FactChecker(
            buscar_dados_processo=self._buscar_resumo_processo_para_fact_checker,
        )

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
                "resposta":       str,
                "intencao":       str,
                "usando_fallback": bool,
                "tokens_usados":  {"input": int, "output": int},
                "processo_id":    int | None,
            }
        """
        t_inicio = time.perf_counter()

        # Verifica quota ANTES de invocar o LangGraph (e portanto antes de chamar Claude)
        try:
            await self._verificar_quota_tokens(escritorio_id)
        except QuotaExcedidaError:
            return {
                "resposta": _MSG_QUOTA_CLIENTE,
                "intencao": "outro",
                "usando_fallback": True,
                "tokens_usados": {},
                "processo_id": None,
            }

        historico = await self._memory.buscar_historico(escritorio_id, cliente_id)

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
        }

        try:
            coro = (
                self._graph.ainvoke(initial_state)
                if self._graph is not None
                else self._fluxo_sequencial(initial_state)
            )
            final_state = await asyncio.wait_for(coro, timeout=_TIMEOUT_FLUXO_SEGUNDOS)
        except TimeoutError:
            log = logger.bind(escritorio_id=escritorio_id, cliente_id=cliente_id)
            log.error("fluxo_timeout", timeout_s=_TIMEOUT_FLUXO_SEGUNDOS)
            _erros_total.labels(no="timeout_global").inc()
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

        # --- Métricas de negócio ---
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
            # Histograms sem escritorio_id (evita alta cardinality de séries temporais)
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
            pass  # métricas nunca bloqueiam o fluxo principal

        # Registra consumo de tokens para controle de quota (fire-and-forget)
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
    # DB / adapters
    # -----------------------------------------------------------------------

    async def _buscar_rag(
        self,
        state: ConversationState,
        contexto_processo: dict | None = None,
    ) -> str:
        """
        Chama o RAGRetriever de forma segura.
        Retorna string vazia se RAG não configurado ou em caso de erro.
        """
        if not self._rag:
            return ""
        try:
            return await self._rag.buscar(
                query=state["mensagem_original"],
                escritorio_id=state["escritorio_id"],
                contexto_processo=contexto_processo,
            )
        except Exception as exc:
            logger.warning("rag_busca_falhou_graceful", erro=str(exc))
            return ""

    async def _buscar_resumo_processo_para_fact_checker(self, processo_id: str) -> dict[str, Any]:
        """Adapter para FactChecker — lê dados reais do processo no banco."""
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

    async def _listar_processos_ativos(
        self,
        session: AsyncSession,
        escritorio_id: int,
        cliente_id: int,
    ) -> list[Processo]:
        stmt = (
            select(Processo)
            .where(
                Processo.cliente_id == cliente_id,
                Processo.escritorio_id == escritorio_id,
                Processo.monitoramento_ativo.is_(True),
            )
            .order_by(Processo.data_ultimo_andamento.desc().nullslast())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _obter_escritorio_cliente(
        self,
        session: AsyncSession,
        escritorio_id: int,
        cliente_id: int,
    ) -> tuple[Escritorio | None, Cliente | None]:
        escritorio = await session.get(Escritorio, escritorio_id)
        cliente = await session.get(Cliente, cliente_id)
        return escritorio, cliente

    async def _verificar_quota_tokens(self, escritorio_id: int) -> None:
        """
        Verifica se o escritório ainda tem quota mensal disponível.

        - Se tokens_reset_em é de um mês anterior, reseta o contador.
        - Se quota_tokens_mes é None (enterprise), sempre passa.
        - Lança QuotaExcedidaError se o limite foi atingido.
          O aviso ao escritório fica no log estruturado; o cliente vê apenas
          a mensagem genérica _MSG_QUOTA_CLIENTE.
        """
        now = datetime.now(tz=timezone.utc)
        async with self._session_factory() as session:
            escritorio = await session.get(Escritorio, escritorio_id)
            if escritorio is None:
                return  # escritório não encontrado — deixa o fluxo principal lidar

            # Sem limite configurado (enterprise ou plano não mapeado)
            if escritorio.quota_tokens_mes is None:
                return

            # Reset mensal: se o último reset foi em mês/ano diferente do atual
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
                return  # acabou de resetar — quota disponível

            # Verifica se já atingiu o limite
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
        """
        Incrementa tokens_usados_mes de forma atômica (UPDATE ... SET x = x + delta).
        Falhas são silenciosas — não devem bloquear a resposta ao cliente.
        """
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

    async def _obter_persona(
        self,
        redis: Redis,
        escritorio_id: int,
        escritorio: "Escritorio | None",
    ) -> str:
        """
        Retorna o bloco XML de persona para injetar nos prompts.
        Cacheia no Redis por 1h — persona muda raramente.
        """
        cache_key = f"escritorio_persona:{escritorio_id}"
        try:
            cached = await redis.get(cache_key)
            if cached:
                return cached  # type: ignore[return-value]
        except Exception:
            pass  # Redis indisponível — segue sem cache

        persona_nome = "Assistente Jurídico"
        persona_tom = "neutro"
        if escritorio:
            persona_nome = escritorio.persona_nome or persona_nome
            persona_tom = escritorio.persona_tom or persona_tom

        instrucao = gerar_instrucao_persona(persona_nome, persona_tom)

        try:
            await redis.set(cache_key, instrucao, ex=3600)  # TTL 1h
        except Exception:
            pass

        return instrucao

    async def _salvar_interacao(
        self,
        session: AsyncSession,
        state: ConversationState,
        resposta_final: str,
        tokens: dict,
        custo: Decimal,
        metadata_extra: dict | None = None,
    ) -> None:
        # custo vem direto do ClaudeClient (Decimal sem perda de precisão float)
        metadata: dict[str, Any] = metadata_extra or {}
        if state.get("usando_fallback"):
            metadata["usando_fallback"] = True

        interacao = Interacao(
            escritorio_id=state["escritorio_id"],
            cliente_id=state["cliente_id"],
            processo_id=state.get("processo_id"),
            tipo=state.get("tipo_mensagem", "texto"),
            direcao="saida",
            mensagem_cliente=state["mensagem_original"],
            mensagem_ia=resposta_final,
            tokens_input=tokens.get("input", 0),
            tokens_output=tokens.get("output", 0),
            custo_estimado=custo,
            metadata_json=metadata or None,
        )
        session.add(interacao)
        await session.commit()

    # -----------------------------------------------------------------------
    # Construção do grafo LangGraph
    # -----------------------------------------------------------------------

    def _build_graph(self):
        graph = StateGraph(ConversationState)

        graph.add_node("classificar_intencao", self._node_classificar_intencao)
        graph.add_node("avaliar_escalacao", self._node_avaliar_escalacao)
        graph.add_node("preparar_escalacao", self._node_preparar_escalacao)
        graph.add_node("buscar_dados", self._node_buscar_dados)
        graph.add_node("gerar_resposta", self._node_gerar_resposta)
        graph.add_node("verificar_resposta", self._node_verificar_resposta)
        graph.add_node("enviar_resposta", self._node_enviar_resposta)
        graph.add_node("tratar_erro", self._node_tratar_erro)

        graph.set_entry_point("classificar_intencao")

        graph.add_edge("classificar_intencao", "avaliar_escalacao")

        graph.add_conditional_edges(
            "avaliar_escalacao",
            self._rota_apos_avaliar_escalacao,
            {
                "preparar_escalacao": "preparar_escalacao",
                "buscar_dados": "buscar_dados",
                "gerar_resposta": "gerar_resposta",
                "tratar_erro": "tratar_erro",
            },
        )

        graph.add_edge("preparar_escalacao", "enviar_resposta")

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
            {
                "verificar_resposta": "verificar_resposta",
                "tratar_erro": "tratar_erro",
            },
        )

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
    # Routing functions (recebem state, retornam chave do próximo nó)
    # -----------------------------------------------------------------------

    def _rota_apos_avaliar_escalacao(self, state: ConversationState) -> str:
        if state.get("erro"):
            return "tratar_erro"
        if state.get("requer_escalacao"):
            return "preparar_escalacao"
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
        # resposta_verificada já setada = sem processos (cliente sem processos cadastrados)
        if state.get("resposta_verificada"):
            return "enviar_resposta"
        return "gerar_resposta"

    def _rota_apos_gerar_resposta(self, state: ConversationState) -> str:
        if state.get("erro"):
            return "tratar_erro"
        return "verificar_resposta"

    def _rota_apos_verificacao(self, state: ConversationState) -> str:
        if state.get("erro"):
            return "tratar_erro"
        if state.get("precisa_regenerar") and (state.get("tentativas_correcao") or 0) < 2:
            return "gerar_resposta"
        return "enviar_resposta"

    # -----------------------------------------------------------------------
    # Nó 1 — classificar_intencao
    # -----------------------------------------------------------------------

    async def _node_classificar_intencao(self, state: ConversationState) -> dict:
        log = logger.bind(
            escritorio_id=state["escritorio_id"],
            cliente_id=state["cliente_id"],
        )
        try:
            raw = await self._claude.classificar_intencao(
                system_prompt=SYSTEM_PROMPT_CLASSIFICAR_INTENCAO,
                mensagem=state["mensagem_original"],
            )
            parsed = json.loads(raw)
            intencao = parsed.get("intencao", "outro")
            categorias_validas = {
                "status",
                "perspectivas",
                "duvida_termo",
                "duvida_geral",
                "saudacao",
                "reclamacao",
                "desabafo",
                "parecer_juridico",
                "estrategia_processual",
                "negociacao",
                "decisao_judicial_impacto_alto",
                "outro",
            }
            if intencao not in categorias_validas:
                intencao = "outro"
            log.info("intencao_classificada_claude", intencao=intencao)
        except Exception as exc:
            intencao = _classificar_por_keywords(state["mensagem_original"])
            log.warning("intencao_fallback_keywords", intencao=intencao, erro=str(exc))

        return {"intencao": intencao}

    # -----------------------------------------------------------------------
    # Nó Avaliar Escalação
    # -----------------------------------------------------------------------
    async def _node_avaliar_escalacao(self, state: ConversationState) -> dict:
        log = logger.bind(
            escritorio_id=state["escritorio_id"],
            cliente_id=state["cliente_id"],
            intencao=state.get("intencao"),
        )
        ESCALACAO_OBRIGATORIA = {
            "parecer_juridico",
            "estrategia_processual",
            "negociacao",
            "decisao_judicial_impacto_alto",
        }
        intencao = state.get("intencao", "outro")
        if intencao in ESCALACAO_OBRIGATORIA:
            log.info("escalacao_detectada", motivo=intencao)
            return {"requer_escalacao": True, "motivo_escalacao": intencao}
        return {"requer_escalacao": False, "motivo_escalacao": None}

    # -----------------------------------------------------------------------
    # Nó Preparar Escalação
    # -----------------------------------------------------------------------
    async def _node_preparar_escalacao(self, state: ConversationState) -> dict:
        log = logger.bind(
            escritorio_id=state["escritorio_id"],
            cliente_id=state["cliente_id"],
            intencao=state.get("intencao"),
        )
        try:
            # Buscar informações necessárias (como instancia do whatsapp)
            instancia_whatsapp = ""
            async with self._session_factory() as session:
                escritorio, _ = await self._obter_escritorio_cliente(
                    session, state["escritorio_id"], state["cliente_id"]
                )
                if escritorio:
                    instancia_whatsapp = escritorio.webhook_whatsapp_instance or ""

            # Invocar o EscalacaoManager
            historico = state.get("historico", [])
            motivo = state.get("motivo_escalacao") or "indefinido"
            mensagem_cliente = state["mensagem_original"]
            
            # Despacha escalação em background para não atrasar resposta ao cliente.
            _task = asyncio.create_task(
                self._escalacao_manager.avaliar_e_notificar_advogados(
                    escritorio_id=state["escritorio_id"],
                    cliente_id=state["cliente_id"],
                    mensagem_cliente=mensagem_cliente,
                    motivo=motivo,
                    historico_recente=historico,
                    instancia_whatsapp=instancia_whatsapp,
                )
            )

            def _log_escalacao_error(task: asyncio.Task) -> None:
                if not task.cancelled() and (exc := task.exception()):
                    logger.error(
                        "escalacao_background_falhou",
                        escritorio_id=state["escritorio_id"],
                        erro=str(exc),
                    )
                    _erros_total.labels(no="escalacao_background").inc()

            _task.add_done_callback(_log_escalacao_error)

            fallback_msg = (
                "Sua pergunta é muito importante e específica para o andamento do seu caso particular. "
                "Para garantir a melhor orientação jurídica, encaminhei sua mensagem imediatamente "
                "para o advogado responsável, que analisará a questão e retornará em breve."
            )
            return {
                "resposta_ia": fallback_msg,
                "resposta_verificada": fallback_msg,
                "precisa_regenerar": False,
            }
        except Exception as exc:
            _erros_total.labels(no="preparar_escalacao").inc()
            log.error("preparar_escalacao_erro_inesperado", erro=str(exc))
            return {"erro": f"preparar_escalacao:{exc}"}

    # -----------------------------------------------------------------------
    # Nó 2 — buscar_dados
    # -----------------------------------------------------------------------

    async def _node_buscar_dados(self, state: ConversationState) -> dict:
        log = logger.bind(
            escritorio_id=state["escritorio_id"],
            cliente_id=state["cliente_id"],
        )
        try:
            async with self._session_factory() as session:
                processos = await self._listar_processos_ativos(
                    session, state["escritorio_id"], state["cliente_id"]
                )

            if not processos:
                log.info("cliente_sem_processos")
                return {"resposta_verificada": TEMPLATE_CLIENTE_SEM_PROCESSO}

            # MVP: usa o processo com andamento mais recente (primeiro da lista)
            processo = processos[0]
            numero_cnj = processo.numero_cnj

            # Tenta cache de andamentos → Jusbrasil como fallback.
            # RAG é executado em paralelo com Jusbrasil quando há cache miss,
            # eliminando latência adicional no caminho crítico.
            andamentos = await self._cache.get_andamentos(numero_cnj)
            if andamentos:
                log.debug("andamentos_do_cache", cnj=numero_cnj)
                contexto_rag = await self._buscar_rag(state)
            else:
                contexto_processo_para_rag = {
                    "tipo_acao": getattr(processo, "tipo_acao", None),
                    "tribunal": processo.tribunal,
                }
                try:
                    andamentos, contexto_rag = await asyncio.wait_for(
                        asyncio.gather(
                            self._jusbrasil.sincronizar_andamentos(numero_cnj),
                            self._buscar_rag(state, contexto_processo_para_rag),
                        ),
                        timeout=_TIMEOUT_JUSBRASIL_SEGUNDOS,
                    )
                    await self._cache.set_andamentos(numero_cnj, andamentos)
                    log.info("andamentos_do_jusbrasil", cnj=numero_cnj)
                except TimeoutError:
                    # Jusbrasil lento → degrada gracefully com dados do banco
                    log.warning(
                        "jusbrasil_timeout_usando_dados_banco",
                        timeout_s=_TIMEOUT_JUSBRASIL_SEGUNDOS,
                        cnj=numero_cnj,
                    )
                    andamentos = []
                    contexto_rag = ""

            ultimo_andamento = (
                andamentos[0].get("descricao", "")
                if andamentos
                else (processo.ultimo_andamento or "sem movimentação recente")
            )
            data_ultimo = (
                andamentos[0].get("data", "")
                if andamentos
                else (
                    processo.data_ultimo_andamento.isoformat()
                    if processo.data_ultimo_andamento
                    else "N/D"
                )
            )

            # Detecta termos jurídicos no andamento e monta glossário contextual
            termos_detectados = self._translator.identificar_termos_tecnicos(ultimo_andamento)
            glossario_andamento: dict[str, str] = {}
            for termo in termos_detectados:
                trad = self._translator.traduzir_termo(termo)
                if trad:
                    glossario_andamento[termo] = trad.split("\n\n")[0]

            # Histórico dos últimos 5 andamentos
            andamentos_recentes = [
                {"descricao": a.get("descricao", ""), "data": a.get("data", "")}
                for a in andamentos[:5]
                if a.get("descricao")
            ]

            dados_processo = {
                "processo_id": processo.id,
                "numero_cnj": numero_cnj,
                "tribunal": processo.tribunal or "N/D",
                "vara": processo.vara or "N/D",
                "polo_cliente": processo.polo_cliente or "autor",
                "ultimo_andamento": ultimo_andamento,
                "data_ultimo_andamento": data_ultimo,
                "andamentos_recentes": andamentos_recentes,
                "glossario_andamento": glossario_andamento,
            }

            log.info("dados_processo_obtidos", cnj=numero_cnj, rag_ativo=bool(contexto_rag))

            return {
                "processo_id": processo.id,
                "dados_processo": dados_processo,
                "contexto_rag": contexto_rag or None,
            }

        except Exception as exc:
            _erros_total.labels(no="buscar_dados").inc()
            log.error("buscar_dados_erro", erro=str(exc))
            return {"erro": f"buscar_dados:{exc}"}

    # -----------------------------------------------------------------------
    # Nó 3 — gerar_resposta
    # -----------------------------------------------------------------------

    async def _node_gerar_resposta(self, state: ConversationState) -> dict:
        log = logger.bind(
            escritorio_id=state["escritorio_id"],
            cliente_id=state["cliente_id"],
            intencao=state.get("intencao"),
        )
        try:
            intencao = state.get("intencao", "outro")
            dados = state.get("dados_processo") or {}

            # Tenta dicionário local antes do Claude (somente para duvida_termo)
            if intencao == "duvida_termo":
                traducao_local = self._translator.traduzir_termo(state["mensagem_original"])
                if traducao_local:
                    log.debug("termo_traduzido_dicionario_local")
                    return {
                        "resposta_ia": traducao_local,
                        "precisa_regenerar": False,
                    }

            # Sessão única: busca escritório e cliente
            async with self._session_factory() as session:
                escritorio, cliente = await self._obter_escritorio_cliente(
                    session, state["escritorio_id"], state["cliente_id"]
                )
            nome_escritorio = escritorio.nome if escritorio else "Escritório"
            nome_cliente = cliente.nome if cliente else "cliente"

            # Carrega persona (cacheada no Redis por 1h)
            persona_instrucao = await self._obter_persona(
                self._redis, state["escritorio_id"], escritorio
            )

            # Monta system_prompt baseado na intenção
            if intencao == "status" and dados:
                andamentos_lista = dados.get("andamentos_recentes") or []
                andamentos_str = (
                    "\n".join(
                        (
                            f"- {a['data']}: {a['descricao']}"
                            if a.get("data")
                            else f"- {a['descricao']}"
                        )
                        for a in andamentos_lista
                    )
                    or "Histórico não disponível"
                )
                system_prompt = SYSTEM_PROMPT_STATUS_PROCESSO.format(
                    nome_escritorio=nome_escritorio,
                    nome_cliente=nome_cliente,
                    numero_cnj=dados.get("numero_cnj", "N/D"),
                    tribunal=dados.get("tribunal", "N/D"),
                    vara=dados.get("vara", "N/D"),
                    ultimo_andamento=dados.get("ultimo_andamento", "sem movimentação recente"),
                    data_ultimo_andamento=dados.get("data_ultimo_andamento", "N/D"),
                    polo_cliente=dados.get("polo_cliente", "N/D"),
                    andamentos_recentes=andamentos_str,
                )
                # Injeta glossário de termos técnicos
                glossario = dados.get("glossario_andamento") or {}
                if glossario:
                    linhas = "\n".join(
                        f"- {termo}: {definicao}" for termo, definicao in glossario.items()
                    )
                    system_prompt += f"\n\n<glossario_termos>\n{linhas}\n</glossario_termos>"

            elif intencao == "perspectivas" and dados:
                # Explica por que não é possível fornecer previsões (compliance OAB)
                system_prompt = SYSTEM_PROMPT_PERSPECTIVAS.format(
                    nome_escritorio=nome_escritorio,
                    nome_cliente=nome_cliente,
                    numero_cnj=dados.get("numero_cnj", "N/D"),
                    tribunal=dados.get("tribunal", "N/D"),
                    polo_cliente=dados.get("polo_cliente", "N/D"),
                    ultimo_andamento=dados.get("ultimo_andamento", "sem movimentação recente"),
                )

            elif intencao == "duvida_geral" and dados:
                system_prompt = SYSTEM_PROMPT_DUVIDA_GERAL.format(
                    nome_escritorio=nome_escritorio,
                    nome_cliente=nome_cliente,
                    numero_cnj=dados.get("numero_cnj", "N/D"),
                    tribunal=dados.get("tribunal", "N/D"),
                    polo_cliente=dados.get("polo_cliente", "N/D"),
                    ultimo_andamento=dados.get("ultimo_andamento", "sem movimentação recente"),
                    data_ultimo_andamento=dados.get("data_ultimo_andamento", "N/D"),
                )

            elif intencao == "duvida_termo":
                system_prompt = SYSTEM_PROMPT_TRADUZIR_TERMO.format(
                    nome_escritorio=nome_escritorio,
                    nome_cliente=nome_cliente,
                    numero_cnj=dados.get("numero_cnj", "N/D"),
                    ultimo_andamento=dados.get("ultimo_andamento", "N/D"),
                )
            elif intencao == "saudacao":
                _numero_cnj = dados.get("numero_cnj", "N/D")
                _ultimo_andamento = dados.get("ultimo_andamento", "N/D")
                _data_ultimo = dados.get("data_ultimo_andamento", "N/D")
                cliente_recorrente = len(state.get("historico", [])) > 0
                if cliente_recorrente:
                    system_prompt = SYSTEM_PROMPT_SAUDACAO_RECORRENTE.format(
                        nome_escritorio=nome_escritorio,
                        nome_cliente=nome_cliente,
                        numero_cnj=_numero_cnj,
                        ultimo_andamento=_ultimo_andamento,
                        data_ultimo_andamento=_data_ultimo,
                    )
                else:
                    system_prompt = SYSTEM_PROMPT_BOAS_VINDAS.format(
                        nome_escritorio=nome_escritorio,
                        nome_cliente=nome_cliente,
                        numero_cnj=_numero_cnj,
                        ultimo_andamento=_ultimo_andamento,
                        data_ultimo_andamento=_data_ultimo,
                    )
            elif intencao == "desabafo":
                system_prompt = SYSTEM_PROMPT_DESABAFO.format(
                    nome_escritorio=nome_escritorio,
                    nome_cliente=nome_cliente,
                )
            else:
                system_prompt = SYSTEM_PROMPT_BASE.format(
                    nome_escritorio=nome_escritorio,
                    nome_cliente=nome_cliente,
                )

            # Prefixa persona (nome + tom) no system_prompt
            if persona_instrucao:
                system_prompt = persona_instrucao + system_prompt

            # Injeta contexto RAG no prompt quando disponível
            # (só presente para intenções que passam por buscar_dados)
            contexto_rag = state.get("contexto_rag") or ""
            if contexto_rag:
                system_prompt += f"\n\n{contexto_rag}"

            resultado = await asyncio.wait_for(
                self._claude.enviar_mensagem(
                    system_prompt=system_prompt,
                    mensagens_historico=state.get("historico", []),
                    mensagem_usuario=state["mensagem_original"],
                    intencao=intencao,
                ),
                timeout=_TIMEOUT_CLAUDE_SEGUNDOS,
            )

            tokens_anteriores = state.get("tokens_usados") or {"input": 0, "output": 0}
            custo_anterior = Decimal(tokens_anteriores.get("custo_str", "0"))
            tokens_atualizados = {
                "input": tokens_anteriores.get("input", 0) + resultado["tokens_input"],
                "output": tokens_anteriores.get("output", 0) + resultado["tokens_output"],
                "custo_str": str(custo_anterior + resultado["custo"]),
            }

            log.info("resposta_gerada", tokens=tokens_atualizados)
            return {
                "resposta_ia": resultado["resposta"],
                "tokens_usados": tokens_atualizados,
                "precisa_regenerar": False,
            }

        except (RuntimeError, TimeoutError) as exc:
            # Claude indisponível ou lento demais → ativar fallback com mensagem pré-definida
            _erros_total.labels(no="gerar_resposta").inc()
            _is_timeout = isinstance(exc, TimeoutError)
            log.error(
                "claude_timeout_ativando_fallback" if _is_timeout else "claude_indisponivel_ativando_fallback",
                erro=str(exc),
                timeout_s=_TIMEOUT_CLAUDE_SEGUNDOS if _is_timeout else None,
            )

            intencao = state.get("intencao", "outro")
            dados = state.get("dados_processo") or {}

            if intencao == "status":
                numero = dados.get("numero_cnj", "seu processo")
                fallback_msg = (
                    f"Recebemos sua mensagem sobre o processo {numero}. "
                    "No momento estou com dificuldades técnicas, "
                    "mas o escritório retornará em breve."
                )
            elif intencao == "perspectivas":
                fallback_msg = (
                    "Entendo sua dúvida sobre as perspectivas do processo. "
                    "Estou com uma instabilidade técnica agora — "
                    "o escritório entrará em contato em breve para esclarecer. ⚖️"
                )
            elif intencao in ("duvida_termo", "duvida_geral"):
                fallback_msg = (
                    "Obrigado pela pergunta! Estou com uma dificuldade técnica temporária. "
                    "Encaminhei sua dúvida ao escritório."
                )
            elif intencao == "saudacao":
                fallback_msg = (
                    "Olá! No momento estou passando por uma manutenção rápida. "
                    "O escritório entrará em contato em breve."
                )
            elif intencao == "desabafo":
                fallback_msg = (
                    "Entendo que esse momento pode ser muito difícil. "
                    "Estou com uma instabilidade técnica agora, mas o escritório "
                    "está ciente e entrará em contato com você em breve. 🤝"
                )
            else:
                fallback_msg = MENSAGENS_FALLBACK.get("indisponivel", TEMPLATE_ERRO_GENERICO)

            return {
                "resposta_ia": fallback_msg,
                "usando_fallback": True,
                "precisa_regenerar": False,
            }

        except Exception as exc:
            _erros_total.labels(no="gerar_resposta").inc()
            log.error("gerar_resposta_erro_inesperado", erro=str(exc))
            return {"erro": f"gerar_resposta:{exc}"}

    # -----------------------------------------------------------------------
    # Nó 4 — verificar_resposta
    # -----------------------------------------------------------------------

    async def _node_verificar_resposta(self, state: ConversationState) -> dict:
        log = logger.bind(
            escritorio_id=state["escritorio_id"],
            cliente_id=state["cliente_id"],
        )

        # Mensagens de fallback são pré-definidas e seguras — pula verificação
        if state.get("usando_fallback"):
            return {
                "resposta_verificada": state.get("resposta_ia"),
                "precisa_regenerar": False,
            }

        resposta = state.get("resposta_ia", "")
        if not resposta:
            return {"erro": "verificar_resposta:resposta_vazia"}

        try:
            # Objeto stub para o FactChecker gravar metadata de auditoria
            class _InteracaoStub:
                metadata_json: dict | None = None

            stub = _InteracaoStub()

            # Disclaimer habilitado para status e perspectivas
            eh_sobre_processo = state.get("intencao") in ("status", "perspectivas")
            resposta_filtrada = self._fact_checker.filtrar_resposta(
                resposta_ia=resposta,
                interacao=stub,
                adicionar_disclaimer=eh_sobre_processo,
            )

            # Verificar factualidade quando há dados de processo
            precisa_regenerar = False
            if state.get("dados_processo") and state.get("processo_id"):
                resultado_fc = await self._fact_checker.verificar_status_processo(
                    processo_id=str(state["processo_id"]),
                    afirmacao_ia=resposta_filtrada,
                    interacao=stub,
                )
                if not resultado_fc["verificado"]:
                    tentativas = state.get("tentativas_correcao") or 0
                    if tentativas < 2:
                        precisa_regenerar = True
                        log.warning(
                            "fact_check_divergencia",
                            correcoes=resultado_fc["correcoes"],
                            tentativa=tentativas,
                        )
                    else:
                        log.error("fact_check_max_tentativas_atingidas")
                        resposta_filtrada = MENSAGENS_FALLBACK.get(
                            "indisponivel", TEMPLATE_ERRO_GENERICO
                        )

            updates: dict[str, Any] = {
                "resposta_verificada": resposta_filtrada,
                "precisa_regenerar": precisa_regenerar,
            }
            if precisa_regenerar:
                updates["tentativas_correcao"] = state.get("tentativas_correcao", 0) + 1

            return updates

        except Exception as exc:
            _erros_total.labels(no="verificar_resposta").inc()
            log.error("verificar_resposta_erro", erro=str(exc))
            return {
                "resposta_verificada": resposta,
                "precisa_regenerar": False,
            }

    # -----------------------------------------------------------------------
    # Nó 5 — enviar_resposta
    # -----------------------------------------------------------------------

    async def _node_enviar_resposta(self, state: ConversationState) -> dict:
        log = logger.bind(
            escritorio_id=state["escritorio_id"],
            cliente_id=state["cliente_id"],
        )

        resposta_final = (
            state.get("resposta_verificada") or state.get("resposta_ia") or TEMPLATE_ERRO_GENERICO
        )
        tokens = state.get("tokens_usados") or {"input": 0, "output": 0}
        custo = Decimal(tokens.get("custo_str", "0"))

        try:
            async with self._session_factory() as session:
                escritorio, cliente = await self._obter_escritorio_cliente(
                    session, state["escritorio_id"], state["cliente_id"]
                )

                if not escritorio or not cliente:
                    log.error("escritorio_ou_cliente_nao_encontrado")
                    return {"erro": "enviar_resposta:entidade_nao_encontrada"}

                instance = escritorio.webhook_whatsapp_instance
                numero = cliente.telefone_whatsapp

                if instance and numero:
                    try:
                        # Fragmenta a resposta em partes menores para simular
                        # digitação humana no WhatsApp (múltiplas mensagens em sequência).
                        partes = _fragmentar_resposta(resposta_final)
                        for i, parte in enumerate(partes):
                            await self._evolution.enviar_texto(instance, numero, parte)
                            # Delay de digitação entre partes (exceto após a última)
                            if i < len(partes) - 1:
                                await asyncio.sleep(_delay_digitacao_whatsapp(partes[i + 1]))
                        log.info(
                            "mensagem_enviada_whatsapp",
                            numero_parcial=numero[:4] + "***",
                            partes=len(partes),
                        )
                    except Exception as exc_wa:
                        log.warning("falha_envio_whatsapp", erro=str(exc_wa))
                else:
                    log.warning(
                        "instancia_ou_numero_ausente",
                        instance=instance,
                        numero=bool(numero),
                    )

                await self._memory.salvar_mensagem(
                    state["escritorio_id"],
                    state["cliente_id"],
                    "user",
                    state["mensagem_original"],
                )
                await self._memory.salvar_mensagem(
                    state["escritorio_id"],
                    state["cliente_id"],
                    "assistant",
                    resposta_final,
                )

                await self._salvar_interacao(session, state, resposta_final, tokens, custo)

            log.info(
                "fluxo_concluido",
                intencao=state.get("intencao"),
                usando_fallback=state.get("usando_fallback"),
                tokens=tokens,
            )
            return {"precisa_regenerar": False}

        except Exception as exc:
            _erros_total.labels(no="enviar_resposta").inc()
            log.error("enviar_resposta_erro", erro=str(exc))
            return {"erro": f"enviar_resposta:{exc}"}

    # -----------------------------------------------------------------------
    # Nó 6 — tratar_erro
    # -----------------------------------------------------------------------

    async def _node_tratar_erro(self, state: ConversationState) -> dict:
        erro = state.get("erro", "erro_desconhecido")
        log = logger.bind(
            escritorio_id=state["escritorio_id"],
            cliente_id=state["cliente_id"],
            erro=erro,
        )
        log.error("fluxo_erro_nao_recuperavel")
        _erros_total.labels(no="tratar_erro").inc()

        try:
            async with self._session_factory() as session:
                escritorio, cliente = await self._obter_escritorio_cliente(
                    session, state["escritorio_id"], state["cliente_id"]
                )

                if (
                    escritorio
                    and cliente
                    and escritorio.webhook_whatsapp_instance
                    and cliente.telefone_whatsapp
                ):
                    try:
                        await self._evolution.enviar_texto(
                            escritorio.webhook_whatsapp_instance,
                            cliente.telefone_whatsapp,
                            TEMPLATE_ERRO_GENERICO,
                        )
                    except Exception as exc_wa:
                        log.warning("falha_envio_mensagem_erro", erro=str(exc_wa))

                metadata = {
                    "erro": True,
                    "tipo_erro": erro,
                }
                interacao = Interacao(
                    escritorio_id=state["escritorio_id"],
                    cliente_id=state["cliente_id"],
                    processo_id=state.get("processo_id"),
                    tipo=state.get("tipo_mensagem", "texto"),
                    direcao="saida",
                    mensagem_cliente=state["mensagem_original"],
                    mensagem_ia=TEMPLATE_ERRO_GENERICO,
                    tokens_input=0,
                    tokens_output=0,
                    custo_estimado=Decimal("0"),
                    metadata_json=metadata,
                )
                session.add(interacao)
                await session.commit()

        except Exception as exc_inner:
            log.error("tratar_erro_falhou_persistir", exc_inner=str(exc_inner))

        return {"usando_fallback": True}

    # -----------------------------------------------------------------------
    # Fluxo sequencial — usado quando LangGraph não está disponível
    # -----------------------------------------------------------------------

    async def _fluxo_sequencial(self, state: ConversationState) -> ConversationState:
        """Executa os nós em sequência quando LangGraph não está instalado."""
        state = dict(state)  # type: ignore[assignment]

        # Nó 1: classificar
        state.update(await self._node_classificar_intencao(state))  # type: ignore[typeddict-item]
        if state.get("erro"):
            await self._node_tratar_erro(state)
            return state  # type: ignore[return-value]

        # Nó Avaliar Escalação
        state.update(await self._node_avaliar_escalacao(state))  # type: ignore[typeddict-item]
        if state.get("erro"):
            await self._node_tratar_erro(state)
            return state  # type: ignore[return-value]

        if state.get("requer_escalacao"):
            state.update(await self._node_preparar_escalacao(state))  # type: ignore[typeddict-item]
            if state.get("erro"):
                await self._node_tratar_erro(state)
                return state  # type: ignore[return-value]
            state.update(await self._node_enviar_resposta(state))  # type: ignore[typeddict-item]
            if state.get("erro"):
                await self._node_tratar_erro(state)
            return state  # type: ignore[return-value]

        # Nó 2: buscar dados (se intenção exige processo)
        if state["intencao"] in (
            "status",
            "duvida_termo",
            "duvida_geral",
            "reclamacao",
            "perspectivas",
            "saudacao",
        ):
            state.update(await self._node_buscar_dados(state))  # type: ignore[typeddict-item]
            if state.get("erro"):
                await self._node_tratar_erro(state)
                return state  # type: ignore[return-value]
            if state.get("resposta_verificada"):
                await self._node_enviar_resposta(state)
                return state  # type: ignore[return-value]

        # Nó 3: gerar resposta
        state.update(await self._node_gerar_resposta(state))  # type: ignore[typeddict-item]
        if state.get("erro"):
            await self._node_tratar_erro(state)
            return state  # type: ignore[return-value]

        # Nó 4: verificar (com até 1 re-geração)
        for _ in range(2):
            state.update(await self._node_verificar_resposta(state))  # type: ignore[typeddict-item]
            if state.get("erro"):
                await self._node_tratar_erro(state)
                return state  # type: ignore[return-value]
            if not state.get("precisa_regenerar"):
                break
            state.update(await self._node_gerar_resposta(state))  # type: ignore[typeddict-item]
            if state.get("erro"):
                await self._node_tratar_erro(state)
                return state  # type: ignore[return-value]

        # Nó 5: enviar
        state.update(await self._node_enviar_resposta(state))  # type: ignore[typeddict-item]
        if state.get("erro"):
            await self._node_tratar_erro(state)

        return state  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Factory — cria o orchestrador com todas as dependências
# ---------------------------------------------------------------------------


def criar_orchestrador(
    api_key_anthropic: str,
    redis_client: Redis,
    session_factory: async_sessionmaker[AsyncSession],
    api_key_jusbrasil: str | None = None,
    api_key_evolution: str | None = None,
    evolution_base_url: str = "http://localhost:8080",
) -> ConversationOrchestrator:
    return ConversationOrchestrator(
        claude_client=ClaudeClient(api_key=api_key_anthropic),
        memory=ConversationMemory(redis=redis_client),
        translator=JuridicalTranslator(),
        jusbrasil_client=JusbrasilClient(api_key=api_key_jusbrasil),
        cache_manager=LegalDataCacheManager(redis_client=redis_client),
        evolution_client=EvolutionClient(
            base_url=evolution_base_url,
            api_key=api_key_evolution or "",
        ),
        session_factory=session_factory,
    )


# ---------------------------------------------------------------------------
# Singleton por processo — apenas componentes 100% síncronos
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
        try:
            orchestrador = ConversationOrchestrator(
                claude_client=ClaudeClient(api_key=settings.ANTHROPIC_API_KEY),
                memory=ConversationMemory(redis=redis_client),
                translator=_criar_translator(),
                jusbrasil_client=JusbrasilClient(api_key=settings.JUSBRASIL_API_KEY),
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
