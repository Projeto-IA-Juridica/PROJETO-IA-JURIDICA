#!/usr/bin/env python3
"""
scripts/chat_ao_vivo.py
========================
Conversa interativa com o agente jurídico no terminal.
Não precisa de banco de dados, Redis, Celery ou WhatsApp.
Só usa a ANTHROPIC_API_KEY real — tudo mais é simulado em memória.

Uso:
    python scripts/chat_ao_vivo.py                           # cliente sem processo
    python scripts/chat_ao_vivo.py --com-processo            # com processo ativo no TJSP
    python scripts/chat_ao_vivo.py --nome-cliente "Maria"    # nome personalizado
    python scripts/chat_ao_vivo.py --com-processo --nome-cliente "Carlos" --nome-escritorio "Pires Adv."
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
    pass  # sem python-dotenv — usa variáveis do ambiente

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not ANTHROPIC_API_KEY:
    print("\nERRO: ANTHROPIC_API_KEY não encontrada.")
    print("Configure no arquivo .env ou exporte a variável antes de rodar.\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Imports do projeto (após ajuste do path)
# ---------------------------------------------------------------------------

from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
from feature_1_ia_personalizada.services.ai.memory import ConversationMemory
from feature_1_ia_personalizada.services.ai.orchestrator import ConversationOrchestrator
from feature_1_ia_personalizada.services.ai.translator import JuridicalTranslator
from feature_1_ia_personalizada.services.legal_data.datajud_client import DataJudClient

# ---------------------------------------------------------------------------
# Memória em RAM (substitui Redis)
# ---------------------------------------------------------------------------


class _MemoriaEmRam(ConversationMemory):
    """Histórico mantido numa lista Python — sem Redis."""

    def __init__(self) -> None:  # não chama super().__init__
        self._hist: list[dict] = []

    async def buscar_historico(self, *args, **kwargs) -> list[dict]:
        return list(self._hist)

    async def salvar_mensagem(self, *args, **kwargs) -> None:
        # args = (escritorio_id, cliente_id, role, content)
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
    obj.webhook_whatsapp_instance = None  # None → Evolution não é chamado
    return obj


def _fake_cliente(nome: str) -> MagicMock:
    obj = MagicMock()
    obj.id = 1
    obj.nome = nome
    obj.telefone_whatsapp = None  # None → Evolution não é chamado
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


# ---------------------------------------------------------------------------
# Session factory (async context manager que retorna session fake)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Jusbrasil fake (retorna andamento simulado para não pagar API)
# ---------------------------------------------------------------------------


def _datajud_fake(com_processo: bool) -> DataJudClient:
    client = AsyncMock(spec=DataJudClient)
    if com_processo:
        client.buscar_andamentos_async = AsyncMock(
            return_value=[
                {
                    "descricao": "Concluso para sentença. Aguardando decisão do juiz.",
                    "data": "2024-03-15",
                }
            ]
        )
    else:
        client.buscar_andamentos_async = AsyncMock(return_value=[])
    return client


# ---------------------------------------------------------------------------
# Cache manager fake (sempre cache miss — vai direto ao DataJud fake)
# ---------------------------------------------------------------------------


def _cache_fake() -> MagicMock:
    cache = AsyncMock()
    cache.get_andamentos = AsyncMock(return_value=None)
    cache.set_andamentos = AsyncMock()
    return cache


# ---------------------------------------------------------------------------
# Evolution client fake (no-op — sem envio WhatsApp)
# ---------------------------------------------------------------------------


def _evolution_fake() -> MagicMock:
    client = AsyncMock()
    client.enviar_texto = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# Construtor
# ---------------------------------------------------------------------------


def _criar_orchestrator(
    *,
    com_processo: bool,
    nome_cliente: str,
    nome_escritorio: str,
) -> ConversationOrchestrator:
    return ConversationOrchestrator(
        claude_client=ClaudeClient(api_key=ANTHROPIC_API_KEY),
        memory=_MemoriaEmRam(),
        translator=JuridicalTranslator(),
        datajud_client=_datajud_fake(com_processo),
        cache_manager=_cache_fake(),
        evolution_client=_evolution_fake(),
        session_factory=_make_session_factory(
            com_processo=com_processo,
            nome_cliente=nome_cliente,
            nome_escritorio=nome_escritorio,
        ),
    )


# ---------------------------------------------------------------------------
# Cores ANSI
# ---------------------------------------------------------------------------

_R = "\033[0m"
_BOLD = "\033[1m"
_VERDE = "\033[32m"
_AZUL = "\033[34m"
_CINZA = "\033[90m"
_AMARELO = "\033[33m"
_VERMELHO = "\033[31m"


# ---------------------------------------------------------------------------
# Loop interativo
# ---------------------------------------------------------------------------


async def chat(
    *,
    com_processo: bool,
    nome_cliente: str,
    nome_escritorio: str,
) -> None:
    orq = _criar_orchestrator(
        com_processo=com_processo,
        nome_cliente=nome_cliente,
        nome_escritorio=nome_escritorio,
    )

    print()
    print(f"{_BOLD}{'─' * 58}{_R}")
    print(f"{_BOLD}  Escritório : {nome_escritorio}{_R}")
    print(f"  Cliente    : {nome_cliente}")
    print(
        f"  Processo   : {'✅ ativo (TJSP 0001234-56.2023.8.26.0001)' if com_processo else '❌ sem processo cadastrado'}"
    )
    print(f"{_BOLD}{'─' * 58}{_R}")
    print(f"{_CINZA}  Comandos: 'sair' para encerrar | 'limpar' para resetar histórico{_R}")
    print()

    while True:
        try:
            mensagem = input(f"{_VERDE}{_BOLD}Você:{_R} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEncerrando.")
            break

        if not mensagem:
            continue

        if mensagem.lower() == "sair":
            print("Até logo!")
            break

        if mensagem.lower() == "limpar":
            await orq._memory.limpar_historico(1, 1)
            print(f"{_CINZA}  [histórico limpo — nova conversa]{_R}\n")
            continue

        print(f"{_CINZA}  [processando...]{_R}", flush=True)

        try:
            resultado = await orq.processar(
                escritorio_id=1,
                cliente_id=1,
                mensagem=mensagem,
            )
        except Exception as exc:
            print(f"{_VERMELHO}  [erro no agente: {exc}]{_R}\n")
            continue

        resposta = resultado["resposta"]
        intencao = resultado.get("intencao", "?")
        tokens = resultado.get("tokens_usados", {})
        fallback = resultado.get("usando_fallback", False)

        print()
        print(f"{_AZUL}{_BOLD}Agente:{_R} {resposta}")
        print()

        # linha de metadados
        partes = [f"intenção: {intencao}"]
        if tokens.get("input") or tokens.get("output"):
            partes.append(f"tokens: {tokens.get('input', 0)}↑ {tokens.get('output', 0)}↓")
        if fallback:
            partes.append(f"{_AMARELO}⚠ fallback ativo{_CINZA}")
        print(f"{_CINZA}  [{' | '.join(partes)}]{_R}")
        print()


# ---------------------------------------------------------------------------
# Argumentos de linha de comando
# ---------------------------------------------------------------------------


def _parse_args():
    import argparse

    p = argparse.ArgumentParser(
        description="Chat ao vivo com o agente jurídico (sem infraestrutura)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--com-processo",
        action="store_true",
        help="Simula cliente com processo ativo no TJSP",
    )
    p.add_argument(
        "--nome-cliente",
        default="João Silva",
        metavar="NOME",
        help='Nome do cliente simulado (padrão: "João Silva")',
    )
    p.add_argument(
        "--nome-escritorio",
        default="Silva & Associados Advogados",
        metavar="NOME",
        help='Nome do escritório simulado (padrão: "Silva & Associados Advogados")',
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        chat(
            com_processo=args.com_processo,
            nome_cliente=args.nome_cliente,
            nome_escritorio=args.nome_escritorio,
        )
    )
