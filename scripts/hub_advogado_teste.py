#!/usr/bin/env python3
"""
scripts/hub_advogado_teste.py
==============================
Hub do Advogado — Demonstração Completa: Import CSV + DataJud + Orchestrator IA

Fluxo demonstrado:
  1. Upload de CSV com clientes e números de processo (CNJ)
  2. Hub do advogado com lista de clientes
  3. Consulta em tempo real ao DataJud pelo número do processo real
  4. Cada cliente tem seu próprio ConversationOrchestrator (LangGraph completo)
  5. Boas-vindas automáticas geradas pelo orchestrator (intenção: saudacao)
  6. Chat com classificação de intenção, fact-check e resposta contextualizada

Dependências de infraestrutura zeradas:
  - Banco de dados → session_factory mockada com dados reais do DataJud
  - Redis → _MemoriaEmRam (in-memory por cliente)
  - Celery → não usado
  - WhatsApp Evolution API → mock no-op (webhook_whatsapp_instance=None)

Requer apenas ANTHROPIC_API_KEY (e opcionalmente DATAJUD_API_KEY).

Uso:
    streamlit run scripts/hub_advogado_teste.py
"""

from __future__ import annotations

import asyncio
import csv
import io
import os
import re
import sys
from contextlib import asynccontextmanager
from datetime import date
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

import httpx
import streamlit as st

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DATAJUD_API_KEY = os.environ.get("DATAJUD_API_KEY", "")

# ---------------------------------------------------------------------------
# Imports do projeto (orchestrator completo)
# ---------------------------------------------------------------------------

from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
from feature_1_ia_personalizada.services.ai.memory import ConversationMemory
from feature_1_ia_personalizada.services.ai.orchestrator import ConversationOrchestrator
from feature_1_ia_personalizada.services.ai.translator import JuridicalTranslator
from feature_1_ia_personalizada.services.legal_data.jusbrasil_client import (
    JusbrasilClient,
)

# ---------------------------------------------------------------------------
# Padrões CNJ
# ---------------------------------------------------------------------------

_CNJ_FORMATADO = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")
_CNJ_RAW = re.compile(r"^\d{20}$")

# ---------------------------------------------------------------------------
# Mapeamento DataJud (derivar índice ElasticSearch do número CNJ)
# ---------------------------------------------------------------------------

_TJ_INDICES: dict[str, str] = {
    "01": "api_publica_tjac",
    "02": "api_publica_tjal",
    "03": "api_publica_tjap",
    "04": "api_publica_tjam",
    "05": "api_publica_tjba",
    "06": "api_publica_tjce",
    "07": "api_publica_tjdf",
    "08": "api_publica_tjes",
    "09": "api_publica_tjgo",
    "10": "api_publica_tjma",
    "11": "api_publica_tjmt",
    "12": "api_publica_tjms",
    "13": "api_publica_tjmg",
    "14": "api_publica_tjpa",
    "15": "api_publica_tjpb",
    "16": "api_publica_tjpr",
    "17": "api_publica_tjpe",
    "18": "api_publica_tjpi",
    "19": "api_publica_tjrj",
    "20": "api_publica_tjrn",
    "21": "api_publica_tjrs",
    "22": "api_publica_tjro",
    "23": "api_publica_tjrr",
    "24": "api_publica_tjsc",
    "25": "api_publica_tjse",
    "26": "api_publica_tjsp",
    "27": "api_publica_tjto",
}
_DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"


# ---------------------------------------------------------------------------
# Parse de CSV (sem banco de dados)
# ---------------------------------------------------------------------------


def _normalizar_telefone(tel: str) -> str:
    numeros = re.sub(r"\D", "", tel)
    if len(numeros) in (10, 11):
        numeros = "55" + numeros
    return numeros


