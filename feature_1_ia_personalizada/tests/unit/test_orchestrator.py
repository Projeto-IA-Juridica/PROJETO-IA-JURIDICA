# feature_1_ia_personalizada/tests/unit/test_orchestrator.py
"""
Testes do ConversationOrchestrator: 6 nós, funções de roteamento, glossário de termos
jurídicos, singleton do JuridicalTranslator e entry-point Celery.

Estratégia geral:
  - Todas as dependências externas (Claude, Redis, Evolution, DB) são mockadas.
  - LangGraph é desabilitado via patch(_LANGGRAPH_OK=False) para testar o
    fluxo sequencial, que é equivalente ao grafo.
  - Cada classe de teste foca em um único nó ou responsabilidade.

Nota sobre async:
  Os métodos `async def test_*` rodam sem @pytest.mark.asyncio explícito porque
  o pyproject.toml define `asyncio_mode = "auto"` (pytest-asyncio >= 0.21).
  Se o projeto migrar para asyncio_mode = "strict", adicionar o decorator em
  cada método async ou usar @pytest.mark.asyncio no nível da classe.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import feature_1_ia_personalizada.services.ai.orchestrator as orq_module
from feature_1_ia_personalizada.services.ai.orchestrator import (
    ConversationOrchestrator,
    ConversationState,
    _classificar_por_keywords,
    _criar_translator,
    executar_fluxo_orquestrador,
    inicializar_orchestrador_worker,
)
from feature_1_ia_personalizada.services.messaging.templates import (
    TEMPLATE_CLIENTE_SEM_PROCESSO,
    TEMPLATE_ERRO_GENERICO,
)
from shared.config.constants import MENSAGENS_FALLBACK

# ---------------------------------------------------------------------------
# Entidades de banco simuladas
# ---------------------------------------------------------------------------


class _Processo:
    id = 1
    numero_cnj = "1234567-89.2023.8.26.0100"
    tribunal = "TJSP"
    vara = "3ª Vara Cível"
    polo_cliente = "autor"
    monitoramento_ativo = True
    ultimo_andamento = "Audiência agendada para 10/02/2025."
    data_ultimo_andamento = None
    cliente_id = 1
    escritorio_id = 1


class _Escritorio:
    id = 1
    nome = "Escritório Advocacia Teste"
    webhook_whatsapp_instance = "inst-abc"


class _Cliente:
    id = 1
    nome = "Maria Oliveira"
    telefone_whatsapp = "5511999990001"
    escritorio_id = 1


# ---------------------------------------------------------------------------
# Helpers de mock de sessão SQLAlchemy
# ---------------------------------------------------------------------------

# Sentinel: distingue "não fornecido" de "explicitamente None".
# Necessário porque _make_session(escritorio=None) deve passar None para a sessão
# (simulando entidade não encontrada no banco), não usar o default _Escritorio().
_UNSET = object()


def _make_session(
    processos=_UNSET,
    escritorio=_UNSET,
    cliente=_UNSET,
) -> AsyncMock:
    """Retorna um mock de sessão assíncrona que simula Escritorio, Cliente e Processo."""
    if escritorio is _UNSET:
        escritorio = _Escritorio()
    if cliente is _UNSET:
        cliente = _Cliente()
    if processos is _UNSET:
        processos = [_Processo()]

    session = AsyncMock()

    async def _get(model_class, pk):
        name = model_class.__name__
        if name == "Escritorio":
            return escritorio
        if name == "Cliente":
            return cliente
        if name == "Processo":
            # Retorna o primeiro processo da lista (usado por _buscar_resumo_processo_para_fact_checker)
            return processos[0] if processos else None
        return None

    session.get = AsyncMock(side_effect=_get)  # type: ignore[method-assign]

    scalars = MagicMock()
    scalars.all.return_value = processos
    result = MagicMock()
    result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()  # type: ignore[method-assign]
    session.refresh = AsyncMock()  # type: ignore[method-assign]
    return session


def _session_factory_from(session: AsyncMock):
    """Envolve a sessão num context-manager callable (async with factory() as s)."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


# ---------------------------------------------------------------------------
# Helpers de mock de dependências
# ---------------------------------------------------------------------------


def _mock_claude(
    resposta: str = "Resposta da IA.",
    tokens_in: int = 100,
    tokens_out: int = 50,
) -> MagicMock:
    c = MagicMock()
    c.enviar_mensagem = AsyncMock(
        return_value={
            "resposta": resposta,
            "tokens_input": tokens_in,
            "tokens_output": tokens_out,
            "custo": Decimal("0.005"),
        }
    )
    c.classificar_intencao = AsyncMock(return_value='{"intencao": "status"}')
    return c


def _mock_translator(
    termos: list[str] | None = None,
    traducoes: dict | None = None,
) -> MagicMock:
    t = MagicMock()
    t.identificar_termos_tecnicos = MagicMock(return_value=termos or [])
    t.traduzir_termo = MagicMock(side_effect=lambda termo: (traducoes or {}).get(termo))
    t.total_termos = len(traducoes or {})
    t.dicionario_disponivel = True
    return t


def _mock_cache(andamentos=None) -> MagicMock:
    c = MagicMock()
    c.get_andamentos = AsyncMock(return_value=andamentos)
    c.set_andamentos = AsyncMock()
    return c


def _mock_jusbrasil(andamentos=None) -> MagicMock:
    j = MagicMock()
    default = [{"descricao": "Despacho proferido.", "data": "2024-06-01T10:00:00"}]
    j.sincronizar_andamentos = AsyncMock(
        return_value=andamentos if andamentos is not None else default
    )
    return j


def _mock_evolution() -> MagicMock:
    e = MagicMock()
    e.enviar_texto = AsyncMock()
    return e


def _mock_memory() -> MagicMock:
    m = MagicMock()
    m.buscar_historico = AsyncMock(return_value=[])
    m.salvar_mensagem = AsyncMock()
    return m


# ---------------------------------------------------------------------------
# Fábrica central de orquestradores mockados
# ---------------------------------------------------------------------------


