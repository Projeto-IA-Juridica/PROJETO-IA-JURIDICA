#!/usr/bin/env python3
"""
scripts/streamlit_chat.py
==========================
Interface Streamlit para conversar com o agente jurídico.
Não precisa de banco de dados, Redis, Celery ou WhatsApp.
Só usa a ANTHROPIC_API_KEY real — tudo mais é simulado em memória.

Uso:
    streamlit run scripts/streamlit_chat.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Path e .env
# ---------------------------------------------------------------------------

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_ROOT, ".env"), override=False)
except ImportError:
    pass

import streamlit as st

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ---------------------------------------------------------------------------
# Imports do projeto
# ---------------------------------------------------------------------------

from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
from feature_1_ia_personalizada.services.ai.memory import ConversationMemory
from feature_1_ia_personalizada.services.ai.orchestrator import ConversationOrchestrator
from feature_1_ia_personalizada.services.ai.translator import JuridicalTranslator
from feature_1_ia_personalizada.services.legal_data.jusbrasil_client import (
    JusbrasilClient,
)

# ---------------------------------------------------------------------------
# Memória em RAM (substitui Redis)
# ---------------------------------------------------------------------------


class _MemoriaEmRam(ConversationMemory):
    def __init__(self) -> None:
        self._hist: list[dict] = []

    async def buscar_historico(self, *args, **kwargs) -> list[dict]:
        return list(self._hist)

    async def salvar_mensagem(self, *args, **kwargs) -> None:
        role, content = str(args[2]), str(args[3])
        self._hist.append({"role": role, "content": content})

    async def limpar_historico(self, *args, **kwargs) -> None:
        self._hist.clear()

    async def tamanho_historico(self, *args, **kwargs) -> int:
        return len(self._hist)


# ---------------------------------------------------------------------------
# Entidades fake
# ---------------------------------------------------------------------------


def _fake_escritorio(nome: str) -> MagicMock:
    obj = MagicMock()
    obj.id = 1
    obj.nome = nome
    obj.webhook_whatsapp_instance = None
    return obj


def _fake_cliente(nome: str) -> MagicMock:
    obj = MagicMock()
    obj.id = 1
    obj.nome = nome
    obj.telefone_whatsapp = None
    obj.escritorio_id = 1
    return obj


def _fake_processo() -> MagicMock:
    obj = MagicMock()
    obj.id = 1
    obj.numero_cnj = "0001234-56.2023.8.26.0001"
    obj.tribunal = "TJSP"
    obj.vara = "3ª Vara Cível de São Paulo"
    obj.polo_cliente = "autor"
    obj.ultimo_andamento = "Concluso para sentença"
    obj.data_ultimo_andamento = None
    obj.monitoramento_ativo = True
    obj.escritorio_id = 1
    obj.cliente_id = 1
    return obj


def _make_session_factory(*, com_processo: bool, nome_cliente: str, nome_escritorio: str):
    escritorio = _fake_escritorio(nome_escritorio)
    cliente = _fake_cliente(nome_cliente)
    processo = _fake_processo()
    processos = [processo] if com_processo else []

    @asynccontextmanager
    async def _factory():
        session = AsyncMock()

        async def _get(model_class, pk: Any):
            nome_classe = getattr(model_class, "__name__", str(model_class))
            if "Escritorio" in nome_classe:
                return escritorio
            if "Cliente" in nome_classe:
                return cliente
            if "Processo" in nome_classe:
                return processo
            return None

        session.get = _get
        resultado = MagicMock()
        resultado.scalars.return_value.all.return_value = processos
        session.execute = AsyncMock(return_value=resultado)
        session.add = MagicMock()
        session.commit = AsyncMock()
        yield session

    return _factory


def _jusbrasil_fake(com_processo: bool) -> JusbrasilClient:
    client = AsyncMock(spec=JusbrasilClient)
    if com_processo:
        client.sincronizar_andamentos = AsyncMock(
            return_value=[
                {
                    "descricao": "Concluso para sentença. Aguardando decisão do juiz.",
                    "data": "2024-03-15",
                }
            ]
        )
    else:
        client.sincronizar_andamentos = AsyncMock(return_value=[])
    return client


def _cache_fake() -> MagicMock:
    cache = AsyncMock()
    cache.get_andamentos = AsyncMock(return_value=None)
    cache.set_andamentos = AsyncMock()
    return cache


def _evolution_fake() -> MagicMock:
    client = AsyncMock()
    client.enviar_texto = AsyncMock()
    return client


def _criar_orchestrator(
    *, com_processo: bool, nome_cliente: str, nome_escritorio: str
) -> ConversationOrchestrator:
    return ConversationOrchestrator(
        claude_client=ClaudeClient(api_key=ANTHROPIC_API_KEY),
        memory=_MemoriaEmRam(),
        translator=JuridicalTranslator(),
        jusbrasil_client=_jusbrasil_fake(com_processo),
        cache_manager=_cache_fake(),
        evolution_client=_evolution_fake(),
        session_factory=_make_session_factory(
            com_processo=com_processo,
            nome_cliente=nome_cliente,
            nome_escritorio=nome_escritorio,
        ),
    )


# ---------------------------------------------------------------------------
# Helpers de estado do Streamlit
# ---------------------------------------------------------------------------


def _init_state(com_processo: bool, nome_cliente: str, nome_escritorio: str) -> None:
    """Inicializa (ou reinicializa) o estado da sessão."""
    st.session_state.messages = []
    st.session_state.total_tokens_in = 0
    st.session_state.total_tokens_out = 0
    st.session_state.orchestrator = _criar_orchestrator(
        com_processo=com_processo,
        nome_cliente=nome_cliente,
        nome_escritorio=nome_escritorio,
    )
    st.session_state.config = {
        "com_processo": com_processo,
        "nome_cliente": nome_cliente,
        "nome_escritorio": nome_escritorio,
    }


def _config_changed(com_processo: bool, nome_cliente: str, nome_escritorio: str) -> bool:
    cfg = st.session_state.get("config", {})
    return (
        cfg.get("com_processo") != com_processo
        or cfg.get("nome_cliente") != nome_cliente
        or cfg.get("nome_escritorio") != nome_escritorio
    )


async def _processar(mensagem: str) -> dict:
    orq: ConversationOrchestrator = st.session_state.orchestrator
    return await orq.processar(escritorio_id=1, cliente_id=1, mensagem=mensagem)


# ---------------------------------------------------------------------------
# App Streamlit
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Concierge Jurídico IA",
    page_icon="⚖️",
    layout="centered",
)

# --- Sidebar ---
with st.sidebar:
    st.title("⚖️ Configurações")
    st.divider()

    nome_escritorio = st.text_input("Escritório", value="Silva & Associados Advogados")
    nome_cliente = st.text_input("Nome do cliente", value="João Silva")
    com_processo = st.toggle("Simular processo ativo (TJSP)", value=False)

    if com_processo:
        st.info(
            "📋 **Processo simulado**\n\n`0001234-56.2023.8.26.0001`\n\nTJSP · 3ª Vara Cível\n\nÚltimo andamento: *Concluso para sentença*"
        )

    st.divider()

    if st.button("🔄 Nova conversa", use_container_width=True):
        _init_state(com_processo, nome_cliente, nome_escritorio)
        st.rerun()

    st.divider()

    # Métricas de uso
    if "total_tokens_in" in st.session_state:
        col1, col2 = st.columns(2)
        col1.metric("Tokens ↑", st.session_state.total_tokens_in)
        col2.metric("Tokens ↓", st.session_state.total_tokens_out)

    # Status da API key
    if ANTHROPIC_API_KEY:
        st.success("API Key configurada", icon="✅")
    else:
        st.error("ANTHROPIC_API_KEY não encontrada no .env", icon="🔑")

# --- Inicializa estado se necessário ---
if "orchestrator" not in st.session_state or _config_changed(
    com_processo, nome_cliente, nome_escritorio
):
    _init_state(com_processo, nome_cliente, nome_escritorio)

# --- Cabeçalho ---
st.title("⚖️ Concierge Jurídico Digital")
st.caption(f"Agente: **{nome_escritorio}** · Cliente: **{nome_cliente}**")
st.divider()

# --- Histórico de mensagens ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "⚖️"):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("meta"):
            meta = msg["meta"]
            partes = []
            if meta.get("intencao"):
                partes.append(f"intenção: `{meta['intencao']}`")
            if meta.get("tokens_in") or meta.get("tokens_out"):
                partes.append(f"tokens: `{meta.get('tokens_in', 0)}↑ {meta.get('tokens_out', 0)}↓`")
            if meta.get("fallback"):
                partes.append("⚠️ fallback ativo")
            if partes:
                st.caption(" · ".join(partes))

# --- Input do usuário ---
if not ANTHROPIC_API_KEY:
    st.error("Configure a `ANTHROPIC_API_KEY` no arquivo `.env` para usar o chat.")
    st.stop()

if prompt := st.chat_input("Digite sua mensagem..."):
    # Mostra mensagem do usuário
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # Processa e mostra resposta
    with st.chat_message("assistant", avatar="⚖️"):
        with st.spinner("Processando..."):
            try:
                resultado = asyncio.run(_processar(prompt))

                resposta = resultado["resposta"]
                intencao = resultado.get("intencao", "outro")
                tokens = resultado.get("tokens_usados", {})
                fallback = resultado.get("usando_fallback", False)
                tokens_in = tokens.get("input", 0)
                tokens_out = tokens.get("output", 0)

                # Acumula métricas na sidebar
                st.session_state.total_tokens_in += tokens_in
                st.session_state.total_tokens_out += tokens_out

                st.markdown(resposta)

                partes = [f"intenção: `{intencao}`"]
                if tokens_in or tokens_out:
                    partes.append(f"tokens: `{tokens_in}↑ {tokens_out}↓`")
                if fallback:
                    partes.append("⚠️ fallback ativo")
                st.caption(" · ".join(partes))

                # Salva no histórico
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": resposta,
                        "meta": {
                            "intencao": intencao,
                            "tokens_in": tokens_in,
                            "tokens_out": tokens_out,
                            "fallback": fallback,
                        },
                    }
                )

            except Exception as exc:
                st.error(f"Erro no agente: {exc}")