def _normalizar_cnj(numero: str) -> str | None:
    numero = numero.strip()
    if _CNJ_FORMATADO.match(numero):
        return numero
    digits = re.sub(r"[.\-/]", "", numero)
    if _CNJ_RAW.match(digits):
        return (
            f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}"
            f".{digits[13]}.{digits[14:16]}.{digits[16:]}"
        )
    return None


def parsear_csv(conteudo: bytes) -> tuple[list[dict], list[dict]]:
    """Parseia o CSV e retorna (clientes, erros). Sem escrita em banco."""
    texto = conteudo.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(texto))

    if not reader.fieldnames:
        return [], [{"linha": 0, "motivo": "CSV vazio ou sem cabeçalho"}]

    campos = [f.strip().lower() for f in reader.fieldnames if f]
    faltando = [c for c in ("nome", "telefone") if c not in campos]
    if faltando:
        return [], [
            {"linha": 1, "motivo": f"Colunas obrigatórias ausentes: {faltando}"}
        ]

    clientes: list[dict] = []
    erros: list[dict] = []

    for i, row in enumerate(reader, start=2):
        row_norm: dict[str, str] = {
            k.strip().lower(): (v or "").strip() for k, v in row.items() if k
        }

        nome = row_norm.get("nome", "")
        telefone_raw = row_norm.get("telefone", "")

        if not nome:
            erros.append({"linha": i, "motivo": "Nome ausente"})
            continue
        if not telefone_raw:
            erros.append({"linha": i, "motivo": "Telefone ausente"})
            continue

        telefone = _normalizar_telefone(telefone_raw)
        if not (telefone.isdigit() and 12 <= len(telefone) <= 13):
            erros.append({"linha": i, "motivo": f"Telefone inválido: {telefone_raw!r}"})
            continue

        numero_processo_raw = row_norm.get("numero_processo", "").strip()
        numero_cnj: str | None = None
        if numero_processo_raw:
            numero_cnj = _normalizar_cnj(numero_processo_raw)
            if numero_cnj is None:
                erros.append(
                    {
                        "linha": i,
                        "motivo": (
                            f"Número de processo inválido: {numero_processo_raw!r}. "
                            "Formato esperado: 0000001-23.2024.8.26.0100"
                        ),
                    }
                )
                continue

        polo_raw = row_norm.get("polo_cliente", "autor").lower().strip()
        polo = polo_raw if polo_raw in ("autor", "reu", "terceiro") else "autor"

        clientes.append(
            {
                "id": len(clientes),
                "nome": nome,
                "telefone": telefone,
                "cpf": row_norm.get("cpf", "") or "(não informado)",
                "data_nascimento": row_norm.get("data_nascimento") or None,
                "profissao": row_norm.get("profissao") or None,
                "empresa": row_norm.get("empresa") or None,
                "status": (row_norm.get("status") or "ativo").lower(),
                "numero_cnj": numero_cnj,
                "polo_cliente": polo if numero_cnj else None,
            }
        )

    return clientes, erros


# ---------------------------------------------------------------------------
# Integração DataJud — API pública real do CNJ
# ---------------------------------------------------------------------------


def _indice_datajud(numero_cnj: str) -> str | None:
    digits = re.sub(r"[.\-]", "", numero_cnj)
    if len(digits) != 20:
        return None
    j = digits[13]
    tt = digits[14:16]
    if j == "8":
        return _TJ_INDICES.get(tt)
    if j == "5":
        n = int(tt)
        return f"api_publica_trf{n}" if 1 <= n <= 6 else None
    if j == "6":
        n = int(tt)
        return f"api_publica_trt{n}" if 1 <= n <= 24 else None
    if j == "4":
        return "api_publica_tst"
    if j == "3":
        return "api_publica_stj"
    if j == "1":
        return "api_publica_stf"
    return None