def _make_orchestrator(
    session: AsyncMock | None = None,
    processos=_UNSET,
    escritorio=_UNSET,
    cliente=_UNSET,
    claude: MagicMock | None = None,
    translator: MagicMock | None = None,
    cache: MagicMock | None = None,
    jusbrasil: MagicMock | None = None,
    evolution: MagicMock | None = None,
    memory: MagicMock | None = None,
) -> ConversationOrchestrator:
    """Cria um ConversationOrchestrator com todas as dependências mockadas."""
    if session is None:
        session = _make_session(processos=processos, escritorio=escritorio, cliente=cliente)
    with patch("feature_1_ia_personalizada.services.ai.orchestrator._LANGGRAPH_OK", False):
        orq = ConversationOrchestrator(
            claude_client=claude or _mock_claude(),
            memory=memory or _mock_memory(),
            translator=translator or _mock_translator(),
            jusbrasil_client=jusbrasil or _mock_jusbrasil(),
            cache_manager=cache or _mock_cache(andamentos=None),
            evolution_client=evolution or _mock_evolution(),
            session_factory=_session_factory_from(session),
        )
    return orq


def _base_state(**overrides) -> ConversationState:
    """ConversationState mínimo válido para usar nos testes."""
    state: ConversationState = {
        "escritorio_id": 1,
        "cliente_id": 1,
        "processo_id": None,
        "mensagem_original": "Qual o status do meu processo?",
        "tipo_mensagem": "texto",
        "historico": [],
        "intencao": "status",
        "dados_processo": None,
        "resposta_ia": None,
        "resposta_verificada": None,
        "tokens_usados": {"input": 0, "output": 0},
        "erro": None,
        "tentativas_correcao": 0,
        "usando_fallback": False,
        "precisa_regenerar": False,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


# ---------------------------------------------------------------------------
# TestClassificarPorKeywords — função pura
# ---------------------------------------------------------------------------


class TestClassificarPorKeywords:
    def test_status(self):
        assert _classificar_por_keywords("qual o andamento do processo?") == "status"

    def test_duvida_termo(self):
        assert _classificar_por_keywords("o que significa agravo?") == "duvida_termo"

    def test_agendamento_retorna_outro(self):
        assert _classificar_por_keywords("quero agendar uma consulta") == "outro"

    def test_saudacao(self):
        assert _classificar_por_keywords("olá, bom dia!") == "saudacao"

    def test_reclamacao(self):
        assert _classificar_por_keywords("estou insatisfeito com a demora") == "reclamacao"

    def test_mensagem_sem_keywords_retorna_outro(self):
        assert _classificar_por_keywords("aaaaa bbbbb") == "outro"

    def test_case_insensitive(self):
        assert _classificar_por_keywords("STATUS DO MEU PROCESSO") == "status"


# ---------------------------------------------------------------------------
# TestNodeClassificarIntencao
# ---------------------------------------------------------------------------


class TestNodeClassificarIntencao:
    async def test_sucesso_retorna_intencao_do_claude(self):
        claude = _mock_claude()
        claude.classificar_intencao = AsyncMock(return_value='{"intencao": "reclamacao"}')
        orq = _make_orchestrator(claude=claude)
        result = await orq._node_classificar_intencao(_base_state())
        assert result["intencao"] == "reclamacao"

    async def test_json_invalido_usa_keywords_como_fallback(self):
        claude = _mock_claude()
        claude.classificar_intencao = AsyncMock(return_value="não é json válido")
        orq = _make_orchestrator(claude=claude)
        state = _base_state(mensagem_original="qual o status do processo?")
        result = await orq._node_classificar_intencao(state)
        assert result["intencao"] == "status"

    async def test_excecao_no_claude_usa_keywords_como_fallback(self):
        claude = _mock_claude()
        claude.classificar_intencao = AsyncMock(side_effect=RuntimeError("API offline"))
        orq = _make_orchestrator(claude=claude)
        state = _base_state(mensagem_original="oi, bom dia")
        result = await orq._node_classificar_intencao(state)
        assert result["intencao"] == "saudacao"

    async def test_intencao_desconhecida_normalizada_para_outro(self):
        claude = _mock_claude()
        claude.classificar_intencao = AsyncMock(return_value='{"intencao": "xpto_invalido"}')
        orq = _make_orchestrator(claude=claude)
        result = await orq._node_classificar_intencao(_base_state())
        assert result["intencao"] == "outro"

    async def test_todas_intencoes_validas_aceitas(self):
        for intencao in (
            "status",
            "duvida_termo",
            "saudacao",
            "reclamacao",
            "outro",
        ):
            claude = _mock_claude()
            claude.classificar_intencao = AsyncMock(return_value=f'{{"intencao": "{intencao}"}}')
            orq = _make_orchestrator(claude=claude)
            result = await orq._node_classificar_intencao(_base_state())
            assert result["intencao"] == intencao


# ---------------------------------------------------------------------------
# TestNodeBuscarDados
# ---------------------------------------------------------------------------


class TestNodeBuscarDados:
    async def test_sem_processos_retorna_template_cliente_sem_processo(self):
        session = _make_session(processos=[])
        orq = _make_orchestrator(session=session)
        result = await orq._node_buscar_dados(_base_state())
        assert result.get("resposta_verificada") == TEMPLATE_CLIENTE_SEM_PROCESSO
        assert not result.get("dados_processo")

    async def test_com_processo_retorna_dados_corretos(self):
        orq = _make_orchestrator(cache=_mock_cache(andamentos=None))
        result = await orq._node_buscar_dados(_base_state())
        dados = result["dados_processo"]
        assert dados["numero_cnj"] == "1234567-89.2023.8.26.0100"
        assert dados["tribunal"] == "TJSP"
        assert result["processo_id"] == 1

    async def test_cache_hit_nao_chama_jusbrasil(self):
        andamentos_cache = [{"descricao": "Andamento do cache.", "data": "2024-01-01"}]
        cache = _mock_cache(andamentos=andamentos_cache)
        jusbrasil = _mock_jusbrasil()
        orq = _make_orchestrator(cache=cache, jusbrasil=jusbrasil)
        result = await orq._node_buscar_dados(_base_state())
        jusbrasil.sincronizar_andamentos.assert_not_called()
        assert result["dados_processo"]["ultimo_andamento"] == "Andamento do cache."

    async def test_cache_miss_chama_jusbrasil_e_salva_cache(self):
        cache = _mock_cache(andamentos=None)
        jusbrasil = _mock_jusbrasil([{"descricao": "Despacho judicial.", "data": "2024-06-01"}])
        orq = _make_orchestrator(cache=cache, jusbrasil=jusbrasil)
        result = await orq._node_buscar_dados(_base_state())
        jusbrasil.sincronizar_andamentos.assert_called_once()
        cache.set_andamentos.assert_called_once()
        assert result["dados_processo"]["ultimo_andamento"] == "Despacho judicial."

    async def test_andamentos_vazios_usa_ultimo_andamento_do_banco(self):
        """Jusbrasil retorna lista vazia → usa processo.ultimo_andamento do banco."""
        cache = _mock_cache(andamentos=None)
        jusbrasil = _mock_jusbrasil(andamentos=[])
        orq = _make_orchestrator(cache=cache, jusbrasil=jusbrasil)
        result = await orq._node_buscar_dados(_base_state())
        # _Processo.ultimo_andamento = "Audiência agendada para 10/02/2025."
        assert result["dados_processo"]["ultimo_andamento"] == "Audiência agendada para 10/02/2025."

    async def test_excecao_retorna_chave_erro(self):
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(side_effect=RuntimeError("DB offline"))
        cm.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=cm)
        with patch("feature_1_ia_personalizada.services.ai.orchestrator._LANGGRAPH_OK", False):
            orq = ConversationOrchestrator(
                claude_client=_mock_claude(),
                memory=_mock_memory(),
                translator=_mock_translator(),
                jusbrasil_client=_mock_jusbrasil(),
                cache_manager=_mock_cache(),
                evolution_client=_mock_evolution(),
                session_factory=factory,
            )
        result = await orq._node_buscar_dados(_base_state())
        assert "erro" in result and "buscar_dados" in result["erro"]

    async def test_glossario_vazio_quando_nenhum_termo_detectado(self):
        translator = _mock_translator(termos=[])
        orq = _make_orchestrator(translator=translator)
        result = await orq._node_buscar_dados(_base_state())
        assert result["dados_processo"]["glossario_andamento"] == {}

    async def test_glossario_preenchido_com_termos_detectados(self):
        traducoes = {
            "despacho": "Decisão judicial de mero expediente.\n\nExemplo: Cite-se o réu.",
            "tutela": "Medida judicial protetiva.",
        }
        translator = _mock_translator(termos=["despacho", "tutela"], traducoes=traducoes)
        andamentos = [
            {
                "descricao": "Despacho concedendo tutela antecipada.",
                "data": "2024-06-01",
            }
        ]
        orq = _make_orchestrator(translator=translator, cache=_mock_cache(andamentos=andamentos))
        result = await orq._node_buscar_dados(_base_state())
        glossario = result["dados_processo"]["glossario_andamento"]
        assert "despacho" in glossario
        assert "tutela" in glossario

    async def test_glossario_nao_inclui_exemplo_na_definicao(self):
        """Somente a definição (antes de '\\n\\nExemplo:') deve ir para o glossário."""
        traducoes = {
            "sentença": "Decisão final do juiz no processo.\n\nExemplo: Sentença de procedência.",
        }
        translator = _mock_translator(termos=["sentença"], traducoes=traducoes)
        orq = _make_orchestrator(translator=translator)
        result = await orq._node_buscar_dados(_base_state())
        definicao = result["dados_processo"]["glossario_andamento"]["sentença"]
        assert "Exemplo:" not in definicao
        assert definicao == "Decisão final do juiz no processo."

    async def test_termo_sem_traducao_nao_incluido_no_glossario(self):
        """Termo detectado mas sem entrada no dicionário é ignorado silenciosamente."""
        translator = _mock_translator(termos=["xpto_desconhecido"])
        translator.traduzir_termo = MagicMock(return_value=None)
        orq = _make_orchestrator(translator=translator)
        result = await orq._node_buscar_dados(_base_state())
        assert result["dados_processo"]["glossario_andamento"] == {}


