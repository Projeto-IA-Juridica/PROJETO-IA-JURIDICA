# feature_1_ia_personalizada/services/ai/orchestrator.py
"""
Orquestrador da IA — Cérebro do Concierge Jurídico Digital.

Fluxo LangGraph:
  classificar_intencao
    ├─ (outro) ───────────────────────────────────────► gerar_resposta → mensagem fixa (fora do escopo)
    ├─ (saudacao) ────────────────────────────────────► gerar_resposta → boas-vindas / recorrente
    └─ (status/duvida_termo/reclamacao) ─────────────► buscar_dados
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
from decimal import Decimal
from typing import Any

import structlog
from prometheus_client import Counter
from redis.asyncio import Redis
from sqlalchemy import select
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
    SYSTEM_PROMPT_SAUDACAO_RECORRENTE,
    SYSTEM_PROMPT_STATUS_PROCESSO,
    SYSTEM_PROMPT_TRADUZIR_TERMO,
)
from feature_1_ia_personalizada.services.ai.translator import JuridicalTranslator
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
from shared.config.constants import MENSAGENS_FALLBACK
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio
from shared.models.interacao import Interacao
from shared.models.processo import Processo

logger = structlog.get_logger(__name__)

_TIMEOUT_FLUXO_SEGUNDOS = (
    60.0  # guarda-chuva contra nós travados (Jusbrasil, Evolution, Claude)
)

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
    intencao: str  # status | duvida_termo | saudacao | reclamacao | outro
    dados_processo: dict | None
    resposta_ia: str | None
    resposta_verificada: str | None
    tokens_usados: dict
    erro: str | None
    tentativas_correcao: int
    usando_fallback: bool
    precisa_regenerar: bool  # sinal interno: verificar_resposta → gerar_resposta


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
    ) -> None:
        self._claude = claude_client
        self._memory = memory
        self._translator = translator
        self._jusbrasil = jusbrasil_client
        self._cache = cache_manager
        self._evolution = evolution_client
        self._session_factory = session_factory

        # FactChecker usa DB via adapter
        self._fact_checker = FactChecker(
            buscar_dados_processo=self._buscar_resumo_processo_para_fact_checker,
        )

        if _LANGGRAPH_OK:
            self._graph = self._build_graph()
            logger.info("orchestrator_iniciado", modo="langgraph")
        else:
            self._graph = None
            logger.warning(
                "orchestrator_iniciado", modo="fallback_simples_sem_langgraph"
            )

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
            "resposta_ia": None,
            "resposta_verificada": None,
            "tokens_usados": {"input": 0, "output": 0},
            "erro": None,
            "tentativas_correcao": 0,
            "usando_fallback": False,
            "precisa_regenerar": False,
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

    async def _buscar_resumo_processo_para_fact_checker(
        self, processo_id: str
    ) -> dict[str, Any]:
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
        graph.add_node("buscar_dados", self._node_buscar_dados)
        graph.add_node("gerar_resposta", self._node_gerar_resposta)
        graph.add_node("verificar_resposta", self._node_verificar_resposta)
        graph.add_node("enviar_resposta", self._node_enviar_resposta)
        graph.add_node("tratar_erro", self._node_tratar_erro)

        graph.set_entry_point("classificar_intencao")

        graph.add_conditional_edges(
            "classificar_intencao",
            self._rota_apos_classificacao,
            {
                "buscar_dados": "buscar_dados",
                "gerar_resposta": "gerar_resposta",
                "tratar_erro": "tratar_erro",
            },
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

    def _rota_apos_classificacao(self, state: ConversationState) -> str:
        if state.get("erro"):
            return "tratar_erro"
        if state.get("intencao") in (
            "status",
            "duvida_termo",
            "reclamacao",
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
        if (
            state.get("precisa_regenerar")
            and (state.get("tentativas_correcao") or 0) < 2
        ):
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
                "duvida_termo",
                "saudacao",
                "reclamacao",
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

            # Tenta cache de andamentos → Jusbrasil como fallback
            andamentos = await self._cache.get_andamentos(numero_cnj)
            if andamentos:
                log.debug("andamentos_do_cache", cnj=numero_cnj)
            else:
                andamentos = await self._jusbrasil.sincronizar_andamentos(numero_cnj)
                await self._cache.set_andamentos(numero_cnj, andamentos)
                log.info("andamentos_do_jusbrasil", cnj=numero_cnj)

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
            # para enriquecer o prompt de status sem custo extra de API
            termos_detectados = self._translator.identificar_termos_tecnicos(
                ultimo_andamento
            )
            glossario_andamento: dict[str, str] = {}
            for termo in termos_detectados:
                trad = self._translator.traduzir_termo(termo)
                if trad:
                    # Usa só a definição (antes do "\n\nExemplo:") para manter o prompt conciso
                    glossario_andamento[termo] = trad.split("\n\n")[0]

            dados_processo = {
                "processo_id": processo.id,
                "numero_cnj": numero_cnj,
                "tribunal": processo.tribunal or "N/D",
                "vara": processo.vara or "N/D",
                "polo_cliente": processo.polo_cliente or "autor",
                "ultimo_andamento": ultimo_andamento,
                "data_ultimo_andamento": data_ultimo,
                "glossario_andamento": glossario_andamento,
            }

            log.info("dados_processo_obtidos", cnj=numero_cnj)
            return {
                "processo_id": processo.id,
                "dados_processo": dados_processo,
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
                traducao_local = self._translator.traduzir_termo(
                    state["mensagem_original"]
                )
                if traducao_local:
                    log.debug("termo_traduzido_dicionario_local")
                    return {
                        "resposta_ia": traducao_local,
                        "precisa_regenerar": False,
                    }

            # Mensagem fora do escopo jurídico — resposta fixa, sem chamar Claude
            if intencao == "outro":
                log.info("intencao_fora_escopo_recusada")
                return {
                    "resposta_ia": (
                        "Estou aqui para ajudar apenas com dúvidas sobre o seu processo — "
                        "andamentos e termos jurídicos. 📋\n\n"
                        "Para outros assuntos, entre em contato diretamente com o escritório."
                    ),
                    "precisa_regenerar": False,
                }

            # Sessão única: busca escritório e cliente (sempre — nome usado em todos os prompts)
            async with self._session_factory() as session:
                escritorio, cliente = await self._obter_escritorio_cliente(
                    session, state["escritorio_id"], state["cliente_id"]
                )
            nome_escritorio = escritorio.nome if escritorio else "Escritório"
            nome_cliente = cliente.nome if cliente else "cliente"

            # Monta system_prompt baseado na intenção
            if intencao == "status" and dados:
                system_prompt = SYSTEM_PROMPT_STATUS_PROCESSO.format(
                    nome_escritorio=nome_escritorio,
                    nome_cliente=nome_cliente,
                    numero_cnj=dados.get("numero_cnj", "N/D"),
                    tribunal=dados.get("tribunal", "N/D"),
                    vara=dados.get("vara", "N/D"),
                    ultimo_andamento=dados.get(
                        "ultimo_andamento", "sem movimentação recente"
                    ),
                    data_ultimo_andamento=dados.get("data_ultimo_andamento", "N/D"),
                    polo_cliente=dados.get("polo_cliente", "N/D"),
                )
                # Injeta glossário de termos técnicos detectados no andamento.
                # Claude usa esses significados para explicar a movimentação em linguagem simples,
                # sem precisar inferir — tradução local (O(1)), zero tokens extras de inferência.
                glossario = dados.get("glossario_andamento") or {}
                if glossario:
                    linhas = "\n".join(
                        f"- {termo}: {definicao}"
                        for termo, definicao in glossario.items()
                    )
                    system_prompt += (
                        f"\n\n<glossario_termos>\n{linhas}\n</glossario_termos>"
                    )
            elif intencao == "duvida_termo":
                system_prompt = SYSTEM_PROMPT_TRADUZIR_TERMO.format(
                    nome_escritorio=nome_escritorio,
                    nome_cliente=nome_cliente,
                )
            elif intencao == "saudacao":
                cliente_recorrente = len(state.get("historico", [])) > 0
                if cliente_recorrente:
                    system_prompt = SYSTEM_PROMPT_SAUDACAO_RECORRENTE.format(
                        nome_escritorio=nome_escritorio,
                        nome_cliente=nome_cliente,
                    )
                else:
                    system_prompt = SYSTEM_PROMPT_BOAS_VINDAS.format(
                        nome_escritorio=nome_escritorio,
                        nome_cliente=nome_cliente,
                    )
            else:
                system_prompt = SYSTEM_PROMPT_BASE.format(
                    nome_escritorio=nome_escritorio,
                    nome_cliente=nome_cliente,
                )

            resultado = await self._claude.enviar_mensagem(
                system_prompt=system_prompt,
                mensagens_historico=state.get("historico", []),
                mensagem_usuario=state["mensagem_original"],
                intencao=intencao,
            )

            tokens_anteriores = state.get("tokens_usados") or {"input": 0, "output": 0}
            custo_anterior = Decimal(tokens_anteriores.get("custo_str", "0"))
            tokens_atualizados = {
                "input": tokens_anteriores.get("input", 0) + resultado["tokens_input"],
                "output": tokens_anteriores.get("output", 0)
                + resultado["tokens_output"],
                # custo_str preserva o Decimal calculado pelo ClaudeClient (sem aritmética float)
                "custo_str": str(custo_anterior + resultado["custo"]),
            }

            log.info("resposta_gerada", tokens=tokens_atualizados)
            return {
                "resposta_ia": resultado["resposta"],
                "tokens_usados": tokens_atualizados,
                "precisa_regenerar": False,
            }

        except RuntimeError as exc:
            # Claude indisponível → ativar fallback com mensagem pré-definida
            _erros_total.labels(no="gerar_resposta").inc()
            log.error("claude_indisponivel_ativando_fallback", erro=str(exc))

            intencao = state.get("intencao", "outro")
            dados = state.get("dados_processo") or {}

            if intencao == "status":
                numero = dados.get("numero_cnj", "seu processo")
                fallback_msg = (
                    f"Recebemos sua mensagem sobre o processo {numero}. "
                    "No momento estou com dificuldades técnicas, "
                    "mas o escritório retornará em breve."
                )
            elif intencao == "duvida_termo":
                fallback_msg = (
                    "Obrigado pela pergunta! Estou com uma dificuldade técnica temporária. "
                    "Encaminhei sua dúvida ao escritório."
                )
            elif intencao == "saudacao":
                fallback_msg = (
                    "Olá! No momento estou passando por uma manutenção rápida. "
                    "O escritório entrará em contato em breve."
                )
            else:
                fallback_msg = MENSAGENS_FALLBACK.get(
                    "indisponivel", TEMPLATE_ERRO_GENERICO
                )

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

            # 1. Filtrar linguagem proibida (pareceres, promessas de resultado)
            resposta_filtrada = self._fact_checker.filtrar_resposta(
                resposta_ia=resposta,
                interacao=stub,
                adicionar_disclaimer=True,
            )

            # 2. Verificar factualidade quando há dados de processo
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
                        # Esgotou as tentativas → usa fallback genérico
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
            # Não bloqueia o fluxo — passa a resposta sem verificação
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
            state.get("resposta_verificada")
            or state.get("resposta_ia")
            or TEMPLATE_ERRO_GENERICO
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

                # Envia via Evolution API (WhatsApp)
                instance = escritorio.webhook_whatsapp_instance
                numero = cliente.telefone_whatsapp

                if instance and numero:
                    try:
                        await self._evolution.enviar_texto(
                            instance, numero, resposta_final
                        )
                        log.info(
                            "mensagem_enviada_whatsapp",
                            numero_parcial=numero[:4] + "***",
                        )
                    except Exception as exc_wa:
                        # Falha no envio WhatsApp não interrompe o fluxo — só loga
                        log.warning("falha_envio_whatsapp", erro=str(exc_wa))
                else:
                    log.warning(
                        "instancia_ou_numero_ausente",
                        instance=instance,
                        numero=bool(numero),
                    )

                # Atualiza memória de conversa no Redis
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

                # Persiste Interação no banco (custo vem do ClaudeClient, sem recálculo)
                await self._salvar_interacao(
                    session, state, resposta_final, tokens, custo
                )

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

                # Tenta enviar mensagem de erro ao cliente
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

                # Persiste interação com metadata de erro para auditoria.
                # Nota: traceback.format_exc() só é confiável dentro de um bloco except ativo.
                # O erro de origem já está capturado em state["erro"] — suficiente para auditoria.
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

        # Nó 2: buscar dados (se intencão exige processo)
        if state["intencao"] in ("status", "duvida_termo", "reclamacao"):
            state.update(await self._node_buscar_dados(state))  # type: ignore[typeddict-item]
            if state.get("erro"):
                await self._node_tratar_erro(state)
                return state  # type: ignore[return-value]
            # Sem processos → resposta já definida em resposta_verificada
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
            # Re-gera com contexto de correção
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
    """
    Instancia e configura o ConversationOrchestrator com todas as dependências.

    Exemplo (Celery worker ou FastAPI lifespan):

        from shared.config.settings import settings
        from shared.database.connection import async_session_factory
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(settings.REDIS_URL)
        orchestrador = criar_orchestrador(
            api_key_anthropic=settings.ANTHROPIC_API_KEY,
            redis_client=redis_client,
            session_factory=async_session_factory,
            api_key_jusbrasil=settings.JUSBRASIL_API_KEY,
            api_key_evolution=settings.EVOLUTION_API_KEY,
            evolution_base_url=settings.EVOLUTION_API_URL,
        )
    """
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
#
# ⚠️  Por que NÃO singletonizar clientes assíncronos (Redis, Claude, Evolution)?
#
#   asyncio.run() cria um novo event loop a cada chamada e o destrói ao final.
#   Clientes assíncronos (redis.asyncio, httpx, aiohttp) atrelam seus pools de
#   conexão ao loop em que foram criados/usados pela primeira vez.
#   Na segunda task do Celery o asyncio.run() cria um novo loop, mas o singleton
#   tenta operar conexões do loop anterior (já destruído):
#       RuntimeError: Event loop is closed
#
#   Solução: singletonizar apenas o JuridicalTranslator (puro dict em memória,
#   zero I/O assíncrono). Todos os clientes assíncronos são instanciados dentro
#   do asyncio.run() de cada task — o custo é irrelevante (apenas atribuição de
#   strings/referências, sem conexões de rede no __init__).

_translator_singleton: JuridicalTranslator | None = None


def _criar_translator() -> JuridicalTranslator:
    """Retorna o singleton se disponível, cria novo caso contrário (testes/scripts)."""
    return (
        _translator_singleton
        if _translator_singleton is not None
        else JuridicalTranslator()
    )


def inicializar_orchestrador_worker() -> None:
    """
    Inicializa o JuridicalTranslator uma única vez por processo worker Celery.

    O tradutor carrega o JSON de termos jurídicos em memória (operação de disco,
    ~ms) — é o único componente cujo custo de inicialização justifica singletonizar.

    Deve ser chamado no sinal `worker_process_init` do Celery:

        from celery.signals import worker_process_init

        @worker_process_init.connect
        def init_worker(**kwargs):
            from feature_1_ia_personalizada.services.ai.orchestrator import (
                inicializar_orchestrador_worker,
            )
            inicializar_orchestrador_worker()
    """
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
    """
    Entry point síncrono chamado pelos workers Celery.

    Todos os clientes assíncronos (Redis, Claude, Evolution) são criados dentro do
    asyncio.run() e destruídos ao final — garantindo que vivam no mesmo event loop.
    Apenas o JuridicalTranslator (puro dict em memória) é reaproveitado via singleton
    quando `inicializar_orchestrador_worker()` foi chamado no worker_process_init.

    Returns:
        {"resposta": str, "intencao": str, "usando_fallback": bool, ...}
    """
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
            return await orchestrador.processar(
                id_escritorio, id_cliente, mensagem, tipo
            )
        finally:
            await redis_client.close()

    return asyncio.run(_run())