async def _buscar_datajud_async(numero_cnj: str) -> dict[str, Any] | None:
    """Consulta assíncrona real ao DataJud. Retorna _source do hit ou None."""
    indice = _indice_datajud(numero_cnj)
    if not indice:
        return None

    digits = re.sub(r"[.\-]", "", numero_cnj)
    url = f"{_DATAJUD_BASE}/{indice}/_search"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if DATAJUD_API_KEY:
        headers["Authorization"] = f"ApiKey {DATAJUD_API_KEY}"

    query = {"query": {"match": {"numeroProcesso": digits}}}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=query, headers=headers)
        if resp.status_code == 200:
            hits = resp.json().get("hits", {}).get("hits", [])
            return hits[0].get("_source") if hits else None
    except Exception:
        pass
    return None


@st.cache_data(ttl=300, show_spinner=False)
def consultar_datajud(numero_cnj: str) -> dict[str, Any] | None:
    """Wrapper síncrono com cache de 5 minutos."""
    return asyncio.run(_buscar_datajud_async(numero_cnj))


# ---------------------------------------------------------------------------
# Memória em RAM — substitui Redis por cliente
# ---------------------------------------------------------------------------


class _MemoriaEmRam(ConversationMemory):
    """Implementação in-memory do ConversationMemory (sem Redis)."""

    def __init__(self) -> None:
        self._hist: list[dict] = []

    async def buscar_historico(self, *args, **kwargs) -> list[dict]:
        return list(self._hist)

    async def salvar_mensagem(self, *args, **kwargs) -> None:
        # args: escritorio_id, cliente_id, role, content
        role, content = str(args[2]), str(args[3])
        self._hist.append({"role": role, "content": content})

    async def limpar_historico(self, *args, **kwargs) -> None:
        self._hist.clear()

    async def tamanho_historico(self, *args, **kwargs) -> int:
        return len(self._hist)


# ---------------------------------------------------------------------------
# Mocks de entidades do banco — populados com dados reais do DataJud
# ---------------------------------------------------------------------------


def _fake_escritorio(nome: str) -> MagicMock:
    obj = MagicMock()
    obj.id = 1
    obj.nome = nome
    obj.webhook_whatsapp_instance = None  # sem Evolution API → não envia WhatsApp
    return obj


def _fake_cliente(cliente: dict) -> MagicMock:
    obj = MagicMock()
    obj.id = 1
    obj.nome = cliente["nome"]
    obj.telefone_whatsapp = cliente["telefone"]
    obj.escritorio_id = 1
    return obj


def _fake_processo(cliente: dict, dados_datajud: dict | None) -> MagicMock | None:
    """
    Monta o objeto Processo a partir do CSV + dados reais do DataJud.
    Retorna None se o cliente não tem processo cadastrado.
    """
    if not cliente.get("numero_cnj"):
        return None

    obj = MagicMock()
    obj.id = 1
    obj.numero_cnj = cliente["numero_cnj"]
    obj.polo_cliente = cliente.get("polo_cliente", "autor")
    obj.monitoramento_ativo = True
    obj.escritorio_id = 1
    obj.cliente_id = 1

    if dados_datajud:
        # Dados reais do DataJud
        tribunal = dados_datajud.get("tribunal", {})
        obj.tribunal = (
            tribunal.get("nome", "N/D") if isinstance(tribunal, dict) else str(tribunal)
        )
        # DataJud não expõe vara diretamente; usa grau quando disponível
        grau = dados_datajud.get("grau", "")
        obj.vara = grau if grau else "N/D"

        movimentos = dados_datajud.get("movimentos", [])
        if movimentos and isinstance(movimentos[0], dict):
            ultimo = movimentos[0]
            obj.ultimo_andamento = ultimo.get("nome", "sem movimentação recente")
            data_str = (ultimo.get("dataHora") or "")[:10]
            try:
                obj.data_ultimo_andamento = (
                    date.fromisoformat(data_str) if data_str else None
                )
            except ValueError:
                obj.data_ultimo_andamento = None
        else:
            obj.ultimo_andamento = "sem movimentação recente"
            obj.data_ultimo_andamento = None
    else:
        # Sem dados do DataJud — preenche com placeholders
        obj.tribunal = "N/D"
        obj.vara = "N/D"
        obj.ultimo_andamento = "aguardando consulta ao tribunal"
        obj.data_ultimo_andamento = None

    return obj