# ---------------------------------------------------------------------------
# TestNodeGerarResposta
# ---------------------------------------------------------------------------


class TestNodeGerarResposta:
    async def test_duvida_termo_com_traducao_local_nao_chama_claude(self):
        translator = _mock_translator()
        translator.traduzir_termo = MagicMock(return_value="Recurso para questões processuais.")
        claude = _mock_claude()
        orq = _make_orchestrator(claude=claude, translator=translator)
        state = _base_state(intencao="duvida_termo", mensagem_original="o que é agravo?")
        result = await orq._node_gerar_resposta(state)
        claude.enviar_mensagem.assert_not_called()
        assert result["resposta_ia"] == "Recurso para questões processuais."
        # Garante que o código passa mensagem_original para traduzir_termo (não termo isolado)
        translator.traduzir_termo.assert_called_once_with("o que é agravo?")

    async def test_duvida_termo_sem_traducao_local_chama_claude(self):
        translator = _mock_translator()
        translator.traduzir_termo = MagicMock(return_value=None)
        claude = _mock_claude("Agravo é um recurso judicial.")
        orq = _make_orchestrator(claude=claude, translator=translator)
        state = _base_state(intencao="duvida_termo", mensagem_original="o que é agravo?")
        result = await orq._node_gerar_resposta(state)
        claude.enviar_mensagem.assert_called_once()
        assert result["resposta_ia"] == "Agravo é um recurso judicial."

    async def test_status_sem_glossario_nao_injeta_bloco_xml(self):
        dados = {
            "numero_cnj": "0001-00.2024.8.26.0100",
            "tribunal": "TJSP",
            "vara": "1ª Vara",
            "polo_cliente": "autor",
            "ultimo_andamento": "Processo em análise.",
            "data_ultimo_andamento": "2024-06-01",
            "glossario_andamento": {},
        }
        claude = _mock_claude()
        orq = _make_orchestrator(claude=claude)
        await orq._node_gerar_resposta(_base_state(intencao="status", dados_processo=dados))
        prompt = claude.enviar_mensagem.call_args.kwargs["system_prompt"]
        assert "<glossario_termos>" not in prompt

    async def test_status_com_glossario_injeta_bloco_xml_no_prompt(self):
        dados = {
            "numero_cnj": "0001-00.2024.8.26.0100",
            "tribunal": "TJSP",
            "vara": "1ª Vara",
            "polo_cliente": "autor",
            "ultimo_andamento": "Despacho proferido.",
            "data_ultimo_andamento": "2024-06-01",
            "glossario_andamento": {"despacho": "Decisão do juiz"},
        }
        claude = _mock_claude()
        orq = _make_orchestrator(claude=claude)
        await orq._node_gerar_resposta(_base_state(intencao="status", dados_processo=dados))
        prompt = claude.enviar_mensagem.call_args.kwargs["system_prompt"]
        assert "<glossario_termos>" in prompt
        assert "- despacho: Decisão do juiz" in prompt
        assert "</glossario_termos>" in prompt

    async def test_status_com_multiplos_termos_no_glossario(self):
        dados = {
            "numero_cnj": "0001-00",
            "tribunal": "TJSP",
            "vara": "1ª Vara",
            "polo_cliente": "autor",
            "ultimo_andamento": "x",
            "data_ultimo_andamento": "2024-06-01",
            "glossario_andamento": {
                "despacho": "Decisão do juiz",
                "tutela": "Medida protetiva",
                "sentença": "Decisão final",
            },
        }
        claude = _mock_claude()
        orq = _make_orchestrator(claude=claude)
        await orq._node_gerar_resposta(_base_state(intencao="status", dados_processo=dados))
        prompt = claude.enviar_mensagem.call_args.kwargs["system_prompt"]
        assert "- despacho: Decisão do juiz" in prompt
        assert "- tutela: Medida protetiva" in prompt
        assert "- sentença: Decisão final" in prompt

    async def test_saudacao_inclui_nome_cliente_no_prompt(self):
        cliente = _Cliente()
        cliente.nome = "Pedro Alves"
        session = _make_session(cliente=cliente)
        claude = _mock_claude()
        orq = _make_orchestrator(session=session, claude=claude)
        await orq._node_gerar_resposta(_base_state(intencao="saudacao"))
        prompt = claude.enviar_mensagem.call_args.kwargs["system_prompt"]
        assert "Pedro Alves" in prompt

    async def test_status_busca_escritorio_e_cliente(self):
        """Para 'status', session.get deve ser chamado para Escritorio e Cliente."""
        from shared.models.cliente import Cliente as ClienteModel
        from shared.models.escritorio import Escritorio as EscritorioModel

        session = _make_session()
        claude = _mock_claude()
        dados = {
            "numero_cnj": "0001",
            "tribunal": "TJSP",
            "vara": "1ª",
            "polo_cliente": "autor",
            "ultimo_andamento": "x",
            "data_ultimo_andamento": "2024",
            "glossario_andamento": {},
        }
        orq = _make_orchestrator(session=session, claude=claude)
        await orq._node_gerar_resposta(_base_state(intencao="status", dados_processo=dados))
        # Ambos são buscados para montar o prompt (nome_escritorio + nome_cliente)
        classes_consultadas = {c.args[0] for c in session.get.call_args_list if c.args}
        assert EscritorioModel in classes_consultadas
        assert ClienteModel in classes_consultadas

    async def test_tokens_acumulados_corretamente(self):
        claude = _mock_claude()
        claude.enviar_mensagem = AsyncMock(
            return_value={
                "resposta": "ok",
                "tokens_input": 200,
                "tokens_output": 80,
                "custo": Decimal("0.010"),
            }
        )
        orq = _make_orchestrator(claude=claude)
        state = _base_state(tokens_usados={"input": 50, "output": 20, "custo_str": "0.002"})
        result = await orq._node_gerar_resposta(state)
        tokens = result["tokens_usados"]
        assert tokens["input"] == 250
        assert tokens["output"] == 100
        assert Decimal(tokens["custo_str"]) == Decimal("0.012")

    async def test_custo_str_preserva_precisao_decimal(self):
        """Acúmulo de custo não deve sofrer perda de precisão float."""
        claude = _mock_claude()
        claude.enviar_mensagem = AsyncMock(
            return_value={
                "resposta": "ok",
                "tokens_input": 1,
                "tokens_output": 1,
                "custo": Decimal("0.000015"),
            }
        )
        orq = _make_orchestrator(claude=claude)
        state = _base_state(tokens_usados={"input": 0, "output": 0, "custo_str": "0.000003"})
        result = await orq._node_gerar_resposta(state)
        assert Decimal(result["tokens_usados"]["custo_str"]) == Decimal("0.000018")

    async def test_runtime_error_do_claude_ativa_fallback_sem_erro(self):
        claude = _mock_claude()
        claude.enviar_mensagem = AsyncMock(side_effect=RuntimeError("Claude indisponível"))
        orq = _make_orchestrator(claude=claude)
        result = await orq._node_gerar_resposta(_base_state(intencao="status"))
        assert result.get("usando_fallback") is True
        assert result.get("erro") is None
        assert result["resposta_ia"]

    async def test_fallback_de_status_menciona_numero_cnj(self):
        """Mensagem de fallback para status deve referenciar o processo."""
        claude = _mock_claude()
        claude.enviar_mensagem = AsyncMock(side_effect=RuntimeError("offline"))
        dados = {
            "numero_cnj": "9999-TESTE",
            "tribunal": "TJSP",
            "vara": "1ª",
            "polo_cliente": "autor",
            "ultimo_andamento": "x",
            "data_ultimo_andamento": "2024",
            "glossario_andamento": {},
        }
        orq = _make_orchestrator(claude=claude)
        result = await orq._node_gerar_resposta(
            _base_state(intencao="status", dados_processo=dados)
        )
        assert "9999-TESTE" in result["resposta_ia"]

    async def test_excecao_inesperada_retorna_chave_erro(self):
        claude = _mock_claude()
        claude.enviar_mensagem = AsyncMock(side_effect=ValueError("bug inesperado"))
        orq = _make_orchestrator(claude=claude)
        result = await orq._node_gerar_resposta(_base_state())
        assert "erro" in result and "gerar_resposta" in result["erro"]

    async def test_precisa_regenerar_false_na_resposta_normal(self):
        orq = _make_orchestrator()
        result = await orq._node_gerar_resposta(_base_state())
        assert result["precisa_regenerar"] is False