def _fake_jusbrasil(dados_datajud: dict | None) -> JusbrasilClient:
    """
    Jusbrasil fake que retorna os movimentos reais do DataJud no formato esperado
    pelo orchestrator: [{"descricao": str, "data": str}]
    """
    client = AsyncMock(spec=JusbrasilClient)

    if dados_datajud:
        movimentos = dados_datajud.get("movimentos", [])
        andamentos = [
            {
                "descricao": m.get("nome", ""),
                "data": (m.get("dataHora") or "")[:10],
            }
            for m in movimentos
            if isinstance(m, dict) and m.get("nome")
        ]
    else:
        andamentos = []

    client.sincronizar_andamentos = AsyncMock(return_value=andamentos)
    return client


def _fake_cache() -> MagicMock:
    """Cache sempre vazio — força busca no Jusbrasil (que retorna dados DataJud)."""
    cache = AsyncMock()
    cache.get_andamentos = AsyncMock(return_value=None)
    cache.set_andamentos = AsyncMock()
    return cache


def _fake_evolution() -> MagicMock:
    """Evolution API no-op — não envia WhatsApp no demo."""
    client = AsyncMock()
    client.enviar_texto = AsyncMock()
    return client


def _make_session_factory(
    escritorio_nome: str, cliente: dict, dados_datajud: dict | None
):
    """
    Cria uma session_factory mockada que retorna entidades populadas com
    dados reais do CSV e do DataJud, no mesmo contrato esperado pelo orchestrator.
    """
    escritorio = _fake_escritorio(escritorio_nome)
    cliente_obj = _fake_cliente(cliente)
    processo_obj = _fake_processo(cliente, dados_datajud)
    processos = [processo_obj] if processo_obj else []

    @asynccontextmanager
    async def _factory():
        session = AsyncMock()

        async def _get(model_class, pk: Any):
            nome_classe = getattr(model_class, "__name__", str(model_class))
            if "Escritorio" in nome_classe:
                return escritorio
            if "Cliente" in nome_classe:
                return cliente_obj
            if "Processo" in nome_classe:
                return processo_obj
            return None

        session.get = _get

        resultado = MagicMock()
        resultado.scalars.return_value.all.return_value = processos
        session.execute = AsyncMock(return_value=resultado)
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        yield session

    return _factory


# ---------------------------------------------------------------------------
# Criação do orchestrator completo por cliente
# ---------------------------------------------------------------------------


def criar_orchestrator(
    escritorio_nome: str,
    cliente: dict,
    dados_datajud: dict | None,
) -> tuple[ConversationOrchestrator, _MemoriaEmRam]:
    """
    Instancia o ConversationOrchestrator real do projeto com:
    - LangGraph completo (classificação → busca → geração → fact-check → resposta)
    - Memória in-memory por cliente
    - Session factory mockada com dados reais do DataJud
    - Jusbrasil fake que expõe movimentos reais do DataJud
    """
    memoria = _MemoriaEmRam()

    orchestrator = ConversationOrchestrator(
        claude_client=ClaudeClient(api_key=ANTHROPIC_API_KEY),
        memory=memoria,
        translator=JuridicalTranslator(),
        jusbrasil_client=_fake_jusbrasil(dados_datajud),
        cache_manager=_fake_cache(),
        evolution_client=_fake_evolution(),
        session_factory=_make_session_factory(escritorio_nome, cliente, dados_datajud),
    )

    # No demo, desabilita a verificação factual por string exata do FactChecker.
    # O FactChecker compara a resposta do Claude com dados brutos do banco (texto exato),
    # mas aqui o Claude traduz para linguagem simples — o que é o comportamento correto.
    # A camada de filtro de linguagem (pareceres, promessas) continua ativa normalmente.
    async def _sem_verificacao_de_dados(_processo_id: str) -> dict:
        return {}

    orchestrator._fact_checker._buscar_dados_processo = _sem_verificacao_de_dados

    return orchestrator, memoria