# ---------------------------------------------------------------------------
# TestNodeVerificarResposta
# ---------------------------------------------------------------------------


class TestNodeVerificarResposta:
    async def test_fallback_ativo_pula_verificacao_inteira(self):
        orq = _make_orchestrator()
        state = _base_state(resposta_ia="Fallback pronto.", usando_fallback=True)
        result = await orq._node_verificar_resposta(state)
        assert result["resposta_verificada"] == "Fallback pronto."
        assert result["precisa_regenerar"] is False

    async def test_resposta_vazia_retorna_erro(self):
        orq = _make_orchestrator()
        state = _base_state(resposta_ia="", usando_fallback=False)
        result = await orq._node_verificar_resposta(state)
        assert "erro" in result and "resposta_vazia" in result["erro"]

    async def test_filtrar_resposta_chamado_e_resultado_usado(self):
        """
        O orchestrator deve chamar filtrar_resposta e usar o texto que ela retorna.
        O FactChecker é mockado — a correção da linguagem em si é testada em test_fact_checker.py.
        """
        orq = _make_orchestrator()
        orq._fact_checker = MagicMock()
        orq._fact_checker.filtrar_resposta = MagicMock(
            return_value="Texto já filtrado pelo FactChecker."
        )
        state = _base_state(resposta_ia="Resposta original da IA.", usando_fallback=False)
        result = await orq._node_verificar_resposta(state)
        orq._fact_checker.filtrar_resposta.assert_called_once()
        assert result["resposta_verificada"] == "Texto já filtrado pelo FactChecker."

    async def test_sem_dados_processo_nao_executa_fact_check(self):
        orq = _make_orchestrator()
        state = _base_state(
            resposta_ia="Resposta segura.",
            dados_processo=None,
            processo_id=None,
            usando_fallback=False,
        )
        result = await orq._node_verificar_resposta(state)
        assert result.get("precisa_regenerar") is False
        assert result.get("resposta_verificada")

    async def test_fact_check_ok_nao_pede_regeneracao(self):
        """Quando FactChecker verifica tudo correto, precisa_regenerar=False."""

        async def _buscar_ok(pid):
            return {
                "numero_cnj": "1234567-89.2023.8.26.0100",
                "tribunal": "TJSP",
                "ultimo_andamento": "Audiência agendada",
            }

        from feature_1_ia_personalizada.services.ai.fact_checker import FactChecker

        orq = _make_orchestrator()
        orq._fact_checker = FactChecker(buscar_dados_processo=_buscar_ok)
        state = _base_state(
            resposta_ia=(
                "O processo 1234567-89.2023.8.26.0100 está no TJSP. "
                "Audiência agendada é o último andamento."
            ),
            dados_processo={
                "numero_cnj": "1234567-89.2023.8.26.0100",
                "tribunal": "TJSP",
            },
            processo_id=1,
            tentativas_correcao=0,
            usando_fallback=False,
        )
        result = await orq._node_verificar_resposta(state)
        assert result["precisa_regenerar"] is False

    async def test_fact_check_divergencia_com_0_tentativas_pede_regeneracao(self):
        async def _buscar_divergente(pid):
            return {
                "numero_cnj": "CNJ-REAL",
                "tribunal": "TJRJ",
                "ultimo_andamento": "Sentença.",
            }

        from feature_1_ia_personalizada.services.ai.fact_checker import FactChecker

        orq = _make_orchestrator()
        orq._fact_checker = FactChecker(buscar_dados_processo=_buscar_divergente)
        state = _base_state(
            resposta_ia="Processo no TJSP sem sentença.",
            dados_processo={"numero_cnj": "CNJ-REAL", "tribunal": "TJRJ"},
            processo_id=1,
            tentativas_correcao=0,
            usando_fallback=False,
        )
        result = await orq._node_verificar_resposta(state)
        assert result["precisa_regenerar"] is True
        assert result["tentativas_correcao"] == 1

    async def test_fact_check_divergencia_com_2_tentativas_usa_mensagem_generica(self):
        """Com tentativas_correcao=2, esgota e usa fallback genérico sem regenerar."""

        async def _buscar_divergente(pid):
            return {"numero_cnj": "CNJ-X", "tribunal": "TJSP"}

        from feature_1_ia_personalizada.services.ai.fact_checker import FactChecker

        orq = _make_orchestrator()
        orq._fact_checker = FactChecker(buscar_dados_processo=_buscar_divergente)
        state = _base_state(
            resposta_ia="Informação incorreta sem CNJ.",
            dados_processo={"numero_cnj": "CNJ-X"},
            processo_id=1,
            tentativas_correcao=2,
            usando_fallback=False,
        )
        result = await orq._node_verificar_resposta(state)
        assert result["precisa_regenerar"] is False
        assert result["resposta_verificada"] in (
            MENSAGENS_FALLBACK.get("indisponivel", TEMPLATE_ERRO_GENERICO),
            TEMPLATE_ERRO_GENERICO,
        )

    async def test_excecao_no_fact_checker_passa_resposta_sem_bloquear(self):
        """Exceção interna no FactChecker não deve interromper o fluxo."""
        orq = _make_orchestrator()
        orq._fact_checker = MagicMock()
        orq._fact_checker.filtrar_resposta = MagicMock(side_effect=RuntimeError("bug"))

        state = _base_state(resposta_ia="Resposta qualquer.", usando_fallback=False)
        result = await orq._node_verificar_resposta(state)
        # Passa a resposta original sem verificação — não seta erro
        assert result.get("resposta_verificada") == "Resposta qualquer."
        assert result.get("precisa_regenerar") is False