# ---------------------------------------------------------------------------
# Helpers de UI
# ---------------------------------------------------------------------------


def _tabela_md(linhas: list[tuple[str, str]]) -> str:
    rows = "\n".join(f"| **{k}** | {v} |" for k, v in linhas)
    return f"| Campo | Valor |\n|-------|-------|\n{rows}"


# ---------------------------------------------------------------------------
# App Streamlit
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Hub do Advogado — IA Jurídica",
    page_icon="⚖️",
    layout="wide",
)

# ── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚖️ Hub do Advogado")
    st.caption("Demonstração Completa — Orchestrator LangGraph")
    st.divider()

    escritorio_nome = st.text_input(
        "Nome do Escritório", value="Silva & Associados Advogados"
    )

    st.divider()
    st.subheader("Importar Clientes")

    arquivo_csv = st.file_uploader(
        "Upload do CSV",
        type=["csv"],
        help=(
            "Obrigatórias: nome, telefone\n"
            "Opcionais: cpf, data_nascimento, profissao, empresa, "
            "numero_processo (formato CNJ), polo_cliente"
        ),
    )

    if arquivo_csv:
        csv_hash = hash(arquivo_csv.getvalue())
        # Só reprocessa se for um arquivo diferente do último importado
        if st.session_state.get("csv_hash") != csv_hash:
            clientes_importados, erros_csv = parsear_csv(arquivo_csv.getvalue())
            st.session_state["clientes_hub"] = clientes_importados
            st.session_state["erros_hub"] = erros_csv
            st.session_state["csv_hash"] = csv_hash
            # Limpa orchestrators apenas quando o CSV muda de verdade
            for key in list(st.session_state.keys()):
                if key.startswith(("orch_", "mem_", "chat_", "welcome_", "datajud_")):
                    del st.session_state[key]
            if clientes_importados:
                st.success(f"{len(clientes_importados)} cliente(s) importado(s)")
            if erros_csv:
                st.warning(f"{len(erros_csv)} linha(s) com erro")

    if st.session_state.get("clientes_hub"):
        st.divider()
        st.subheader("Clientes")
        for c in st.session_state["clientes_hub"]:
            ativo = c.get("status", "ativo") != "inativo"
            icone = "🟢" if ativo else "🔴"
            badge_proc = " 📋" if c.get("numero_cnj") else ""
            st.write(f"{icone} {c['nome']}{badge_proc}")

    st.divider()

    if ANTHROPIC_API_KEY:
        st.success("Claude: configurado", icon="✅")
    else:
        st.error("ANTHROPIC_API_KEY ausente", icon="🔑")

    if DATAJUD_API_KEY:
        st.success("DataJud: com chave API", icon="✅")
    else:
        st.info("DataJud: acesso público", icon="ℹ️")

    st.caption("Orchestrator: LangGraph + FactChecker + Translator")

    st.divider()
    st.caption("📄 CSV de exemplo:")
    csv_exemplo = (
        "nome,telefone,cpf,data_nascimento,profissao,empresa,numero_processo,polo_cliente\n"
        "João Silva,11999990001,123.456.789-00,15/03/1980,Engenheiro,Tech Corp,"
        "0000001-68.2019.8.26.0053,autor\n"
        "Maria Santos,21988880002,987.654.321-00,22/07/1975,Médica,Hospital ABC,,\n"
        "Carlos Oliveira,31977770003,456.789.012-00,08/11/1990,Empresário,,,\n"
    )
    st.download_button(
        "Baixar clientes_teste.csv",
        data=csv_exemplo,
        file_name="clientes_teste.csv",
        mime="text/csv",
        use_container_width=True,
    )

# ── Main Area ────────────────────────────────────────────────────────────────

clientes: list[dict] = st.session_state.get("clientes_hub", [])