# ---------------------------------------------------------------------------
# TestNodeEnviarResposta
# ---------------------------------------------------------------------------


class TestNodeEnviarResposta:
    async def test_envia_mensagem_via_whatsapp(self):
        evolution = _mock_evolution()
        orq = _make_orchestrator(evolution=evolution)
        state = _base_state(
            resposta_verificada="Resposta ao cliente.",
            tokens_usados={"input": 100, "output": 50, "custo_str": "0.005"},
        )
        await orq._node_enviar_resposta(state)
        evolution.enviar_texto.assert_called_once()
        args = evolution.enviar_texto.call_args.args
        assert args[2] == "Resposta ao cliente."

    async def test_usa_resposta_ia_quando_verificada_ausente(self):
        """Se resposta_verificada for None, usa resposta_ia como fallback."""
        evolution = _mock_evolution()
        orq = _make_orchestrator(evolution=evolution)
        state = _base_state(
            resposta_verificada=None,
            resposta_ia="Resposta direta da IA.",
            tokens_usados={"input": 10, "output": 5, "custo_str": "0.001"},
        )
        await orq._node_enviar_resposta(state)
        args = evolution.enviar_texto.call_args.args
        assert args[2] == "Resposta direta da IA."

    async def test_falha_no_whatsapp_nao_interrompe_fluxo(self):
        evolution = _mock_evolution()
        evolution.enviar_texto = AsyncMock(side_effect=Exception("WhatsApp offline"))
        orq = _make_orchestrator(evolution=evolution)
        state = _base_state(
            resposta_verificada="ok",
            tokens_usados={"input": 0, "output": 0, "custo_str": "0"},
        )
        result = await orq._node_enviar_resposta(state)
        assert result.get("erro") is None

    async def test_escritorio_nao_encontrado_retorna_erro(self):
        session = _make_session(escritorio=None)
        orq = _make_orchestrator(session=session)
        state = _base_state(
            resposta_verificada="ok",
            tokens_usados={"input": 0, "output": 0, "custo_str": "0"},
        )
        result = await orq._node_enviar_resposta(state)
        assert "erro" in result and "entidade_nao_encontrada" in result["erro"]

    async def test_salva_mensagem_user_e_assistant_na_memoria(self):
        memory = _mock_memory()
        orq = _make_orchestrator(memory=memory)
        state = _base_state(
            mensagem_original="Mensagem do cliente.",
            resposta_verificada="Resposta da IA.",
            tokens_usados={"input": 10, "output": 5, "custo_str": "0.001"},
        )
        await orq._node_enviar_resposta(state)
        assert memory.salvar_mensagem.call_count == 2
        papeis = [c.args[2] for c in memory.salvar_mensagem.call_args_list]
        assert "user" in papeis
        assert "assistant" in papeis

    async def test_interacao_persistida_com_custo_decimal_exato(self):
        session = _make_session()
        orq = _make_orchestrator(session=session)
        state = _base_state(
            resposta_verificada="ok",
            tokens_usados={"input": 100, "output": 50, "custo_str": "0.00525"},
        )
        await orq._node_enviar_resposta(state)
        session.add.assert_called_once()
        interacao = session.add.call_args.args[0]
        assert interacao.custo_estimado == Decimal("0.00525")

    async def test_sem_instancia_whatsapp_nao_envia(self):
        escritorio = _Escritorio()
        escritorio.webhook_whatsapp_instance = None
        session = _make_session(escritorio=escritorio)
        evolution = _mock_evolution()
        orq = _make_orchestrator(session=session, evolution=evolution)
        state = _base_state(
            resposta_verificada="ok",
            tokens_usados={"input": 0, "output": 0, "custo_str": "0"},
        )
        await orq._node_enviar_resposta(state)
        evolution.enviar_texto.assert_not_called()

    async def test_sem_telefone_cliente_nao_envia(self):
        cliente = _Cliente()
        cliente.telefone_whatsapp = None
        session = _make_session(cliente=cliente)
        evolution = _mock_evolution()
        orq = _make_orchestrator(session=session, evolution=evolution)
        state = _base_state(
            resposta_verificada="ok",
            tokens_usados={"input": 0, "output": 0, "custo_str": "0"},
        )
        await orq._node_enviar_resposta(state)
        evolution.enviar_texto.assert_not_called()


# ---------------------------------------------------------------------------
# TestNodeTratarErro
# ---------------------------------------------------------------------------


class TestNodeTratarErro:
    async def test_envia_template_de_erro_via_whatsapp(self):
        evolution = _mock_evolution()
        orq = _make_orchestrator(evolution=evolution)
        await orq._node_tratar_erro(_base_state(erro="buscar_dados:DB offline"))
        evolution.enviar_texto.assert_called_once()
        args = evolution.enviar_texto.call_args.args
        assert args[2] == TEMPLATE_ERRO_GENERICO

    async def test_falha_no_whatsapp_nao_propaga_excecao(self):
        evolution = _mock_evolution()
        evolution.enviar_texto = AsyncMock(side_effect=Exception("WhatsApp down"))
        orq = _make_orchestrator(evolution=evolution)
        # não deve levantar exceção
        await orq._node_tratar_erro(_base_state(erro="qualquer_erro"))

    async def test_persiste_interacao_com_metadata_erro(self):
        session = _make_session()
        orq = _make_orchestrator(session=session)
        await orq._node_tratar_erro(_base_state(erro="gerar_resposta:timeout"))
        session.add.assert_called_once()
        interacao = session.add.call_args.args[0]
        assert interacao.metadata_json["erro"] is True
        assert interacao.metadata_json["tipo_erro"] == "gerar_resposta:timeout"

    async def test_custo_zero_no_registro_de_erro(self):
        session = _make_session()
        orq = _make_orchestrator(session=session)
        await orq._node_tratar_erro(_base_state(erro="erro_teste"))
        interacao = session.add.call_args.args[0]
        assert interacao.custo_estimado == Decimal("0")

    async def test_retorna_usando_fallback_true(self):
        orq = _make_orchestrator()
        result = await orq._node_tratar_erro(_base_state(erro="any"))
        assert result == {"usando_fallback": True}

    async def test_sem_entidades_nao_envia_whatsapp_mas_persiste_interacao(self):
        """
        Quando escritorio ou cliente não é encontrado no banco, o Evolution NÃO deve
        ser chamado, mas a interação de auditoria DEVE ser persistida normalmente.
        Cobre o guard `if escritorio and cliente and ...` dentro de _node_tratar_erro.
        """
        session = _make_session(escritorio=None, cliente=None)
        evolution = _mock_evolution()
        orq = _make_orchestrator(session=session, evolution=evolution)
        result = await orq._node_tratar_erro(_base_state(erro="buscar_dados:DB offline"))
        evolution.enviar_texto.assert_not_called()
        session.add.assert_called_once()
        assert result == {"usando_fallback": True}

    async def test_falha_total_no_db_nao_propaga_excecao(self):
        """
        Quando a sessão do banco falha dentro de _node_tratar_erro (ex: DB offline),
        o except interno captura o erro e o nó retorna {"usando_fallback": True}
        sem propagar exceção — fluxo nunca trava por falha no tratamento de erro.
        """
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(side_effect=RuntimeError("PG connection refused"))
        cm.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=cm)
        with patch("feature_1_ia_personalizada.services.ai.orchestrator._LANGGRAPH_OK", False):
            orq = ConversationOrchestrator(
                claude_client=_mock_claude(),
                memory=_mock_memory(),
                translator=_mock_translator(),
                jusbrasil_client=_mock_jusbrasil(),
                cache_manager=_mock_cache(),
                evolution_client=_mock_evolution(),
                session_factory=factory,
            )
        result = await orq._node_tratar_erro(_base_state(erro="qualquer_erro"))
        assert result == {"usando_fallback": True}


# ---------------------------------------------------------------------------
# TestRotas — funções de roteamento (síncronas e puras)
# ---------------------------------------------------------------------------