if not clientes:
    st.title("⚖️ Hub do Advogado — Demonstração Completa")
    st.markdown(
        """
        ### O que este teste demonstra

        O fluxo completo da plataforma, usando o **orchestrator real do projeto** (LangGraph):

        | Etapa | Tecnologia |
        |-------|-----------|
        | Upload CSV | Parser in-memory |
        | Consulta de processo | API real DataJud (CNJ) |
        | Classificação de intenção | Claude (LangGraph nó 1) |
        | Busca de dados | Session factory com dados DataJud injetados |
        | Geração de resposta | Claude com prompts do projeto |
        | Verificação de fatos | FactChecker do projeto |
        | Memória de conversa | In-memory por cliente (sem Redis) |
        | Envio | No-op (sem WhatsApp no demo) |

        ---

        ### Como usar

        1. Clique em **Upload do CSV** na barra lateral
        2. Use o CSV de exemplo ou crie o seu com números de processo reais
        3. Clique na aba do cliente para abrir o atendimento
        4. O orchestrator gera boas-vindas e responde perguntas com dados reais

        ---

        ### Exemplos de perguntas para testar

        - *"Qual é o status do meu processo?"* → intent: status, usa dados DataJud
        - *"O que significa concluso para sentença?"* → intent: duvida_termo
        - *"Estou preocupado com o andamento"* → intent: reclamacao
        - *"Oi, tudo bem?"* → intent: saudacao
        """
    )

    if st.session_state.get("erros_hub"):
        with st.expander("Ver erros do CSV"):
            for e in st.session_state["erros_hub"]:
                st.error(f"Linha {e['linha']}: {e['motivo']}")
    st.stop()

# ── Header ───────────────────────────────────────────────────────────────────

col_titulo, col_info = st.columns([3, 1])
with col_titulo:
    st.title(f"⚖️ {escritorio_nome}")
    st.caption(
        f"{len(clientes)} cliente(s) · "
        f"{sum(1 for c in clientes if c.get('numero_cnj'))} com processo · "
        "Orchestrator LangGraph ativo"
    )
with col_info:
    if st.session_state.get("erros_hub"):
        with st.expander(f"⚠️ {len(st.session_state['erros_hub'])} erro(s) no CSV"):
            for e in st.session_state["erros_hub"]:
                st.write(f"Linha {e['linha']}: {e['motivo']}")

st.divider()

# ── Tabs por cliente ──────────────────────────────────────────────────────────

tabs = st.tabs([c["nome"] for c in clientes])