class TestRotas:
    def _orq(self) -> ConversationOrchestrator:
        return _make_orchestrator()

    # _rota_apos_classificacao
    def test_classificacao_status_vai_para_buscar_dados(self):
        assert (
            self._orq()._rota_apos_classificacao(_base_state(intencao="status", erro=None))
            == "buscar_dados"
        )

    def test_classificacao_duvida_termo_vai_para_buscar_dados(self):
        assert (
            self._orq()._rota_apos_classificacao(_base_state(intencao="duvida_termo", erro=None))
            == "buscar_dados"
        )

    def test_classificacao_outro_vai_para_gerar_resposta(self):
        assert (
            self._orq()._rota_apos_classificacao(_base_state(intencao="outro", erro=None))
            == "gerar_resposta"
        )

    def test_classificacao_reclamacao_vai_para_buscar_dados(self):
        assert (
            self._orq()._rota_apos_classificacao(_base_state(intencao="reclamacao", erro=None))
            == "buscar_dados"
        )

    def test_classificacao_saudacao_vai_para_gerar_resposta(self):
        assert (
            self._orq()._rota_apos_classificacao(_base_state(intencao="saudacao", erro=None))
            == "gerar_resposta"
        )

    def test_classificacao_com_erro_vai_para_tratar_erro(self):
        assert (
            self._orq()._rota_apos_classificacao(_base_state(erro="falha_claude")) == "tratar_erro"
        )

    # _rota_apos_busca_dados
    def test_busca_com_resposta_verificada_vai_para_enviar(self):
        state = _base_state(resposta_verificada="sem processos cadastrados", erro=None)
        assert self._orq()._rota_apos_busca_dados(state) == "enviar_resposta"

    def test_busca_sem_erro_vai_para_gerar_resposta(self):
        assert (
            self._orq()._rota_apos_busca_dados(_base_state(erro=None, resposta_verificada=None))
            == "gerar_resposta"
        )

    def test_busca_com_erro_vai_para_tratar_erro(self):
        assert (
            self._orq()._rota_apos_busca_dados(_base_state(erro="buscar_dados:DB offline"))
            == "tratar_erro"
        )

    # _rota_apos_gerar_resposta
    def test_gerar_sem_erro_vai_para_verificar(self):
        assert self._orq()._rota_apos_gerar_resposta(_base_state(erro=None)) == "verificar_resposta"

    def test_gerar_com_erro_vai_para_tratar_erro(self):
        assert (
            self._orq()._rota_apos_gerar_resposta(_base_state(erro="gerar_resposta:x"))
            == "tratar_erro"
        )

    # _rota_apos_verificacao — fronteira crítica: tentativas_correcao < 2
    def test_verificacao_sem_regenerar_vai_para_enviar(self):
        state = _base_state(precisa_regenerar=False, tentativas_correcao=0)
        assert self._orq()._rota_apos_verificacao(state) == "enviar_resposta"

    def test_verificacao_regenerar_com_0_tentativas_vai_para_gerar(self):
        """0 < 2 → pode regenerar."""
        state = _base_state(precisa_regenerar=True, tentativas_correcao=0)
        assert self._orq()._rota_apos_verificacao(state) == "gerar_resposta"

    def test_verificacao_regenerar_com_1_tentativa_vai_para_gerar(self):
        """1 < 2 → ainda pode regenerar."""
        state = _base_state(precisa_regenerar=True, tentativas_correcao=1)
        assert self._orq()._rota_apos_verificacao(state) == "gerar_resposta"

    def test_verificacao_regenerar_com_2_tentativas_vai_para_enviar(self):
        """2 não é < 2 → limite atingido, envia o que tiver."""
        state = _base_state(precisa_regenerar=True, tentativas_correcao=2)
        assert self._orq()._rota_apos_verificacao(state) == "enviar_resposta"

    def test_verificacao_com_erro_vai_para_tratar_erro(self):
        assert self._orq()._rota_apos_verificacao(_base_state(erro="verificar:x")) == "tratar_erro"


# ---------------------------------------------------------------------------
# TestSingletonTranslator
# ---------------------------------------------------------------------------


class TestSingletonTranslator:
    def setup_method(self):
        """Reseta o singleton antes de cada teste para isolamento."""
        orq_module._translator_singleton = None

    def teardown_method(self):
        orq_module._translator_singleton = None

    def test_sem_singleton_cria_novo_translator(self):
        with patch(
            "feature_1_ia_personalizada.services.ai.orchestrator.JuridicalTranslator"
        ) as MockT:
            MockT.return_value = MagicMock()
            t = _criar_translator()
        assert t is not None

    def test_com_singleton_retorna_o_mesmo_objeto(self):
        fake = MagicMock()
        orq_module._translator_singleton = fake
        assert _criar_translator() is fake

    def test_inicializar_worker_seta_singleton(self):
        with patch(
            "feature_1_ia_personalizada.services.ai.orchestrator.JuridicalTranslator"
        ) as MockT:
            instancia = MagicMock()
            instancia.total_termos = 50
            MockT.return_value = instancia
            inicializar_orchestrador_worker()
        assert orq_module._translator_singleton is instancia

    def test_inicializar_worker_nao_cria_clientes_async(self):
        """Worker init cria apenas JuridicalTranslator — ClaudeClient e EvolutionClient
        não devem ser instanciados (evita conexões de rede fora do event loop)."""
        with (
            patch(
                "feature_1_ia_personalizada.services.ai.orchestrator.JuridicalTranslator"
            ) as MockT,
            patch("feature_1_ia_personalizada.services.ai.orchestrator.ClaudeClient") as MockClaude,
            patch(
                "feature_1_ia_personalizada.services.ai.orchestrator.EvolutionClient"
            ) as MockEvolution,
        ):
            fake = MagicMock(total_termos=10)
            MockT.return_value = fake
            inicializar_orchestrador_worker()
        MockClaude.assert_not_called()
        MockEvolution.assert_not_called()
        MockT.assert_called_once()

    def test_criar_translator_sem_singleton_instancia_novo_a_cada_chamada(self):
        """Sem singleton, cada chamada cria uma instância nova (scripts/testes isolados)."""
        with patch(
            "feature_1_ia_personalizada.services.ai.orchestrator.JuridicalTranslator"
        ) as MockT:
            a = MagicMock()
            b = MagicMock()
            MockT.side_effect = [a, b]
            t1 = _criar_translator()
            t2 = _criar_translator()
        assert t1 is a
        assert t2 is b


# ---------------------------------------------------------------------------
# TestExecutarFluxoOrquestrador — entry-point Celery
# ---------------------------------------------------------------------------


class TestExecutarFluxoOrquestrador:
    @pytest.fixture(autouse=True)
    def _patch_db_module(self):
        """
        executar_fluxo_orquestrador faz `from shared.database.connection import ...`
        que dispara create_async_engine() → exige asyncpg (não instalado no env de testes).
        Injetamos um módulo fake em sys.modules antes de qualquer import real acontecer.
        """
        fake_db = MagicMock()
        fake_db.async_session_factory = MagicMock()
        with patch.dict(
            sys.modules,
            {
                "shared.database.connection": fake_db,
                "shared.database": fake_db,
            },
        ):
            yield

    def test_retorna_resultado_de_processar(self):
        resultado_esperado = {
            "resposta": "Seu processo está em andamento.",
            "intencao": "status",
            "usando_fallback": False,
            "tokens_usados": {"input": 100, "output": 50},
            "processo_id": 1,
        }
        with patch(
            "feature_1_ia_personalizada.services.ai.orchestrator.asyncio.run",
            return_value=resultado_esperado,
        ):
            result = executar_fluxo_orquestrador(1, 1, "status do processo?")
        assert result == resultado_esperado

    def test_chama_asyncio_run_uma_vez(self):
        with patch(
            "feature_1_ia_personalizada.services.ai.orchestrator.asyncio.run",
            return_value={},
        ) as mock_run:
            executar_fluxo_orquestrador(1, 1, "oi")
        mock_run.assert_called_once()

    def test_translator_nao_e_instanciado_no_corpo_sincrono(self):
        """
        JuridicalTranslator NÃO deve ser instanciado no corpo síncrono de
        executar_fluxo_orquestrador — só dentro de _run() (no event loop).
        Garante que a leitura do JSON de termos não ocorre fora do asyncio.run().
        O comportamento do singleton em si está em TestSingletonTranslator.
        """
        resultado = {
            "resposta": "ok",
            "intencao": "outro",
            "usando_fallback": False,
            "tokens_usados": {},
            "processo_id": None,
        }
        with patch(
            "feature_1_ia_personalizada.services.ai.orchestrator.asyncio.run",
            return_value=resultado,
        ):
            with patch(
                "feature_1_ia_personalizada.services.ai.orchestrator.JuridicalTranslator"
            ) as MockT:
                executar_fluxo_orquestrador(1, 1, "oi")
        # asyncio.run mockado → _run nunca executou → JuridicalTranslator não foi chamado
        # (instanciação ocorre apenas dentro de _run, via _criar_translator())
        MockT.assert_not_called()


# ---------------------------------------------------------------------------
# TestFluxoSequencial — integração sem LangGraph
# ---------------------------------------------------------------------------


class TestFluxoSequencial:
    async def test_fluxo_saudacao_sem_buscar_dados(self):
        """
        saudacao → gerar_resposta → verificar → enviar.
        O nó buscar_dados NÃO deve ser chamado para saudacao.
        """
        claude = _mock_claude("Olá! Em que posso ajudar?")
        claude.classificar_intencao = AsyncMock(return_value='{"intencao": "saudacao"}')
        evolution = _mock_evolution()
        memory = _mock_memory()

        with patch("feature_1_ia_personalizada.services.ai.orchestrator._LANGGRAPH_OK", False):
            orq = ConversationOrchestrator(
                claude_client=claude,
                memory=memory,
                translator=_mock_translator(),
                jusbrasil_client=_mock_jusbrasil(),
                cache_manager=_mock_cache(),
                evolution_client=evolution,
                session_factory=_session_factory_from(_make_session()),
            )

        result = await orq.processar(1, 1, "olá", tipo="texto")
        assert result["intencao"] == "saudacao"
        assert result["resposta"]
        evolution.enviar_texto.assert_called_once()

    async def test_fluxo_status_completo(self):
        """status → buscar_dados → gerar_resposta → verificar → enviar."""
        claude = _mock_claude("O processo 1234567-89.2023.8.26.0100 está no TJSP.")
        claude.classificar_intencao = AsyncMock(return_value='{"intencao": "status"}')
        evolution = _mock_evolution()

        with patch("feature_1_ia_personalizada.services.ai.orchestrator._LANGGRAPH_OK", False):
            orq = ConversationOrchestrator(
                claude_client=claude,
                memory=_mock_memory(),
                translator=_mock_translator(),
                jusbrasil_client=_mock_jusbrasil(),
                cache_manager=_mock_cache(),
                evolution_client=evolution,
                session_factory=_session_factory_from(_make_session()),
            )

        result = await orq.processar(1, 1, "qual o status?")
        assert result["intencao"] == "status"
        assert result["processo_id"] == 1
        assert result["resposta"]
        evolution.enviar_texto.assert_called_once()

    async def test_fluxo_cliente_sem_processos_envia_template(self):
        """Sem processos, o fluxo deve enviar TEMPLATE_CLIENTE_SEM_PROCESSO."""
        claude = _mock_claude()
        claude.classificar_intencao = AsyncMock(return_value='{"intencao": "status"}')
        evolution = _mock_evolution()

        with patch("feature_1_ia_personalizada.services.ai.orchestrator._LANGGRAPH_OK", False):
            orq = ConversationOrchestrator(
                claude_client=claude,
                memory=_mock_memory(),
                translator=_mock_translator(),
                jusbrasil_client=_mock_jusbrasil(),
                cache_manager=_mock_cache(),
                evolution_client=evolution,
                session_factory=_session_factory_from(_make_session(processos=[])),
            )

        result = await orq.processar(1, 1, "meu processo?")
        assert result["resposta"] == TEMPLATE_CLIENTE_SEM_PROCESSO
        # Claude não deve ter sido chamado para gerar resposta
        claude.enviar_mensagem.assert_not_called()

    async def test_fluxo_timeout_retorna_mensagem_fallback(self):
        """asyncio.TimeoutError → retorna resposta de timeout, usando_fallback=True."""
        with patch("feature_1_ia_personalizada.services.ai.orchestrator._LANGGRAPH_OK", False):
            orq = ConversationOrchestrator(
                claude_client=_mock_claude(),
                memory=_mock_memory(),
                translator=_mock_translator(),
                jusbrasil_client=_mock_jusbrasil(),
                cache_manager=_mock_cache(),
                evolution_client=_mock_evolution(),
                session_factory=_session_factory_from(_make_session()),
            )

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await orq.processar(1, 1, "qualquer mensagem")

        assert result["usando_fallback"] is True
        assert result["resposta"] == MENSAGENS_FALLBACK.get("timeout", TEMPLATE_ERRO_GENERICO)

    async def test_fluxo_com_fallback_claude_nao_seta_erro(self):
        """RuntimeError no Claude ativa fallback — o fluxo termina normalmente."""
        claude = _mock_claude()
        claude.classificar_intencao = AsyncMock(return_value='{"intencao": "saudacao"}')
        claude.enviar_mensagem = AsyncMock(side_effect=RuntimeError("Claude down"))

        with patch("feature_1_ia_personalizada.services.ai.orchestrator._LANGGRAPH_OK", False):
            orq = ConversationOrchestrator(
                claude_client=claude,
                memory=_mock_memory(),
                translator=_mock_translator(),
                jusbrasil_client=_mock_jusbrasil(),
                cache_manager=_mock_cache(),
                evolution_client=_mock_evolution(),
                session_factory=_session_factory_from(_make_session()),
            )

        result = await orq.processar(1, 1, "ajuda")
        assert result["usando_fallback"] is True
        assert result["resposta"]
        assert not result.get("erro")