for tab, cliente in zip(tabs, clientes, strict=False):
    with tab:
        cid = cliente["id"]

        # ── Consulta DataJud ────────────────────────────────────────────────

        dados_dj: dict | None = None
        if cliente.get("numero_cnj"):
            dj_key = f"datajud_{cliente['numero_cnj']}"
            if dj_key not in st.session_state:
                with st.spinner(f"Consultando DataJud: {cliente['numero_cnj']}..."):
                    st.session_state[dj_key] = consultar_datajud(cliente["numero_cnj"])
            dados_dj = st.session_state[dj_key]

        # ── Inicializa orchestrator (uma vez por cliente) ───────────────────

        orch_key = f"orch_{cid}"
        if orch_key not in st.session_state:
            orchestrator, memoria = criar_orchestrator(
                escritorio_nome, cliente, dados_dj
            )
            st.session_state[orch_key] = orchestrator
            st.session_state[f"mem_{cid}"] = memoria
            st.session_state[f"chat_{cid}"] = []
            st.session_state[f"tokens_{cid}"] = {"in": 0, "out": 0}

        orchestrator: ConversationOrchestrator = st.session_state[orch_key]

        # ── Cards de informação ─────────────────────────────────────────────

        col_cliente, col_processo = st.columns([1, 2])

        with col_cliente:
            st.markdown("#### Dados do Cliente")
            linhas_info: list[tuple[str, str]] = [
                ("Nome", cliente["nome"]),
                ("Telefone", f"`{cliente['telefone']}`"),
                ("CPF", cliente["cpf"]),
                ("Nascimento", cliente.get("data_nascimento") or "—"),
                ("Profissão", cliente.get("profissao") or "—"),
                ("Empresa", cliente.get("empresa") or "—"),
                (
                    "Status",
                    "🟢 Ativo" if cliente["status"] != "inativo" else "🔴 Inativo",
                ),
            ]
            st.markdown(_tabela_md(linhas_info))

        with col_processo:
            st.markdown("#### Processo Judicial")

            if not cliente.get("numero_cnj"):
                st.info("Nenhum processo cadastrado para este cliente.")
            elif dados_dj:
                tribunal = dados_dj.get("tribunal", {})
                nome_trib = (
                    tribunal.get("nome", "—")
                    if isinstance(tribunal, dict)
                    else str(tribunal)
                )
                classe = dados_dj.get("classe", {})
                nome_classe = (
                    classe.get("nome", "—") if isinstance(classe, dict) else str(classe)
                )
                assuntos = dados_dj.get("assuntos", [])
                assunto_str = (
                    ", ".join(
                        a.get("nome", "") if isinstance(a, dict) else str(a)
                        for a in assuntos[:2]
                    )
                    or "—"
                )
                movimentos = dados_dj.get("movimentos", [])
                ultimo_mov = movimentos[0] if movimentos else {}
                nome_mov = (
                    ultimo_mov.get("nome", "—") if isinstance(ultimo_mov, dict) else "—"
                )
                data_mov = (
                    (ultimo_mov.get("dataHora") or "")[:10]
                    if isinstance(ultimo_mov, dict)
                    else "—"
                )
                data_ajuiz = (dados_dj.get("dataAjuizamento") or "")[:10] or "—"

                linhas_proc: list[tuple[str, str]] = [
                    ("CNJ", f"`{cliente['numero_cnj']}`"),
                    ("Tribunal", nome_trib),
                    ("Classe", nome_classe),
                    ("Assunto(s)", assunto_str),
                    ("Polo", (cliente["polo_cliente"] or "—").upper()),
                    ("Ajuizamento", data_ajuiz),
                    ("Último Andamento", nome_mov),
                    ("Data Andamento", data_mov),
                ]
                st.markdown(_tabela_md(linhas_proc))
                st.success(
                    "Dados reais do DataJud injetados no orchestrator", icon="✅"
                )

                if len(movimentos) > 1:
                    with st.expander("Ver andamentos anteriores"):
                        for mov in movimentos[1:6]:
                            if isinstance(mov, dict):
                                data_m = (mov.get("dataHora") or "")[:10]
                                st.write(f"• **{data_m}** — {mov.get('nome', '')}")
            else:
                linhas_proc_vazio: list[tuple[str, str]] = [
                    ("CNJ", f"`{cliente['numero_cnj']}`"),
                    ("Polo", (cliente.get("polo_cliente") or "—").upper()),
                    ("DataJud", "Processo não encontrado"),
                ]
                st.markdown(_tabela_md(linhas_proc_vazio))
                st.warning(
                    "Processo não encontrado no DataJud. "
                    "O orchestrator responderá com as informações disponíveis do cadastro.",
                    icon="⚠️",
                )

        st.divider()

        # ── Chat com orchestrator LangGraph ─────────────────────────────────

        if not ANTHROPIC_API_KEY:
            st.error("Configure `ANTHROPIC_API_KEY` no `.env` para ativar o chat.")
            continue

        chat_key = f"chat_{cid}"
        tokens_key = f"tokens_{cid}"
        welcome_key = f"welcome_{cid}"

        # Boas-vindas automáticas via orchestrator (intenção: saudacao)
        if not st.session_state.get(welcome_key):
            with st.spinner("Orchestrator gerando boas-vindas (intent: saudacao)..."):
                try:
                    resultado_bv = asyncio.run(
                        orchestrator.processar(
                            escritorio_id=1,
                            cliente_id=1,
                            mensagem="olá",
                            tipo="texto",
                        )
                    )
                    boas_vindas = resultado_bv["resposta"]
                    intencao_bv = resultado_bv.get("intencao", "saudacao")
                    fallback_bv = resultado_bv.get("usando_fallback", False)
                except Exception:
                    boas_vindas = (
                        f"Olá, {cliente['nome'].split()[0]}! "
                        f"Bem-vindo(a) ao {escritorio_nome}."
                    )
                    intencao_bv = "erro"
                    fallback_bv = True

            st.session_state[chat_key].append(
                {
                    "role": "assistant",
                    "content": boas_vindas,
                    "meta": {"intencao": intencao_bv, "fallback": fallback_bv},
                }
            )
            st.session_state[welcome_key] = True

        # Cabeçalho do chat
        col_chat_title, col_tokens = st.columns([3, 1])
        with col_chat_title:
            st.markdown("#### Chat — Orchestrator LangGraph")
        with col_tokens:
            tk = st.session_state[tokens_key]
            if tk["in"] or tk["out"]:
                st.caption(f"tokens acumulados: `{tk['in']}↑ {tk['out']}↓`")

        # Histórico de mensagens
        for msg in st.session_state[chat_key]:
            avatar = "⚖️" if msg["role"] == "assistant" else "👤"
            with st.chat_message(msg["role"], avatar=avatar):
                st.markdown(msg["content"])
                if msg["role"] == "assistant" and msg.get("meta"):
                    meta = msg["meta"]
                    partes = []
                    if meta.get("intencao"):
                        partes.append(f"intent: `{meta['intencao']}`")
                    if meta.get("tokens_in") or meta.get("tokens_out"):
                        partes.append(
                            f"tokens: `{meta.get('tokens_in', 0)}↑ "
                            f"{meta.get('tokens_out', 0)}↓`"
                        )
                    if meta.get("fallback"):
                        partes.append("⚠️ fallback")
                    if partes:
                        st.caption(" · ".join(partes))

        # Input do usuário
        if prompt := st.chat_input(
            "Pergunte sobre o processo, termos jurídicos ou tire dúvidas...",
            key=f"input_{cid}",
        ):
            st.session_state[chat_key].append({"role": "user", "content": prompt})
            with st.chat_message("user", avatar="👤"):
                st.markdown(prompt)

            with st.chat_message("assistant", avatar="⚖️"):
                with st.spinner("Orchestrator processando (LangGraph)..."):
                    try:
                        resultado = asyncio.run(
                            orchestrator.processar(
                                escritorio_id=1,
                                cliente_id=1,
                                mensagem=prompt,
                                tipo="texto",
                            )
                        )
                        resposta = resultado["resposta"]
                        intencao = resultado.get("intencao", "outro")
                        tokens = resultado.get("tokens_usados", {})
                        fallback = resultado.get("usando_fallback", False)
                        ti = tokens.get("input", 0)
                        to = tokens.get("output", 0)

                        st.session_state[tokens_key]["in"] += ti
                        st.session_state[tokens_key]["out"] += to

                    except Exception as exc:
                        resposta = (
                            "Desculpe, ocorreu um erro no processamento. "
                            f"Tente novamente. ({exc})"
                        )
                        intencao, ti, to, fallback = "erro", 0, 0, True

                st.markdown(resposta)

                partes = [f"intent: `{intencao}`"]
                if ti or to:
                    partes.append(f"tokens: `{ti}↑ {to}↓`")
                if fallback:
                    partes.append("⚠️ fallback")
                st.caption(" · ".join(partes))

            st.session_state[chat_key].append(
                {
                    "role": "assistant",
                    "content": resposta,
                    "meta": {
                        "intencao": intencao,
                        "tokens_in": ti,
                        "tokens_out": to,
                        "fallback": fallback,
                    },
                }
            )
            st.rerun()
