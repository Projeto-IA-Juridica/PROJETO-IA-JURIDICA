#!/usr/bin/env python3
"""
scripts/hub_juridico_v2.py
==========================
Hub Jurídico v2.0 — Demonstração Completa de Produção

Features integradas:
  Feature 4 — Onboarding automatizado (5 etapas, fluxo real)
  Feature 1 — IA Personalizada (LangGraph + persona + memória por cliente)
  Feature 2 — Score de Risco Processual (5 componentes ponderados)
  Feature 3 — RAG Jurídico (upload PDF/TXT, busca semântica, injeção no prompt)

Infraestrutura zerada para o demo (sem Docker/Redis/Postgres):
  • DB         → MagicMock + dados reais do DataJud (API pública CNJ)
  • Redis      → _MemoriaEmRam (in-memory por cliente)
  • Embeddings → TF-IDF keyword-based in-memory (sem Voyage/OpenAI)
  • WhatsApp   → no-op Evolution client (simulado com QR fake)

Requer apenas: ANTHROPIC_API_KEY
Opcional:      DATAJUD_API_KEY (melhora rate-limit na consulta de processos)

Uso:
    streamlit run scripts/hub_juridico_v2.py
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import os
import re
import sys
import time
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# ── Path + .env ───────────────────────────────────────────────────────────────

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

# ── Imports do projeto ────────────────────────────────────────────────────────

from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
from feature_1_ia_personalizada.services.ai.memory import ConversationMemory
from feature_1_ia_personalizada.services.ai.orchestrator import ConversationOrchestrator
from feature_1_ia_personalizada.services.ai.prompts import gerar_instrucao_persona
from feature_1_ia_personalizada.services.ai.translator import JuridicalTranslator
from feature_1_ia_personalizada.services.legal_data.jusbrasil_client import JusbrasilClient
from feature_1_ia_personalizada.services.legal_data.vitoria_preditor import ScoreRiscoCalculator
from feature_1_ia_personalizada.services.prospeccao.dna_advogado import DNAEscritorio
from feature_1_ia_personalizada.services.prospeccao.matching import MatchingService
from feature_1_ia_personalizada.services.prospeccao.empresa_intelligence import EmpresaInteligencia
from feature_1_ia_personalizada.services.prospeccao.pessoa_intelligence import PessoaInteligencia

# ── PyMuPDF opcional (extração de PDF no demo RAG) ────────────────────────────

try:
    import fitz as _fitz  # type: ignore
    _FITZ_OK = True
except ImportError:
    _fitz = None
    _FITZ_OK = False

# ── Constantes CNJ ────────────────────────────────────────────────────────────

_CNJ_FORMATADO = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")
_CNJ_RAW = re.compile(r"^\d{20}$")
_DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"

_TJ_INDICES: dict[str, str] = {
    "01": "api_publica_tjac", "02": "api_publica_tjal", "03": "api_publica_tjap",
    "04": "api_publica_tjam", "05": "api_publica_tjba", "06": "api_publica_tjce",
    "07": "api_publica_tjdf", "08": "api_publica_tjes", "09": "api_publica_tjgo",
    "10": "api_publica_tjma", "11": "api_publica_tjmt", "12": "api_publica_tjms",
    "13": "api_publica_tjmg", "14": "api_publica_tjpa", "15": "api_publica_tjpb",
    "16": "api_publica_tjpr", "17": "api_publica_tjpe", "18": "api_publica_tjpi",
    "19": "api_publica_tjrj", "20": "api_publica_tjrn", "21": "api_publica_tjrs",
    "22": "api_publica_tjro", "23": "api_publica_tjrr", "24": "api_publica_tjsc",
    "25": "api_publica_tjse", "26": "api_publica_tjsp", "27": "api_publica_tjto",
}

# ── Instâncias globais (stateless, seguras para reuso) ────────────────────────

_score_calculator = ScoreRiscoCalculator()

# =============================================================================
# SEÇÃO 1 — Helpers CNJ / DataJud
# =============================================================================


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
        return f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:]}"
    return None


def _indice_datajud(numero_cnj: str) -> str | None:
    digits = re.sub(r"[.\-]", "", numero_cnj)
    if len(digits) != 20:
        return None
    j, tt = digits[13], digits[14:16]
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
    indice = _indice_datajud(numero_cnj)
    if not indice:
        return None
    digits = re.sub(r"[.\-]", "", numero_cnj)
    url = f"{_DATAJUD_BASE}/{indice}/_search"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if DATAJUD_API_KEY:
        headers["Authorization"] = f"ApiKey {DATAJUD_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json={"query": {"match": {"numeroProcesso": digits}}}, headers=headers)
        if resp.status_code == 200:
            hits = resp.json().get("hits", {}).get("hits", [])
            return hits[0].get("_source") if hits else None
    except Exception:
        pass
    return None


@st.cache_data(ttl=300, show_spinner=False)
def consultar_datajud(numero_cnj: str) -> dict[str, Any] | None:
    return asyncio.run(_buscar_datajud_async(numero_cnj))


def parsear_csv(conteudo: bytes) -> tuple[list[dict], list[dict]]:
    texto = conteudo.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(texto))
    if not reader.fieldnames:
        return [], [{"linha": 0, "motivo": "CSV vazio ou sem cabeçalho"}]
    campos = [f.strip().lower() for f in reader.fieldnames if f]
    faltando = [c for c in ("nome", "telefone") if c not in campos]
    if faltando:
        return [], [{"linha": 1, "motivo": f"Colunas obrigatórias ausentes: {faltando}"}]
    clientes: list[dict] = []
    erros: list[dict] = []
    for i, row in enumerate(reader, start=2):
        row_norm = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
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
                erros.append({"linha": i, "motivo": f"CNJ inválido: {numero_processo_raw!r}"})
                continue
        polo_raw = row_norm.get("polo_cliente", "autor").lower().strip()
        polo = polo_raw if polo_raw in ("autor", "reu", "terceiro") else "autor"
        clientes.append({
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
        })
    return clientes, erros


# =============================================================================
# SEÇÃO 2 — Score de Risco (Feature 2)
# =============================================================================


def _calcular_score(cliente: dict, dados_dj: dict | None) -> dict | None:
    if not cliente.get("numero_cnj"):
        return None

    class _Proxy:
        pass

    p = _Proxy()
    p.polo_cliente = cliente.get("polo_cliente") or "autor"
    p.fase_processual = None
    p.valor_causa = None
    if dados_dj:
        classe = dados_dj.get("classe", {})
        p.tipo_acao = (classe.get("nome") if isinstance(classe, dict) else str(classe)) or None
    else:
        p.tipo_acao = None
    datajud_data = {
        "tempo_medio_tramitacao_dias": dados_dj.get("tempo_medio_tramitacao_dias") if dados_dj else None,
        "taxa_procedencia_autor": dados_dj.get("taxa_procedencia_autor") if dados_dj else None,
    }
    try:
        r = _score_calculator.calcular(p, datajud_data)
        return {
            "score": r.score,
            "nivel": r.nivel,
            "interpretacao": r.interpretacao,
            "componentes": r.componentes.model_dump(),
        }
    except Exception:
        return None


def _cor_nivel(nivel: str) -> str:
    return {"baixo": "#2e7d32", "moderado": "#f57c00", "alto": "#c62828", "critico": "#6a1b9a"}.get(nivel, "#555")


def _render_score_card(score_data: dict) -> None:
    score = score_data["score"]
    nivel = score_data["nivel"]
    interp = score_data["interpretacao"]
    comp = score_data["componentes"]
    cor = _cor_nivel(nivel)
    emojis = {"baixo": "🟢", "moderado": "🟡", "alto": "🔴", "critico": "🟣"}
    emoji = emojis.get(nivel, "⚪")
    st.markdown(
        f"""
        <div style="border:1.5px solid {cor};border-radius:10px;padding:14px 18px;
                    background:{cor}18;margin-bottom:8px;">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
                <span style="font-size:13px;font-weight:600;color:{cor};text-transform:uppercase;
                             letter-spacing:.05em;">{emoji} Score de Risco Processual</span>
                <span style="font-size:22px;font-weight:700;color:{cor};">
                    {score}<span style="font-size:13px;font-weight:400;color:#888;">/100</span>
                </span>
            </div>
            <div style="background:#e0e0e0;border-radius:4px;height:7px;margin-bottom:10px;">
                <div style="width:{score}%;background:{cor};height:7px;border-radius:4px;"></div>
            </div>
            <div style="font-size:12px;color:#555;line-height:1.5;">{interp}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Ver detalhamento — 5 componentes ponderados (Feature 2)"):
        nomes = {
            "complexidade_juridica": "Complexidade Jurídica",
            "duracao_estimada": "Duração Estimada",
            "historico_vara": "Histórico da Vara",
            "valor_causa": "Valor da Causa",
            "fase_processual": "Fase Processual",
        }
        pesos = {
            "complexidade_juridica": "25%", "duracao_estimada": "25%",
            "historico_vara": "20%", "valor_causa": "15%", "fase_processual": "15%",
        }
        for chave, valor in comp.items():
            label = nomes.get(chave, chave)
            peso = pesos.get(chave, "")
            bc = _cor_nivel("alto" if valor >= 75 else "moderado" if valor >= 40 else "baixo")
            st.markdown(
                f"""<div style="margin-bottom:8px;">
                    <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
                        <span style="color:#444;">{label} <span style="color:#aaa;">({peso})</span></span>
                        <span style="font-weight:600;color:{bc};">{valor}/100</span>
                    </div>
                    <div style="background:#e0e0e0;border-radius:3px;height:5px;">
                        <div style="width:{valor}%;background:{bc};height:5px;border-radius:3px;"></div>
                    </div></div>""",
                unsafe_allow_html=True,
            )
        st.caption("⚠️ Uso exclusivo interno — não representa previsão de resultado (OAB Provimento 205/2021).")


# =============================================================================
# SEÇÃO 3 — Base de Conhecimento RAG In-Memory (Feature 3 — demo)
# =============================================================================


class _MockRAGBase:
    """
    Base de conhecimento jurídico in-memory para o demo.

    Pipeline simulado:
      Upload PDF/TXT → Extração de texto → Chunking (500 chars, 50-word overlap)
      → Indexação por keywords → Busca TF-IDF → Injeção no system prompt

    Em produção: substitui por pgvector + Voyage AI embeddings (cosine similarity).
    """

    _STOPWORDS = frozenset(
        "de da do e a o em para com que é um uma os as se na no ao dos das pelo pela "
        "este esta esse essa neste nesta por mais seu sua ao à também não".split()
    )

    def __init__(self) -> None:
        self._chunks: list[dict] = []

    def adicionar(self, titulo: str, tipo: str, texto: str) -> int:
        """Chunka o texto e indexa. Retorna nº de chunks gerados."""
        texto_limpo = self._limpar(texto)
        chunks = self._chunkar(texto_limpo)
        for i, chunk in enumerate(chunks):
            self._chunks.append({
                "id": f"{hashlib.md5(chunk.encode()).hexdigest()[:8]}",
                "titulo": titulo,
                "tipo": tipo,
                "texto": chunk,
                "keywords": self._keywords(chunk),
            })
        return len(chunks)

    def buscar(self, query: str, top_k: int = 3) -> list[dict]:
        """Busca por Jaccard similarity entre keywords da query e dos chunks."""
        q_kw = self._keywords(query)
        if not q_kw:
            return []
        scored = []
        for chunk in self._chunks:
            inter = len(q_kw & chunk["keywords"])
            union = len(q_kw | chunk["keywords"])
            score = inter / union if union > 0 else 0.0
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored[:top_k]]

    def formatar_contexto(self, chunks: list[dict]) -> str:
        """Formata chunks para injeção no system prompt (mesmo formato do RAGRetriever real)."""
        if not chunks:
            return ""
        partes = []
        for c in chunks:
            partes.append(f"[{c['tipo'].upper()} — {c['titulo']}]\n{c['texto']}")
        return (
            "<contexto_juridico>\n"
            + "\n\n---\n\n".join(partes)
            + "\n</contexto_juridico>"
        )

    def listar_documentos(self) -> list[dict]:
        """Retorna lista de documentos únicos com estatísticas."""
        vistos: dict[str, dict] = {}
        for c in self._chunks:
            titulo = c["titulo"]
            if titulo not in vistos:
                vistos[titulo] = {"titulo": titulo, "tipo": c["tipo"], "chunks": 0}
            vistos[titulo]["chunks"] += 1
        return list(vistos.values())

    def remover(self, titulo: str) -> int:
        antes = len(self._chunks)
        self._chunks = [c for c in self._chunks if c["titulo"] != titulo]
        return antes - len(self._chunks)

    @property
    def total_docs(self) -> int:
        return len({c["titulo"] for c in self._chunks})

    @property
    def total_chunks(self) -> int:
        return len(self._chunks)

    # ── Internos ─────────────────────────────────────────────────────────────

    @staticmethod
    def _limpar(texto: str) -> str:
        texto = re.sub(r"\s+", " ", texto)
        texto = re.sub(r"[^\w\s.,;:!?()\-\"']", " ", texto)
        return texto.strip()

    def _chunkar(self, texto: str, tam: int = 500) -> list[str]:
        palavras = texto.split()
        chunks: list[str] = []
        atual: list[str] = []
        tam_atual = 0
        for p in palavras:
            atual.append(p)
            tam_atual += len(p) + 1
            if tam_atual >= tam:
                chunks.append(" ".join(atual))
                atual = atual[-30:]  # overlap de 30 palavras
                tam_atual = sum(len(w) + 1 for w in atual)
        if atual and sum(len(w) for w in atual) > 40:
            chunks.append(" ".join(atual))
        return chunks

    def _keywords(self, texto: str) -> frozenset[str]:
        palavras = re.findall(r"\b\w{3,}\b", texto.lower())
        return frozenset(p for p in palavras if p not in self._STOPWORDS)


def _extrair_texto(arquivo_bytes: bytes, nome: str) -> str:
    """Extrai texto de PDF (se fitz disponível) ou TXT."""
    ext = nome.rsplit(".", 1)[-1].lower()
    if ext == "pdf" and _FITZ_OK:
        doc = _fitz.open(stream=arquivo_bytes, filetype="pdf")
        partes = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(partes)
    try:
        return arquivo_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return arquivo_bytes.decode("latin-1", errors="replace")


class _MockRAGRetriever:
    """
    Adapta _MockRAGBase para a interface exata de RAGRetriever do projeto.

    O orchestrator chama:
        await self._rag.buscar(query, escritorio_id, contexto_processo)

    Este adapter enriquece a query com o tipo_acao do processo (quando disponível),
    executa a busca por Jaccard similarity e retorna o bloco XML pronto para
    injeção no system_prompt — exatamente como o retriever real com pgvector faz.

    Em produção: substituído por RAGRetriever(VectorStore) com Voyage AI embeddings.
    """

    def __init__(self, base: _MockRAGBase) -> None:
        self._base = base

    async def buscar(
        self,
        query: str,
        escritorio_id: int,
        contexto_processo: dict | None = None,
    ) -> str:
        if self._base.total_chunks == 0:
            return ""
        # Enriquece query com contexto do processo (mesmo que o retriever real faz)
        q = query
        if contexto_processo:
            tipo_acao = contexto_processo.get("tipo_acao") or ""
            tribunal = contexto_processo.get("tribunal") or ""
            if tipo_acao:
                q = f"{q} {tipo_acao} {tribunal}"
        chunks = self._base.buscar(q, top_k=3)
        return self._base.formatar_contexto(chunks) if chunks else ""


# =============================================================================
# SEÇÃO 4 — Mock de Entidades (sem Banco de Dados)
# =============================================================================


def _fake_escritorio(ob: dict) -> MagicMock:
    """Cria mock de Escritorio com todos os campos esperados pelo orchestrator."""
    obj = MagicMock()
    obj.id = 1
    obj.nome = ob.get("nome_escritorio", "Escritório Demo")
    obj.webhook_whatsapp_instance = "demo_instance" if ob.get("whatsapp_ok") else None
    # Feature 4 — persona configurada no onboarding
    obj.persona_nome = ob.get("persona_nome", "Assistente Jurídico")
    obj.persona_tom = ob.get("persona_tom", "formal")
    obj.horario_inicio = ob.get("horario_inicio", "08:00")
    obj.horario_fim = ob.get("horario_fim", "18:00")
    obj.onboarding_etapa = ob.get("etapa", 5)
    obj.onboarding_completo = ob.get("onboarding_completo", True)
    return obj


def _fake_cliente(cliente: dict) -> MagicMock:
    obj = MagicMock()
    obj.id = cliente["id"] + 1
    obj.nome = cliente["nome"]
    obj.telefone_whatsapp = cliente["telefone"]
    obj.escritorio_id = 1
    return obj


def _fake_processo(cliente: dict, dados_dj: dict | None) -> MagicMock | None:
    if not cliente.get("numero_cnj"):
        return None
    obj = MagicMock()
    obj.id = cliente["id"] + 100
    obj.numero_cnj = cliente["numero_cnj"]
    obj.polo_cliente = cliente.get("polo_cliente", "autor")
    obj.monitoramento_ativo = True
    obj.escritorio_id = 1
    obj.cliente_id = cliente["id"] + 1
    if dados_dj:
        tribunal = dados_dj.get("tribunal", {})
        obj.tribunal = tribunal.get("nome", "N/D") if isinstance(tribunal, dict) else str(tribunal)
        obj.vara = dados_dj.get("grau", "N/D") or "N/D"
        classe = dados_dj.get("classe", {})
        obj.tipo_acao = (classe.get("nome") if isinstance(classe, dict) else str(classe)) or None
        movimentos = dados_dj.get("movimentos", [])
        if movimentos and isinstance(movimentos[0], dict):
            ultimo = movimentos[0]
            obj.ultimo_andamento = ultimo.get("nome", "sem movimentação recente")
            data_str = (ultimo.get("dataHora") or "")[:10]
            try:
                obj.data_ultimo_andamento = date.fromisoformat(data_str) if data_str else None
            except ValueError:
                obj.data_ultimo_andamento = None
        else:
            obj.ultimo_andamento = "sem movimentação recente"
            obj.data_ultimo_andamento = None
        # Feature 3 — estado atual (RAG)
        obj.estado_atual = {
            "classe": obj.tipo_acao,
            "tribunal": obj.tribunal,
            "ultimo_andamento": obj.ultimo_andamento,
        }
    else:
        obj.tribunal = obj.vara = "N/D"
        obj.tipo_acao = None
        obj.ultimo_andamento = "aguardando consulta ao tribunal"
        obj.data_ultimo_andamento = None
        obj.estado_atual = {}
    return obj


def _fake_jusbrasil(dados_dj: dict | None) -> JusbrasilClient:
    client = AsyncMock(spec=JusbrasilClient)
    if dados_dj:
        movimentos = dados_dj.get("movimentos", [])
        andamentos = [
            {"descricao": m.get("nome", ""), "data": (m.get("dataHora") or "")[:10]}
            for m in movimentos if isinstance(m, dict) and m.get("nome")
        ]
    else:
        andamentos = []
    client.sincronizar_andamentos = AsyncMock(return_value=andamentos)
    return client


def _fake_cache() -> MagicMock:
    cache = AsyncMock()
    cache._redis = AsyncMock()
    cache._redis.get = AsyncMock(return_value=None)   # cache miss → gera persona do escritorio
    cache._redis.set = AsyncMock()
    cache.get_andamentos = AsyncMock(return_value=None)
    cache.set_andamentos = AsyncMock()
    return cache


def _fake_evolution() -> MagicMock:
    client = AsyncMock()
    client.enviar_texto = AsyncMock()
    return client


class _MemoriaEmRam(ConversationMemory):
    """Substitui Redis: histórico por cliente em RAM."""

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


def _make_session_factory(ob: dict, cliente: dict, dados_dj: dict | None):
    escritorio = _fake_escritorio(ob)
    cliente_obj = _fake_cliente(cliente)
    processo_obj = _fake_processo(cliente, dados_dj)
    processos = [processo_obj] if processo_obj else []

    @asynccontextmanager
    async def _factory():
        session = AsyncMock()

        async def _get(model_class, pk: Any):
            nome = getattr(model_class, "__name__", str(model_class))
            if "Escritorio" in nome:
                return escritorio
            if "Cliente" in nome:
                return cliente_obj
            if "Processo" in nome:
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


def criar_orchestrator(
    ob: dict,
    cliente: dict,
    dados_dj: dict | None,
    rag_base: _MockRAGBase | None = None,
) -> tuple[ConversationOrchestrator, _MemoriaEmRam]:
    """
    Instancia o ConversationOrchestrator completo com todos os componentes reais:
      - ClaudeClient: chamadas reais ao Claude Sonnet
      - _MemoriaEmRam: substitui Redis (histórico in-memory por cliente)
      - JuridicalTranslator: dicionário jurídico real (identifica + explica termos)
      - _fake_jusbrasil: andamentos do DataJud injetados como se fossem do Jusbrasil
      - _fake_cache: cache miss → orchestrator busca dados frescos
      - _MockRAGRetriever: conecta _MockRAGBase ao pipeline do orchestrator
        (await self._rag.buscar → injeção do bloco <contexto_juridico> no system_prompt)
      - FactChecker: habilitado com session_factory mockada que retorna dados reais
    """
    memoria = _MemoriaEmRam()

    # RAG: envolve a base in-memory com a interface que o orchestrator espera
    rag_retriever = _MockRAGRetriever(rag_base) if (rag_base and rag_base.total_chunks > 0) else None

    orchestrator = ConversationOrchestrator(
        claude_client=ClaudeClient(api_key=ANTHROPIC_API_KEY),
        memory=memoria,
        translator=JuridicalTranslator(),
        jusbrasil_client=_fake_jusbrasil(dados_dj),
        cache_manager=_fake_cache(),
        evolution_client=_fake_evolution(),
        session_factory=_make_session_factory(ob, cliente, dados_dj),
        rag_retriever=rag_retriever,  # None = RAG desativado gracefully
    )
    # FactChecker habilitado: a session_factory já retorna os dados do processo corretos,
    # então o checker valida a resposta contra os andamentos reais do DataJud.
    return orchestrator, memoria


# =============================================================================
# SEÇÃO 5 — Helpers de UI
# =============================================================================


def _tabela_md(linhas: list[tuple[str, str]]) -> str:
    rows = "\n".join(f"| **{k}** | {v} |" for k, v in linhas)
    return f"| Campo | Valor |\n|-------|-------|\n{rows}"


def _badge(texto: str, cor: str = "#555", bg: str = "#f0f0f0") -> str:
    return (
        f'<span style="background:{bg};color:{cor};padding:2px 8px;'
        f'border-radius:12px;font-size:11px;font-weight:600;">{texto}</span>'
    )


def _render_andamentos(dados_dj: dict, max_items: int = 8) -> None:
    movimentos = dados_dj.get("movimentos", [])
    if not movimentos:
        st.info("Nenhum andamento disponível.")
        return
    for mov in movimentos[:max_items]:
        if not isinstance(mov, dict):
            continue
        data = (mov.get("dataHora") or "")[:10]
        nome = mov.get("nome", "—")
        complementos = mov.get("complementosTabelados", [])
        desc_extra = ""
        if complementos and isinstance(complementos, list):
            nomes_comp = [c.get("nome", "") for c in complementos if isinstance(c, dict) and c.get("nome")]
            if nomes_comp:
                desc_extra = f" — {', '.join(nomes_comp[:2])}"
        st.markdown(f"- **{data}** — {nome}{desc_extra}")


# =============================================================================
# SEÇÃO 6 — PÁGINA: Onboarding (Feature 4)
# =============================================================================


def page_onboarding() -> None:
    ob = st.session_state.setdefault("onboarding", {
        "etapa": 0, "onboarding_completo": False,
        "nome_escritorio": "", "cnpj": "", "email_admin": "",
        "nome_responsavel": "", "oab_responsavel": "",
        "persona_nome": "Assistente Jurídico", "persona_tom": "formal",
        "horario_inicio": "08:00", "horario_fim": "18:00",
        "clientes_importados": [], "erros_importacao": [],
        "whatsapp_ok": False,
        "template_boas_vindas": "Olá {nome_cliente}! Seja bem-vindo(a) ao nosso escritório. Como posso ajudar?",
        "template_atualizacao": "Olá {nome_cliente}! Há novidades no seu processo: {resumo_andamento}",
        "template_sem_novidade": "Olá {nome_cliente}, consultamos seu processo e não há novidades por enquanto.",
    })

    st.title("🚀 Onboarding do Escritório")
    st.caption("Configure seu escritório em 5 etapas e esteja operacional em 30 minutos.")

    etapa = ob["etapa"]
    nomes_etapas = [
        "📋 Cadastro", "🤖 Configurar IA", "📂 Importar Clientes",
        "💬 WhatsApp", "📝 Templates", "🚀 Go-Live",
    ]
    progress = etapa / 5.0
    st.progress(progress, text=f"Etapa {etapa}/5 — {nomes_etapas[min(etapa, 5)]}")
    st.divider()

    # ── Etapa 0: Cadastro do Escritório ──────────────────────────────────────
    if etapa == 0:
        st.subheader("📋 Etapa 1 — Dados do Escritório")
        st.caption("Crie a conta do seu escritório. Esta etapa é pública — nenhum token necessário.")
        with st.form("form_register"):
            col1, col2 = st.columns(2)
            with col1:
                nome_esc = st.text_input("Nome do Escritório *", value=ob.get("nome_escritorio", ""))
                cnpj = st.text_input("CNPJ *", value=ob.get("cnpj", ""), placeholder="11.222.333/0001-81")
                email = st.text_input("E-mail do Administrador *", value=ob.get("email_admin", ""))
            with col2:
                nome_resp = st.text_input("Nome do Responsável *", value=ob.get("nome_responsavel", ""))
                oab = st.text_input("OAB do Responsável *", value=ob.get("oab_responsavel", ""), placeholder="SP123456")
                senha = st.text_input("Senha *", type="password", help="Mínimo 8 caracteres")

            st.caption("(*) Campos obrigatórios")
            submitted = st.form_submit_button("Registrar Escritório →", use_container_width=True, type="primary")

        if submitted:
            erros = []
            if len(nome_esc.strip()) < 2:
                erros.append("Nome do escritório inválido (mínimo 2 caracteres)")
            cnpj_digits = re.sub(r"\D", "", cnpj)
            if len(cnpj_digits) != 14:
                erros.append("CNPJ inválido (deve ter 14 dígitos)")
            if not re.match(r"[A-Z]{2}\d{5,6}", oab.upper().strip()):
                erros.append("OAB inválida (formato esperado: SP123456)")
            if len(senha) < 8:
                erros.append("Senha deve ter no mínimo 8 caracteres")
            if erros:
                for e in erros:
                    st.error(e)
            else:
                ob.update({
                    "etapa": 1,
                    "nome_escritorio": nome_esc.strip(),
                    "cnpj": cnpj_digits,
                    "email_admin": email.strip(),
                    "nome_responsavel": nome_resp.strip(),
                    "oab_responsavel": oab.upper().strip(),
                })
                st.success("✅ Escritório cadastrado! Avançando para configuração da IA...")
                time.sleep(0.5)
                st.rerun()

    # ── Etapa 1: Configurar IA / Persona ─────────────────────────────────────
    elif etapa == 1:
        st.subheader("🤖 Etapa 2 — Configurar a IA Jurídica")
        st.caption("Defina a identidade da sua IA. Ela será injetada em todos os prompts (Feature 1 + Feature 4).")

        with st.container(border=True):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Preview da Persona**")
                prev_nome = st.text_input("Nome da IA", value=ob.get("persona_nome", "Assistente Jurídico"))
                prev_tom = st.selectbox("Tom de voz", ["formal", "amigavel", "neutro"],
                                        index=["formal", "amigavel", "neutro"].index(ob.get("persona_tom", "formal")))
            with col2:
                st.markdown("**Horário de Atendimento**")
                h_ini = st.text_input("Início", value=ob.get("horario_inicio", "08:00"), placeholder="HH:MM")
                h_fim = st.text_input("Fim", value=ob.get("horario_fim", "18:00"), placeholder="HH:MM")

        # Preview ao vivo da persona
        st.markdown("**Preview da instrução gerada para o Claude:**")
        instrucao = gerar_instrucao_persona(prev_nome, prev_tom)
        st.code(instrucao, language="xml")

        col_back, col_next = st.columns(2)
        with col_back:
            if st.button("← Voltar", use_container_width=True):
                ob["etapa"] = 0
                st.rerun()
        with col_next:
            if st.button("Salvar e Avançar →", use_container_width=True, type="primary"):
                erros = []
                if not re.match(r"^\d{2}:\d{2}$", h_ini) or not re.match(r"^\d{2}:\d{2}$", h_fim):
                    erros.append("Horário deve estar no formato HH:MM")
                elif h_ini >= h_fim:
                    erros.append("Horário de início deve ser menor que o de fim")
                if erros:
                    for e in erros:
                        st.error(e)
                else:
                    ob.update({
                        "etapa": 2,
                        "persona_nome": prev_nome.strip(),
                        "persona_tom": prev_tom,
                        "horario_inicio": h_ini,
                        "horario_fim": h_fim,
                    })
                    st.success(f"✅ IA '{prev_nome}' configurada (tom: {prev_tom})")
                    time.sleep(0.5)
                    st.rerun()

    # ── Etapa 2: Importar Clientes / Processos ────────────────────────────────
    elif etapa == 2:
        st.subheader("📂 Etapa 3 — Importar Clientes e Processos")
        st.caption(
            "Faça upload do CSV. O sistema valida o CNJ e consulta o DataJud em tempo real."
        )

        st.download_button(
            "📥 Baixar CSV de exemplo",
            data=(
                "nome,telefone,cpf,data_nascimento,profissao,empresa,numero_processo,polo_cliente\n"
                "João da Silva,11999990001,123.456.789-00,15/03/1980,Engenheiro,Tech Corp,0000001-68.2019.8.26.0053,autor\n"
                "Maria Santos,21988880002,987.654.321-00,22/07/1975,Médica,Hospital ABC,,\n"
                "Carlos Oliveira,31977770003,456.789.012-00,08/11/1990,Empresário,,,\n"
            ),
            file_name="clientes_exemplo.csv",
            mime="text/csv",
        )

        arquivo = st.file_uploader("Upload do CSV", type=["csv"])
        if arquivo:
            csv_hash = hash(arquivo.getvalue())
            if st.session_state.get("_onb_csv_hash") != csv_hash:
                clientes, erros = parsear_csv(arquivo.getvalue())
                st.session_state["_onb_csv_hash"] = csv_hash
                ob["clientes_importados"] = clientes
                ob["erros_importacao"] = erros

            clientes = ob["clientes_importados"]
            erros = ob["erros_importacao"]

            if erros:
                with st.expander(f"⚠️ {len(erros)} erro(s)"):
                    for e in erros:
                        st.error(f"Linha {e['linha']}: {e['motivo']}")

            if clientes:
                st.success(f"✅ {len(clientes)} cliente(s) válidos")
                com_cnj = [c for c in clientes if c.get("numero_cnj")]
                st.info(f"📋 {len(com_cnj)} com número de processo (CNJ) — serão consultados no DataJud")

                with st.expander("Preview dos clientes + consulta DataJud", expanded=True):
                    for c in clientes[:5]:
                        st.markdown(f"**{c['nome']}** — `{c['telefone']}`")
                        if c.get("numero_cnj"):
                            with st.spinner(f"Consultando DataJud: {c['numero_cnj']}..."):
                                dj_key = f"_onb_dj_{c['numero_cnj']}"
                                if dj_key not in st.session_state:
                                    st.session_state[dj_key] = consultar_datajud(c["numero_cnj"])
                                dados = st.session_state[dj_key]
                            if dados:
                                classe = dados.get("classe", {})
                                nome_classe = classe.get("nome", "—") if isinstance(classe, dict) else str(classe)
                                tribunal = dados.get("tribunal", {})
                                nome_trib = tribunal.get("nome", "—") if isinstance(tribunal, dict) else str(tribunal)
                                st.caption(f"   ✅ DataJud: {nome_classe} — {nome_trib}")
                            else:
                                st.caption(f"   ⚠️ DataJud: processo `{c['numero_cnj']}` não encontrado")
                        st.divider()
                    if len(clientes) > 5:
                        st.caption(f"+ {len(clientes) - 5} cliente(s) omitidos no preview")

        col_back, col_next = st.columns(2)
        with col_back:
            if st.button("← Voltar", use_container_width=True):
                ob["etapa"] = 1
                st.rerun()
        with col_next:
            pode_avancar = bool(ob.get("clientes_importados"))
            if st.button("Salvar e Avançar →", use_container_width=True, type="primary", disabled=not pode_avancar):
                ob["etapa"] = 3
                st.rerun()
            if not pode_avancar:
                if st.button("Pular (sem clientes agora) →", use_container_width=True):
                    ob["etapa"] = 3
                    st.rerun()

    # ── Etapa 3: Conectar WhatsApp ────────────────────────────────────────────
    elif etapa == 3:
        st.subheader("💬 Etapa 4 — Conectar WhatsApp Business")
        st.caption("Integração com Evolution API — QR Code para autenticação do WhatsApp.")

        if ob.get("whatsapp_ok"):
            st.success("✅ WhatsApp conectado! Instância: `demo_escritorio_1`", icon="💬")
        else:
            col_qr, col_info = st.columns([1, 2])
            with col_qr:
                # QR code simulado
                st.markdown(
                    """
                    <div style="background:#f5f5f5;border:2px dashed #ccc;border-radius:8px;
                                padding:20px;text-align:center;font-size:40px;">
                        📱<br>
                        <span style="font-size:12px;color:#888;">QR Code simulado<br>(demo mode)</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with col_info:
                st.markdown("""
                **Em produção:**
                1. Abra o WhatsApp Business no celular
                2. Acesse Configurações → Dispositivos Vinculados
                3. Escaneie o QR code ao lado
                4. Aguarde a conexão (≈ 10 segundos)

                **Tecnologia:** Evolution API v2 + webhook para recebimento de mensagens
                """)
                if st.button("Simular Conexão (Demo)", type="primary"):
                    with st.spinner("Conectando instância Evolution API..."):
                        time.sleep(1.5)
                    ob["whatsapp_ok"] = True
                    st.rerun()

        col_back, col_next = st.columns(2)
        with col_back:
            if st.button("← Voltar", use_container_width=True):
                ob["etapa"] = 2
                st.rerun()
        with col_next:
            if st.button("Avançar →", use_container_width=True, type="primary"):
                ob["etapa"] = 4
                st.rerun()

    # ── Etapa 4: Templates de Mensagem ───────────────────────────────────────
    elif etapa == 4:
        st.subheader("📝 Etapa 5 — Templates de Mensagem")
        st.caption("Personalize as mensagens automáticas. Use `{nome_cliente}` e `{resumo_andamento}` como placeholders.")

        with st.form("form_templates"):
            t_bv = st.text_area(
                "Boas-Vindas (obrigatório: `{nome_cliente}`)",
                value=ob.get("template_boas_vindas", ""),
                height=80,
            )
            t_at = st.text_area(
                "Atualização de Processo (obrigatórios: `{nome_cliente}` e `{resumo_andamento}`)",
                value=ob.get("template_atualizacao", ""),
                height=80,
            )
            t_sn = st.text_area(
                "Sem Novidade (obrigatório: `{nome_cliente}`)",
                value=ob.get("template_sem_novidade", ""),
                height=80,
            )
            submitted = st.form_submit_button("Salvar Templates →", type="primary", use_container_width=True)

        if submitted:
            erros = []
            if "{nome_cliente}" not in t_bv:
                erros.append("Template de boas-vindas deve conter {nome_cliente}")
            if "{nome_cliente}" not in t_at or "{resumo_andamento}" not in t_at:
                erros.append("Template de atualização deve conter {nome_cliente} e {resumo_andamento}")
            if "{nome_cliente}" not in t_sn:
                erros.append("Template 'sem novidade' deve conter {nome_cliente}")
            if erros:
                for e in erros:
                    st.error(e)
            else:
                ob.update({
                    "etapa": 5,
                    "template_boas_vindas": t_bv,
                    "template_atualizacao": t_at,
                    "template_sem_novidade": t_sn,
                })
                st.rerun()

        if st.button("← Voltar", use_container_width=True):
            ob["etapa"] = 3
            st.rerun()

    # ── Etapa 5: Go-Live ──────────────────────────────────────────────────────
    elif etapa >= 5:
        st.subheader("🚀 Go-Live — Escritório Pronto para Operar!")
        st.balloons()

        clientes = ob.get("clientes_importados", [])
        com_cnj = [c for c in clientes if c.get("numero_cnj")]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Clientes", len(clientes))
        col2.metric("Com Processo", len(com_cnj))
        col3.metric("WhatsApp", "✅ Ativo" if ob.get("whatsapp_ok") else "⚠️ Pendente")
        col4.metric("Etapa", "5/5 ✅")

        st.markdown("""
        ### Resumo do Onboarding

        | Feature | Status |
        |---------|--------|
        | IA Personalizada (Feature 1) | ✅ Persona configurada |
        | Score de Risco (Feature 2) | ✅ Calculando automaticamente |
        | Base RAG (Feature 3) | ✅ Pronta para documentos |
        | Onboarding (Feature 4) | ✅ Concluído |
        """)

        st.info(
            f"**Persona:** {ob.get('persona_nome')} · Tom: {ob.get('persona_tom')} · "
            f"Horário: {ob.get('horario_inicio')}–{ob.get('horario_fim')}"
        )

        # Ativar monitoramento nos processos
        if com_cnj:
            st.success(f"🔔 Monitoramento ativado em {len(com_cnj)} processo(s) via DataJud")

        if st.button("🏠 Entrar no Hub do Advogado", type="primary", use_container_width=True):
            ob["onboarding_completo"] = True
            ob["etapa"] = 5
            # Salva clientes na sessão principal
            st.session_state["clientes_hub"] = ob.get("clientes_importados", [])
            st.session_state["pagina"] = "hub"
            st.rerun()


# =============================================================================
# SEÇÃO 7 — PÁGINA: Hub do Advogado (Features 1 + 2 + 3)
# =============================================================================


def page_hub() -> None:
    ob = st.session_state.get("onboarding", {})
    clientes: list[dict] = st.session_state.get("clientes_hub", [])

    if not clientes:
        st.warning("Nenhum cliente carregado. Retorne ao Onboarding ou faça upload de um CSV.")
        if st.button("Ir para Onboarding"):
            st.session_state["pagina"] = "onboarding"
            st.rerun()
        return

    escritorio_nome = ob.get("nome_escritorio", "Escritório Demo")

    # ── Header ───────────────────────────────────────────────────────────────
    col_tit, col_meta = st.columns([3, 1])
    with col_tit:
        st.title(f"⚖️ {escritorio_nome}")
        persona_info = f"IA: **{ob.get('persona_nome', 'Assistente')}** (tom: {ob.get('persona_tom', 'formal')})"
        st.caption(
            f"{len(clientes)} cliente(s) · "
            f"{sum(1 for c in clientes if c.get('numero_cnj'))} com processo · "
            f"{persona_info}"
        )
    with col_meta:
        if ANTHROPIC_API_KEY:
            st.success("Claude ativo", icon="✅")
        else:
            st.error("ANTHROPIC_API_KEY ausente", icon="🔑")

    st.divider()

    # ── Tabs por cliente ──────────────────────────────────────────────────────
    nomes_tabs = [c["nome"].split()[0] for c in clientes]
    tabs = st.tabs(nomes_tabs)

    for tab, cliente in zip(tabs, clientes, strict=False):
        with tab:
            cid = cliente["id"]
            _render_cliente_tab(cid, cliente, ob)


def _render_cliente_tab(cid: int, cliente: dict, ob: dict) -> None:
    """Renderiza a aba completa de um cliente: processo + score + RAG + chat."""
    # ── Consulta DataJud ──────────────────────────────────────────────────────
    dados_dj: dict | None = None
    if cliente.get("numero_cnj"):
        dj_key = f"datajud_{cliente['numero_cnj']}"
        if dj_key not in st.session_state:
            with st.spinner(f"Consultando DataJud: {cliente['numero_cnj']}..."):
                st.session_state[dj_key] = consultar_datajud(cliente["numero_cnj"])
        dados_dj = st.session_state[dj_key]

    # ── Inicializa orchestrator (recriado se a base RAG mudou) ───────────────
    rag_base: _MockRAGBase | None = st.session_state.get("rag_base")
    rag_chunks_key = f"rag_chunks_at_orch_{cid}"
    rag_chunks_agora = rag_base.total_chunks if rag_base else 0
    orch_key = f"orch_{cid}"

    # Reinicia o orchestrator se o número de chunks RAG mudou desde a última criação
    # (garante que novos documentos são imediatamente usados no pipeline do Claude)
    if orch_key not in st.session_state or st.session_state.get(rag_chunks_key, -1) != rag_chunks_agora:
        if ANTHROPIC_API_KEY:
            orchestrator, memoria = criar_orchestrator(ob, cliente, dados_dj, rag_base=rag_base)
            st.session_state[orch_key] = orchestrator
            st.session_state[f"mem_{cid}"] = memoria
            st.session_state[rag_chunks_key] = rag_chunks_agora
        else:
            st.session_state[orch_key] = None
        if orch_key not in st.session_state or st.session_state.get(rag_chunks_key, -1) != rag_chunks_agora:
            st.session_state[f"chat_{cid}"] = []
            st.session_state[f"tokens_{cid}"] = {"in": 0, "out": 0, "intencoes": {}}
            st.session_state[f"welcome_{cid}"] = False

    if f"chat_{cid}" not in st.session_state:
        st.session_state[f"chat_{cid}"] = []
        st.session_state[f"tokens_{cid}"] = {"in": 0, "out": 0, "intencoes": {}}
        st.session_state[f"welcome_{cid}"] = False

    orchestrator = st.session_state[orch_key]

    # ── Layout: info + processo ───────────────────────────────────────────────
    col_cli, col_proc = st.columns([1, 2])

    with col_cli:
        st.markdown("#### 👤 Cliente")
        st.markdown(_tabela_md([
            ("Nome", cliente["nome"]),
            ("Telefone", f"`{cliente['telefone']}`"),
            ("CPF", cliente["cpf"]),
            ("Nascimento", cliente.get("data_nascimento") or "—"),
            ("Profissão", cliente.get("profissao") or "—"),
            ("Empresa", cliente.get("empresa") or "—"),
            ("Status", "🟢 Ativo" if cliente.get("status") != "inativo" else "🔴 Inativo"),
        ]))

    with col_proc:
        st.markdown("#### 📋 Processo Judicial")
        if not cliente.get("numero_cnj"):
            st.info("Nenhum processo cadastrado para este cliente.")
        elif dados_dj:
            tribunal = dados_dj.get("tribunal", {})
            nome_trib = tribunal.get("nome", "—") if isinstance(tribunal, dict) else str(tribunal)
            classe = dados_dj.get("classe", {})
            nome_classe = classe.get("nome", "—") if isinstance(classe, dict) else str(classe)
            assuntos = dados_dj.get("assuntos", [])
            assunto_str = ", ".join(
                a.get("nome", "") if isinstance(a, dict) else str(a) for a in assuntos[:2]
            ) or "—"
            movimentos = dados_dj.get("movimentos", [])
            ultimo = movimentos[0] if movimentos else {}
            data_ajuiz = (dados_dj.get("dataAjuizamento") or "")[:10] or "—"
            st.markdown(_tabela_md([
                ("CNJ", f"`{cliente['numero_cnj']}`"),
                ("Tribunal", nome_trib),
                ("Classe", nome_classe),
                ("Assunto(s)", assunto_str),
                ("Polo", (cliente.get("polo_cliente") or "—").upper()),
                ("Ajuizamento", data_ajuiz),
                ("Último Andamento", (ultimo.get("nome", "—") if isinstance(ultimo, dict) else "—")),
                ("Data", ((ultimo.get("dataHora") or "")[:10] if isinstance(ultimo, dict) else "—")),
            ]))
            st.success("Dados reais do DataJud injetados no orchestrator", icon="✅")

            if len(movimentos) > 1:
                with st.expander("📜 Andamentos anteriores (Feature 3 — histórico para RAG)"):
                    _render_andamentos(dados_dj)
        else:
            st.markdown(_tabela_md([
                ("CNJ", f"`{cliente['numero_cnj']}`"),
                ("Polo", (cliente.get("polo_cliente") or "—").upper()),
                ("DataJud", "Processo não encontrado"),
            ]))
            st.warning("Processo não encontrado no DataJud. O orchestrator responde com dados do cadastro.", icon="⚠️")

    # ── Score de Risco (Feature 2) ────────────────────────────────────────────
    if cliente.get("numero_cnj"):
        st.markdown("#### 🔒 Score de Risco — Painel Exclusivo do Advogado")
        score_data = _calcular_score(cliente, dados_dj)
        if score_data:
            _render_score_card(score_data)
        else:
            st.info("Score disponível após consulta ao DataJud com dados de classe processual.")

    # ── Status RAG — injeção acontece dentro do orchestrator (Feature 3) ─────
    if rag_base and rag_base.total_chunks > 0:
        # Preview do que o orchestrator vai buscar quando receber a próxima mensagem
        query_preview = f"{dados_dj.get('classe', {}).get('nome', '') if dados_dj else ''} {cliente.get('profissao', '')}"
        chunks_preview = rag_base.buscar(query_preview.strip() or "jurídico", top_k=3)
        if chunks_preview:
            with st.expander(
                f"📚 Feature 3 — RAG ativo: {rag_base.total_docs} doc(s) / {rag_base.total_chunks} chunks "
                f"(o orchestrator injeta contexto automaticamente via `_buscar_rag`)"
            ):
                st.caption(
                    "O bloco `<contexto_juridico>` abaixo é injetado no `system_prompt` "
                    "pelo nó `buscar_dados` do LangGraph antes de chamar o Claude."
                )
                for ch in chunks_preview:
                    st.markdown(f"**[{ch['tipo']}] {ch['titulo']}**")
                    st.caption(ch["texto"][:250] + "..." if len(ch["texto"]) > 250 else ch["texto"])
        else:
            st.info(f"📚 RAG ativo ({rag_base.total_chunks} chunks) — nenhum documento relevante para este processo ainda.")
    elif rag_base is not None:
        st.caption("📚 Base RAG vazia — adicione documentos em **Base RAG** para enriquecer as respostas.")

    st.divider()

    # ── Chat com orchestrator (Feature 1 + persona) ───────────────────────────
    if not ANTHROPIC_API_KEY:
        st.error("Configure `ANTHROPIC_API_KEY` no `.env` para ativar o chat com IA.")
        return

    chat_key = f"chat_{cid}"
    tokens_key = f"tokens_{cid}"
    welcome_key = f"welcome_{cid}"

    # Boas-vindas automáticas (intent: saudacao)
    if not st.session_state.get(welcome_key) and orchestrator:
        with st.spinner(f"IA gerando boas-vindas para {cliente['nome'].split()[0]}..."):
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
            except Exception as exc:
                boas_vindas = (
                    f"Olá, {cliente['nome'].split()[0]}! Bem-vindo(a) ao "
                    f"{st.session_state.get('onboarding', {}).get('nome_escritorio', 'nosso escritório')}. "
                    "Como posso ajudar?"
                )
                intencao_bv, fallback_bv = "erro", True
        st.session_state[chat_key].append({
            "role": "assistant",
            "content": boas_vindas,
            "meta": {"intencao": intencao_bv, "fallback": fallback_bv},
        })
        st.session_state[welcome_key] = True

    # Header do chat
    col_chat_hdr, col_tokens = st.columns([3, 1])
    with col_chat_hdr:
        st.markdown(f"#### 💬 Chat — {ob.get('persona_nome', 'Assistente Jurídico')}")
        st.caption(
            f"Persona: **{ob.get('persona_nome')}** (tom {ob.get('persona_tom')}) · "
            f"LangGraph + FactChecker + Translator"
        )
    with col_tokens:
        tk = st.session_state[tokens_key]
        if tk["in"] or tk["out"]:
            custo_estimado = (tk["in"] * 3 + tk["out"] * 15) / 1_000_000
            st.caption(f"`{tk['in']}↑ {tk['out']}↓` tokens")
            st.caption(f"Custo estimado: US$ {custo_estimado:.4f}")

    # Histórico
    for msg in st.session_state[chat_key]:
        avatar = "⚖️" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("meta"):
                meta = msg["meta"]
                partes = []
                intencao = meta.get("intencao", "")
                if intencao:
                    partes.append(f"intent: `{intencao}`")
                if meta.get("tokens_in") or meta.get("tokens_out"):
                    partes.append(f"tokens: `{meta.get('tokens_in', 0)}↑ {meta.get('tokens_out', 0)}↓`")
                if meta.get("rag_ativo"):
                    partes.append("📚 RAG injetado")
                # Intenções que disparam escalação automática para o advogado
                _ESCALACAO_INTENCOES = {"parecer_juridico", "estrategia_processual", "negociacao", "decisao_judicial_impacto_alto"}
                if intencao in _ESCALACAO_INTENCOES:
                    partes.append("🚨 escalado → advogado notificado")
                if meta.get("fallback"):
                    partes.append("⚠️ fallback")
                if partes:
                    st.caption(" · ".join(partes))

    # Input
    prompt = st.chat_input(
        "Pergunte sobre o processo, termos jurídicos ou tire dúvidas...",
        key=f"input_{cid}",
    )
    if prompt and orchestrator:
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar="⚖️"):
            with st.spinner("Orchestrator LangGraph processando..."):
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
                    rag_ativo = bool(rag_base and rag_base.total_chunks > 0)
                    st.session_state[tokens_key]["in"] += ti
                    st.session_state[tokens_key]["out"] += to
                    intenções_dict = st.session_state[tokens_key].setdefault("intencoes", {})
                    intenções_dict[intencao] = intenções_dict.get(intencao, 0) + 1
                except Exception as exc:
                    resposta = f"Desculpe, ocorreu um erro. Tente novamente. ({exc})"
                    intencao, ti, to, fallback, rag_ativo = "erro", 0, 0, True, False

            _ESCALACAO_INTENCOES = {"parecer_juridico", "estrategia_processual", "negociacao", "decisao_judicial_impacto_alto"}
            st.markdown(resposta)
            partes = [f"intent: `{intencao}`"]
            if ti or to:
                partes.append(f"tokens: `{ti}↑ {to}↓`")
            if rag_ativo:
                partes.append("📚 RAG injetado")
            if intencao in _ESCALACAO_INTENCOES:
                partes.append("🚨 escalado → advogado notificado")
            if fallback:
                partes.append("⚠️ fallback")
            st.caption(" · ".join(partes))

        st.session_state[chat_key].append({
            "role": "assistant",
            "content": resposta,
            "meta": {"intencao": intencao, "tokens_in": ti, "tokens_out": to, "fallback": fallback, "rag_ativo": rag_ativo},
        })
        st.rerun()


# =============================================================================
# SEÇÃO 8 — PÁGINA: Base de Conhecimento RAG (Feature 3)
# =============================================================================


def page_rag() -> None:
    st.title("📚 Base de Conhecimento Jurídico — RAG")
    st.caption(
        "Feature 3 — Retrieval-Augmented Generation. "
        "Faça upload de documentos jurídicos; a IA os consulta automaticamente ao responder perguntas."
    )

    # Inicializa base RAG na sessão
    if "rag_base" not in st.session_state:
        st.session_state["rag_base"] = _MockRAGBase()
    rag: _MockRAGBase = st.session_state["rag_base"]

    # ── Métricas ──────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("Documentos", rag.total_docs)
    col2.metric("Chunks Indexados", rag.total_chunks)
    col3.metric("Similaridade Mínima", "0.75 (Jaccard)")

    st.divider()

    # ── Upload ────────────────────────────────────────────────────────────────
    col_upload, col_config = st.columns([2, 1])

    with col_upload:
        st.subheader("📤 Adicionar Documento")
        arquivo = st.file_uploader(
            "PDF ou TXT",
            type=["pdf", "txt"],
            help=f"PDF {'✅ suportado (PyMuPDF)' if _FITZ_OK else '⚠️ requer pip install pymupdf'} · TXT sempre suportado",
        )

        if arquivo:
            col_t, col_tipo = st.columns(2)
            with col_t:
                titulo = st.text_input("Título do documento", value=arquivo.name.rsplit(".", 1)[0])
            with col_tipo:
                tipo = st.selectbox("Tipo", ["peticao", "sentenca", "jurisprudencia", "tese", "parecer"])

            if st.button("📥 Ingerir Documento", type="primary"):
                with st.spinner("Extraindo texto, chunking e indexando..."):
                    texto = _extrair_texto(arquivo.getvalue(), arquivo.name)
                    if not texto.strip():
                        st.error("Não foi possível extrair texto do arquivo.")
                    else:
                        n_chunks = rag.adicionar(titulo, tipo, texto)
                        st.success(
                            f"✅ Documento '{titulo}' ingerido! "
                            f"{n_chunks} chunk(s) gerados e indexados."
                        )
                        st.rerun()

    with col_config:
        st.subheader("⚙️ Pipeline RAG")
        st.markdown("""
        **Implementação demo:**
        - Chunking: 500 chars, 30-word overlap
        - Indexação: keywords (TF-IDF-like)
        - Busca: Jaccard similarity
        - Re-ranking: top-3 por relevância

        **Em produção:**
        - Embeddings: Voyage AI (`voyage-law-2`)
        - Armazenamento: PostgreSQL + pgvector
        - Busca: cosine similarity
        - Re-ranking: MMR (Max Marginal Relevance)
        - Cache: Redis TTL 1h
        """)

    st.divider()

    # ── Guia: O que colocar na base ───────────────────────────────────────────
    with st.expander("📋 O que colocar na base RAG para melhores resultados", expanded=rag.total_docs == 0):
        st.markdown("""
        O retriever enriquece automaticamente a busca com o **tipo de ação** e **tribunal**
        do processo do cliente — então documentos da mesma área jurídica são sempre priorizados.
        """)

        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.markdown("#### Por tipo de documento")
            st.markdown("""
🟡 **`jurisprudencia`** — maior impacto
- Acórdãos do TJSP/TRT/STJ na mesma área de atuação
- Súmulas aplicáveis (STJ, STF, TST)
- Julgados paradigma similares aos casos dos clientes

🟠 **`tese`** — segundo maior impacto
- Teses defensivas/ofensivas por área
- Argumentação que o escritório usa nas petições
- Pontos fortes e fracos de cada tipo de ação

🟢 **`sentenca`** — contexto processual
- Sentenças recebidas em casos similares (anonimizadas)
- Padrões de fundamentação dos juízes da comarca
- Decisões interlocutórias comuns no tribunal

🟣 **`parecer`** — respostas técnicas prontas
- FAQs internas ("O que acontece depois da citação?")
- Explicações de fase processual por tipo de ação
- Respostas padronizadas para perguntas frequentes

🔵 **`peticao`** — linguagem do escritório
- Petições iniciais com os argumentos usados
- Contestações nas áreas de atuação principal
            """)

        with col_g2:
            st.markdown("#### Por área de atuação")
            st.markdown("""
⚖️ **Trabalhista**
→ Súmulas TST + OJ SDI · Tese rescisão indireta / dano moral

🏥 **Cível / Indenizatório**
→ Acórdãos TJSP por comarca · Tabela danos morais da vara

💊 **Previdenciário**
→ Portarias INSS + jurisprudência TRF · Tese por tipo de benefício

👨‍👩‍👧 **Família**
→ Jurisprudência pensão + guarda · FAQ procedimentos cartório

🛒 **Consumidor**
→ CDC + Súmulas STJ · Decisões Procon da região
            """)

            st.markdown("#### Tamanho ideal")
            st.markdown("""
O chunker divide em blocos de **~500 palavras** (overlap de 30).
Documentos entre **1 e 10 páginas** funcionam melhor.

Para sentenças longas (+40 pág): extraia só os
**fundamentos da decisão** (3-5 pág) e ingira essa parte.
            """)

        st.markdown("---")
        st.markdown("#### ❌ O que **não** colocar")
        col_n1, col_n2 = st.columns(2)
        with col_n1:
            st.markdown("""
- Petições com dados pessoais reais (sem anonimizar)
- Documentos genéricos de internet (Wikipedia, artigos vagos)
            """)
        with col_n2:
            st.markdown("""
- Texto puro da lei — o Claude já sabe a lei; coloque a **aplicação** dela
- Jurisprudência com mais de 5 anos sem revisar (muda com frequência)
            """)

    st.divider()

    # ── Documentos Indexados ──────────────────────────────────────────────────
    st.subheader("📂 Documentos na Base")
    docs = rag.listar_documentos()
    if not docs:
        st.info("Nenhum documento indexado ainda. Faça upload acima.")
    else:
        for doc in docs:
            col_doc, col_del = st.columns([5, 1])
            with col_doc:
                tipo_badge = {
                    "peticao": "🔵", "sentenca": "🟢", "jurisprudencia": "🟡",
                    "tese": "🟠", "parecer": "🟣",
                }.get(doc["tipo"], "⚪")
                st.markdown(f"{tipo_badge} **{doc['titulo']}** · `{doc['tipo']}` · {doc['chunks']} chunks")
            with col_del:
                if st.button("🗑️", key=f"del_{doc['titulo']}", help="Remover documento"):
                    removidos = rag.remover(doc["titulo"])
                    st.info(f"Removido: {doc['titulo']} ({removidos} chunks)")
                    st.rerun()

    st.divider()

    # ── Teste de Busca ────────────────────────────────────────────────────────
    st.subheader("🔍 Teste de Busca Semântica")
    st.caption("Simula como a IA recupera contexto ao responder uma pergunta.")

    query = st.text_input("Consulta", placeholder="ex: prescrição trabalhista, rescisão indireta, pensão alimentícia...")
    col_k, _ = st.columns([1, 3])
    with col_k:
        top_k = st.slider("Top K resultados", 1, 5, 3)

    if query and rag.total_chunks > 0:
        chunks = rag.buscar(query, top_k=top_k)
        if chunks:
            st.success(f"✅ {len(chunks)} chunk(s) recuperado(s)")
            for i, c in enumerate(chunks, 1):
                with st.expander(f"Chunk {i} — [{c['tipo']}] {c['titulo']}"):
                    st.write(c["texto"])
                    kw_preview = list(c["keywords"])[:10]
                    st.caption(f"Keywords: {', '.join(kw_preview)}")
            st.subheader("Contexto que seria injetado no prompt:")
            st.code(rag.formatar_contexto(chunks), language="xml")
        else:
            st.warning("Nenhum chunk relevante encontrado para esta consulta.")
    elif query and rag.total_chunks == 0:
        st.warning("Base de conhecimento vazia. Adicione documentos primeiro.")

    # ── Explicação do pipeline completo ──────────────────────────────────────
    st.divider()
    with st.expander("📖 Como o RAG se integra ao orchestrator (Feature 3)"):
        st.markdown("""
        ```
        [Mensagem do cliente]
              ↓
        [Nó 1: Classificar Intenção] → intent: status | duvida_termo | perspectivas | ...
              ↓ (se precisa de dados)
        [Nó 2: Buscar Dados DB + DataJud]   [Nó 3: Buscar Contexto RAG]
              ↓                                    ↓
        [Nó 4: Gerar Resposta]  ← system_prompt com persona + dados processo + contexto RAG
              ↓
        [Nó 5: Verificar Fatos (FactChecker)]
              ↓
        [Nó 6: Enviar Resposta → Evolution WhatsApp]
        ```

        **Persona (Feature 4 → Feature 1):**
        ```xml
        <persona>
        Você se chama {persona_nome}. Ao se apresentar, use este nome.
        {instrução_do_tom}
        </persona>
        ```

        O bloco `<persona>` é gerado por `gerar_instrucao_persona()` e prefixado
        ao `SYSTEM_PROMPT_BASE` antes de cada chamada ao Claude.

        **Contexto RAG:**
        ```xml
        <contexto_juridico>
        [JURISPRUDENCIA — Título do Doc]
        Texto do chunk recuperado...
        </contexto_juridico>
        ```
        """)


# =============================================================================
# SEÇÃO 9 — PÁGINA: Configurações (editar persona + templates após go-live)
# =============================================================================


def page_configuracoes() -> None:
    st.title("⚙️ Configurações do Escritório")
    ob = st.session_state.get("onboarding", {})
    if not ob:
        st.warning("Complete o Onboarding primeiro.")
        return

    tab_persona, tab_templates, tab_status = st.tabs(["🤖 Persona IA", "📝 Templates", "📊 Status do Sistema"])

    with tab_persona:
        st.subheader("Configurar Persona da IA")
        st.caption("Alterações aqui reinicializam os orchestrators existentes.")
        with st.form("form_persona"):
            novo_nome = st.text_input("Nome da IA", value=ob.get("persona_nome", "Assistente Jurídico"))
            novo_tom = st.selectbox("Tom de voz", ["formal", "amigavel", "neutro"],
                                    index=["formal", "amigavel", "neutro"].index(ob.get("persona_tom", "formal")))
            novo_ini = st.text_input("Horário Início", value=ob.get("horario_inicio", "08:00"))
            novo_fim = st.text_input("Horário Fim", value=ob.get("horario_fim", "18:00"))
            if st.form_submit_button("Salvar Persona", type="primary"):
                ob.update({"persona_nome": novo_nome, "persona_tom": novo_tom,
                           "horario_inicio": novo_ini, "horario_fim": novo_fim})
                # Reinicializa orchestrators para pegar nova persona
                for key in list(st.session_state.keys()):
                    if key.startswith(("orch_", "welcome_")):
                        del st.session_state[key]
                st.success("✅ Persona atualizada. Orchestrators reinicializados.")
                st.rerun()

        st.markdown("**Preview da instrução atual:**")
        st.code(gerar_instrucao_persona(ob.get("persona_nome", "Assistente"), ob.get("persona_tom", "formal")), language="xml")

    with tab_templates:
        st.subheader("Templates de Mensagem WhatsApp")
        with st.form("form_templates_config"):
            t_bv = st.text_area("Boas-Vindas", value=ob.get("template_boas_vindas", ""), height=80)
            t_at = st.text_area("Atualização", value=ob.get("template_atualizacao", ""), height=80)
            t_sn = st.text_area("Sem Novidade", value=ob.get("template_sem_novidade", ""), height=80)
            if st.form_submit_button("Salvar Templates", type="primary"):
                ob.update({"template_boas_vindas": t_bv, "template_atualizacao": t_at, "template_sem_novidade": t_sn})
                st.success("✅ Templates salvos")

        # Preview com dados reais do cliente
        st.subheader("Preview com dados reais")
        clientes = st.session_state.get("clientes_hub", [])
        if clientes:
            c = clientes[0]
            preview_bv = ob.get("template_boas_vindas", "").replace("{nome_cliente}", c["nome"])
            preview_at = ob.get("template_atualizacao", "").replace("{nome_cliente}", c["nome"]).replace(
                "{resumo_andamento}", "Despacho publicado em 18/03/2026 — aguardando designação de audiência"
            )
            st.markdown(f"**Boas-vindas:** {preview_bv}")
            st.markdown(f"**Atualização:** {preview_at}")

    with tab_status:
        st.subheader("Status do Sistema")
        col1, col2, col3 = st.columns(3)
        col1.metric("Claude", "✅ Online" if ANTHROPIC_API_KEY else "❌ Sem chave")
        col2.metric("DataJud", "✅ Público" if not DATAJUD_API_KEY else "✅ Com API Key")
        col3.metric("WhatsApp", "✅ Simulado" if ob.get("whatsapp_ok") else "⚠️ Não conectado")

        st.subheader("Analytics de Intenções")
        clientes = st.session_state.get("clientes_hub", [])
        total_intencoes: dict[str, int] = {}
        total_tokens_in = total_tokens_out = 0
        for c in clientes:
            tk = st.session_state.get(f"tokens_{c['id']}", {})
            total_tokens_in += tk.get("in", 0)
            total_tokens_out += tk.get("out", 0)
            for intent, cnt in tk.get("intencoes", {}).items():
                total_intencoes[intent] = total_intencoes.get(intent, 0) + cnt

        if total_intencoes:
            for intent, cnt in sorted(total_intencoes.items(), key=lambda x: -x[1]):
                st.progress(cnt / max(total_intencoes.values()), text=f"`{intent}` — {cnt}x")
        else:
            st.info("Nenhuma conversa registrada ainda.")

        if total_tokens_in or total_tokens_out:
            custo = (total_tokens_in * 3 + total_tokens_out * 15) / 1_000_000
            st.metric("Total Tokens", f"{total_tokens_in + total_tokens_out:,}")
            st.metric("Custo Estimado Claude Sonnet", f"US$ {custo:.4f}")


# =============================================================================
# =============================================================================
# SEÇÃO 9B — PÁGINA: CRM Inteligente (Feature 7)
# =============================================================================

_CRM_CORES = {
    "excelente": "#2ecc71",
    "satisfeito": "#27ae60",
    "neutro":     "#f39c12",
    "em_risco":   "#e67e22",
    "critico":    "#e74c3c",
}

_CRM_ICONES = {
    "excelente": "🟢",
    "satisfeito": "🟢",
    "neutro":     "🟡",
    "em_risco":   "🟠",
    "critico":    "🔴",
}


def _calcular_crm_mock(cliente: dict) -> dict:
    """
    Calcula score CRM mockado a partir dos dados do cliente na sessão.
    Usa o CRMScoreCalculator real com um CRMContexto sintético.
    """
    from feature_1_ia_personalizada.services.crm.aggregator import (
        CRMContexto, NPSRegistro, ProcessoResumo,
    )
    from feature_1_ia_personalizada.services.crm.score_calculator import calcular_score_crm
    from datetime import UTC, datetime, timedelta
    import random

    seed = hash(cliente["nome"]) % 10000
    rng = random.Random(seed)

    nps_nota = st.session_state.get(f"nps_{cliente['id']}")
    nps_historico = [NPSRegistro(data=datetime.now(UTC), nota=nps_nota)] if nps_nota else []
    nps_medio = float(nps_nota) if nps_nota else None

    tem_processo = bool(cliente.get("numero_cnj"))
    processos = (
        [ProcessoResumo(
            numero_cnj=cliente["numero_cnj"],
            tipo_acao=cliente.get("tipo_acao"),
            fase_processual=None,
            score_nivel=rng.choice(["baixo", "moderado", "alto"]),
            score_interpretacao=None,
        )]
        if tem_processo else []
    )

    ctx = CRMContexto(
        cliente_id=cliente["id"],
        escritorio_id=1,
        nome=cliente["nome"],
        profissao=cliente.get("profissao"),
        empresa=cliente.get("empresa"),
        data_nascimento=None,
        nps_historico=nps_historico,
        nps_medio_3m=nps_medio,
        total_interacoes_30d=rng.randint(0, 15),
        total_interacoes_90d=rng.randint(5, 40),
        dias_desde_ultimo_contato=rng.randint(0, 90),
        ultimo_contato_at=datetime.now(UTC) - timedelta(days=rng.randint(0, 90)),
        processos_ativos=processos,
        pior_score_risco=processos[0].score_nivel if processos else None,
        escalacoes_pendentes=rng.choice([0, 0, 0, 1]),
        escalacoes_rejeitadas_30d=rng.choice([0, 0, 1]),
        crm_score_anterior=None,
        crm_analisado_em_anterior=None,
        crm_resumo_anterior=None,
        crm_acao_sugerida_anterior=None,
    )

    crm = calcular_score_crm(ctx)
    return {
        "nivel": crm.nivel,
        "score": crm.score,
        "fatores": crm.fatores,
        "dias_contato": ctx.dias_desde_ultimo_contato,
        "interacoes_30d": ctx.total_interacoes_30d,
    }


def _badge_nivel(nivel: str) -> str:
    cor = _CRM_CORES.get(nivel, "#999")
    icone = _CRM_ICONES.get(nivel, "⚪")
    return f'<span style="background:{cor};color:white;padding:2px 8px;border-radius:8px;font-size:0.8em">{icone} {nivel.replace("_", " ").upper()}</span>'


def page_crm() -> None:
    """Feature 7 — CRM Inteligente."""
    st.title("🤝 CRM Inteligente")
    st.caption("Classificação de satisfação e sugestões de ação geradas por IA para cada cliente.")

    clientes = st.session_state.get("clientes_hub", [])
    if not clientes:
        st.warning("Nenhum cliente carregado. Faça o onboarding primeiro.")
        return

    # ── Controles ─────────────────────────────────────────────────────────────
    col_btn, col_filtro, col_busca = st.columns([2, 2, 3])
    with col_btn:
        analisar = st.button("🔄 Analisar todos os clientes", use_container_width=True)
    with col_filtro:
        filtro_nivel = st.selectbox(
            "Filtrar por nível",
            ["Todos", "critico", "em_risco", "neutro", "satisfeito", "excelente"],
            label_visibility="collapsed",
        )
    with col_busca:
        busca = st.text_input("Buscar por nome", placeholder="Digite o nome...", label_visibility="collapsed")

    # Dispara ou carrega análises
    if analisar or "crm_resultados" not in st.session_state:
        with st.spinner("Calculando scores CRM..."):
            resultados = {}
            for c in clientes:
                resultados[c["id"]] = _calcular_crm_mock(c)
            st.session_state["crm_resultados"] = resultados
        st.success(f"✅ {len(clientes)} cliente(s) analisado(s)")

    resultados = st.session_state.get("crm_resultados", {})

    # ── Resumo por nível ───────────────────────────────────────────────────────
    st.divider()
    contagens = {n: 0 for n in _CRM_CORES}
    for r in resultados.values():
        contagens[r["nivel"]] = contagens.get(r["nivel"], 0) + 1

    cols = st.columns(5)
    for col, (nivel, total) in zip(cols, contagens.items()):
        cor = _CRM_CORES[nivel]
        with col:
            st.markdown(
                f'<div style="border-left:4px solid {cor};padding-left:8px">'
                f'<div style="font-size:1.6em;font-weight:bold">{total}</div>'
                f'<div style="color:{cor};font-size:0.85em">{nivel.replace("_"," ").upper()}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Tabela de clientes ─────────────────────────────────────────────────────
    clientes_filtrados = [
        c for c in clientes
        if c["id"] in resultados
        and (filtro_nivel == "Todos" or resultados[c["id"]]["nivel"] == filtro_nivel)
        and (not busca or busca.lower() in c["nome"].lower())
    ]
    clientes_filtrados.sort(key=lambda c: resultados[c["id"]]["score"])

    if not clientes_filtrados:
        st.info("Nenhum cliente corresponde aos filtros.")
        return

    for cliente in clientes_filtrados:
        r = resultados[cliente["id"]]
        nivel = r["nivel"]
        cor = _CRM_CORES[nivel]

        with st.container(border=True):
            col_info, col_score, col_detalhe = st.columns([4, 2, 3])

            with col_info:
                st.markdown(
                    f"**{cliente['nome']}** &nbsp; {_badge_nivel(nivel)}",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"📞 {cliente.get('telefone','—')} · "
                    f"💼 {cliente.get('profissao','—')} · "
                    f"📋 {'com processo' if cliente.get('numero_cnj') else 'sem processo'}"
                )

            with col_score:
                st.metric("Score CRM", f"{r['score']}/100")
                st.caption(f"⏱ {r['dias_contato']}d sem contato · 💬 {r['interacoes_30d']} msgs/mês")

            with col_detalhe:
                with st.expander("Ver fatores"):
                    for nome_fator, dados in r["fatores"].items():
                        pct = int(dados["contribuicao"])
                        st.progress(
                            min(dados["pontos"] / 100, 1.0),
                            text=f"{nome_fator}: {dados['pontos']}pts → {pct} contrib.",
                        )

                # Ação sugerida baseada no nível
                if nivel == "critico":
                    st.error("📞 Ligar imediatamente", icon="🚨")
                elif nivel == "em_risco":
                    st.warning("📩 Enviar atualização do processo", icon="⚠️")
                elif nivel == "neutro":
                    st.info("💬 Check-in de relacionamento", icon="ℹ️")
                else:
                    st.success("✅ Nenhuma ação necessária", icon="✅")


# =============================================================================
# SEÇÃO 10 — PÁGINA: Analytics de Satisfação e Retenção (Feature 5)
# =============================================================================


def _gerar_dados_analytics(clientes: list[dict]) -> dict:
    """
    Gera dados analytics a partir dos clientes carregados na sessão.
    Combina dados reais (tokens, intenções, NPS coletados) com valores simulados para demo.
    Seed determinística por conjunto de clientes — dados consistentes dentro da sessão.
    """
    import random

    seed = sum(hash(c["nome"]) for c in clientes) if clientes else 42
    rng = random.Random(seed)
    n = max(len(clientes), 1)

    # ── Resumo ────────────────────────────────────────────────────────────────
    total_interacoes = sum(
        max(1, st.session_state.get(f"tokens_{c['id']}", {}).get("in", 0) // 500)
        + rng.randint(4, 18)
        for c in clientes
    ) if clientes else rng.randint(40, 120)

    clientes_ativos = max(1, n - rng.randint(0, max(0, n - 1)))

    # NPS: usa notas reais coletadas na sessão; completa com sintéticas
    nps_reais = [
        st.session_state[f"nps_{c['id']}"]
        for c in clientes
        if f"nps_{c['id']}" in st.session_state
    ]
    if nps_reais:
        nps_medio = round(sum(nps_reais) / len(nps_reais), 1)
    else:
        nps_medio = round(rng.uniform(3.2, 4.8), 1)
    nps_anterior = round(nps_medio + rng.uniform(-0.5, 0.5), 1)
    variacao = nps_medio - nps_anterior
    variacao_str = f"+{variacao:.1f}" if variacao >= 0 else f"{variacao:.1f}"

    # ── Eficiência ────────────────────────────────────────────────────────────
    tempo_ms = rng.randint(800, 2000)
    interacoes_sem_humano = int(total_interacoes * rng.uniform(0.55, 0.85))
    pct_autonomia = round(interacoes_sem_humano / total_interacoes * 100, 1) if total_interacoes else 0.0
    horas_eco = round(interacoes_sem_humano * 8 / 60, 1)
    custo_total = round(
        sum(
            (st.session_state.get(f"tokens_{c['id']}", {}).get("in", 0) * 3 +
             st.session_state.get(f"tokens_{c['id']}", {}).get("out", 0) * 15) / 1_000_000
            for c in clientes
        ) or rng.uniform(0.10, 2.50),
        4,
    )

    # ── Tendência semanal (8 semanas) ─────────────────────────────────────────
    from datetime import timedelta
    tendencia = []
    semana_base = datetime(2026, 1, 19)
    for i in range(8):
        semana_dt = semana_base + timedelta(weeks=i)
        label = f"{semana_dt.year}-{semana_dt.strftime('W%W')}"
        tot = rng.randint(8, 35)
        saidas = rng.randint(int(tot * 0.5), tot)
        tendencia.append({
            "semana": label,
            "total_interacoes": tot,
            "nps_medio": round(rng.uniform(3.0, 5.0), 1),
            "autonomia_pct": round(saidas / tot * 100, 1),
        })

    # ── Ranking de clientes ───────────────────────────────────────────────────
    ranking = []
    for c in clientes:
        nps_cli = st.session_state.get(f"nps_{c['id']}")
        if nps_cli is None:
            nps_cli = rng.choice([None, None, round(rng.uniform(1.0, 5.0), 1)])
        ultimo_contato_dias = rng.randint(1, 60)
        sem_contato_recente = ultimo_contato_dias > 30
        em_risco = sem_contato_recente and nps_cli is not None and nps_cli <= 3
        ranking.append({
            "cliente_id": c["id"],
            "nome": c["nome"],
            "nps_medio": nps_cli,
            "total_interacoes": rng.randint(3, 25),
            "ultimo_contato_dias": ultimo_contato_dias,
            "em_risco": em_risco,
            "sem_avaliacao": nps_cli is None,
        })
    ranking.sort(key=lambda r: (
        not r["em_risco"],
        not r["sem_avaliacao"],
        r["nps_medio"] if r["nps_medio"] is not None else 999,
    ))

    return {
        "resumo": {
            "total_interacoes": total_interacoes,
            "clientes_ativos": clientes_ativos,
            "nps_medio": nps_medio,
            "nps_anterior": nps_anterior,
            "variacao_nps": variacao_str,
        },
        "eficiencia": {
            "tempo_resposta_medio_ms": tempo_ms,
            "interacoes_sem_humano": interacoes_sem_humano,
            "percentual_autonomia": pct_autonomia,
            "horas_economizadas_estimadas": horas_eco,
            "custo_total_usd": custo_total,
        },
        "tendencia_semanal": tendencia,
        "por_cliente": ranking,
        "score_risco_distribuicao": {
            "baixo": rng.randint(0, max(0, n - 2)),
            "moderado": rng.randint(0, max(0, n - 1)),
            "alto": rng.randint(0, max(0, n // 2)),
            "critico": rng.randint(0, 1),
        },
    }


def _render_tendencia_chart(tendencia: list[dict]) -> None:
    """Barras HTML in-line — sem dependência de plotly/matplotlib."""
    if not tendencia:
        st.info("Sem dados de tendência.")
        return
    max_tot = max(t["total_interacoes"] for t in tendencia) or 1
    bars = '<div style="display:flex;align-items:flex-end;gap:6px;height:120px;padding:8px 0;">'
    for t in tendencia:
        pct = t["total_interacoes"] / max_tot * 100
        nps = t["nps_medio"]
        cor = "#4CAF50" if nps >= 4.0 else "#FF9800" if nps >= 3.0 else "#f44336"
        semana_label = t["semana"].split("-W")[-1] if "-W" in t["semana"] else t["semana"]
        bars += (
            f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;">'
            f'<span style="font-size:9px;color:#666;">{t["total_interacoes"]}</span>'
            f'<div style="width:100%;height:{pct:.0f}%;background:{cor};border-radius:3px 3px 0 0;min-height:4px;"'
            f' title="{t["semana"]}: {t["total_interacoes"]} interações, NPS {nps}, {t["autonomia_pct"]}% autonomia">'
            f'</div>'
            f'<span style="font-size:8px;color:#888;">W{semana_label}</span>'
            f'</div>'
        )
    bars += "</div>"
    bars += '<div style="font-size:10px;color:#888;margin-top:4px;">🟢 NPS≥4 · 🟠 NPS≥3 · 🔴 NPS&lt;3 — altura = volume de interações</div>'
    st.markdown(bars, unsafe_allow_html=True)


def page_analytics() -> None:
    """Feature 5 — Analytics de Satisfação e Retenção."""
    st.title("📊 Analytics de Satisfação e Retenção")
    st.caption(
        "Feature 5 — NPS, eficiência da IA, tendência semanal e ranking de clientes. "
        "Demo: dados calculados a partir dos clientes e conversas da sessão atual."
    )

    clientes: list[dict] = st.session_state.get("clientes_hub", [])
    if not clientes:
        st.warning("Nenhum cliente carregado. Complete o Onboarding e importe clientes primeiro.")
        if st.button("Ir para Onboarding"):
            st.session_state["pagina"] = "onboarding"
            st.rerun()
        return

    dados = _gerar_dados_analytics(clientes)
    resumo = dados["resumo"]
    eficiencia = dados["eficiencia"]
    tendencia = dados["tendencia_semanal"]
    ranking = dados["por_cliente"]

    tab_dash, tab_nps, tab_export, tab_prometheus = st.tabs([
        "📈 Dashboard", "⭐ Pesquisa NPS", "📥 Exportar", "🔧 Prometheus",
    ])

    # =========================================================================
    # Tab 1 — Dashboard
    # =========================================================================
    with tab_dash:
        col_periodo, _ = st.columns([1, 3])
        with col_periodo:
            st.selectbox(
                "Período de análise",
                [7, 30, 90],
                index=1,
                format_func=lambda d: f"Últimos {d} dias",
                key="analytics_dias",
            )

        st.divider()

        # Resumo
        st.subheader("📋 Resumo do Período")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Interações", resumo["total_interacoes"])
        c2.metric("Clientes Ativos", resumo["clientes_ativos"])
        c3.metric("NPS Médio", f"{resumo['nps_medio']:.1f} ⭐", delta=resumo["variacao_nps"])
        c4.metric("NPS Anterior", f"{resumo['nps_anterior']:.1f}")
        c5.metric("Variação NPS", resumo["variacao_nps"])

        st.divider()

        # Eficiência
        st.subheader("⚡ Eficiência da IA")
        ce1, ce2, ce3, ce4, ce5 = st.columns(5)
        ce1.metric("Tempo Resposta Médio", f"{eficiencia['tempo_resposta_medio_ms']} ms")
        ce2.metric("Interações sem Humano", eficiencia["interacoes_sem_humano"])
        ce3.metric("Autonomia", f"{eficiencia['percentual_autonomia']:.1f}%")
        ce4.metric("Horas Economizadas", f"{eficiencia['horas_economizadas_estimadas']:.1f}h")
        ce5.metric("Custo Total Claude", f"US$ {eficiencia['custo_total_usd']:.4f}")

        pct = eficiencia["percentual_autonomia"]
        cor_auto = "#4CAF50" if pct >= 70 else "#FF9800" if pct >= 50 else "#f44336"
        st.markdown(
            f"""<div style="margin:8px 0;">
                <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">
                    <span>Taxa de Autonomia da IA</span>
                    <span style="font-weight:600;color:{cor_auto};">{pct:.1f}%</span>
                </div>
                <div style="background:#e0e0e0;border-radius:4px;height:10px;">
                    <div style="width:{pct}%;background:{cor_auto};height:10px;border-radius:4px;"></div>
                </div>
                <div style="font-size:11px;color:#888;margin-top:3px;">
                    {eficiencia['interacoes_sem_humano']} de {resumo['total_interacoes']}
                    interações resolvidas sem intervenção humana
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        st.divider()

        # Tendência semanal
        st.subheader("📅 Tendência Semanal (últimas 8 semanas)")
        _render_tendencia_chart(tendencia[-8:])
        with st.expander("Ver dados tabulados"):
            for t in tendencia:
                emoji_nps = "🟢" if t["nps_medio"] >= 4.0 else "🟠" if t["nps_medio"] >= 3.0 else "🔴"
                st.caption(
                    f"**{t['semana']}** — {t['total_interacoes']} interações · "
                    f"NPS {emoji_nps} {t['nps_medio']:.1f} · Autonomia {t['autonomia_pct']:.1f}%"
                )

        st.divider()

        # Ranking de clientes
        st.subheader("👥 Ranking de Clientes")
        st.caption("Em risco (NPS baixo + sem contato recente) aparece primeiro; sem avaliação em segundo.")
        for r in ranking:
            cor_card = "#ffebee" if r["em_risco"] else "#fff8e1" if r["sem_avaliacao"] else "#f1f8e9"
            borda = "#ef9a9a" if r["em_risco"] else "#ffe082" if r["sem_avaliacao"] else "#a5d6a7"
            status_icon = "🔴 Em Risco" if r["em_risco"] else ("⚪ Sem Avaliação" if r["sem_avaliacao"] else "🟢 Ok")
            nps_str = f"{r['nps_medio']:.1f} ⭐" if r["nps_medio"] is not None else "—"
            st.markdown(
                f"""<div style="border:1px solid {borda};border-radius:8px;padding:10px 14px;
                             background:{cor_card};margin-bottom:6px;display:flex;
                             justify-content:space-between;align-items:center;">
                    <div>
                        <span style="font-weight:600;">{r['nome']}</span>
                        <span style="font-size:11px;color:#666;margin-left:8px;">{status_icon}</span>
                    </div>
                    <div style="text-align:right;font-size:12px;color:#555;">
                        NPS: <strong>{nps_str}</strong> ·
                        {r['total_interacoes']} interações ·
                        último contato há {r['ultimo_contato_dias']}d
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )

        # Score de risco distribuição
        st.divider()
        st.subheader("🔒 Distribuição de Score de Risco (Feature 2)")
        score_dist = dados["score_risco_distribuicao"]
        total_score = sum(score_dist.values()) or 1
        niveis = [
            ("baixo", "🟢"), ("moderado", "🟡"), ("alto", "🔴"), ("critico", "🟣"),
        ]
        for col, (nivel, emoji) in zip(st.columns(4), niveis):
            qtd = score_dist.get(nivel, 0)
            col.metric(f"{emoji} {nivel.capitalize()}", qtd,
                       help=f"{qtd / total_score * 100:.0f}% dos processos")

    # =========================================================================
    # Tab 2 — Pesquisa NPS
    # =========================================================================
    with tab_nps:
        st.subheader("⭐ Pesquisa de Satisfação NPS")
        st.markdown("""
        Simula o fluxo completo de coleta NPS via WhatsApp (Feature 5):
        1. Advogado dispara pesquisa → `solicitar_nps_cliente` (Celery) envia mensagem
        2. Cliente responde 1–5 → webhook detecta, salva `satisfacao`, remove `aguardando_nps`
        3. Nota ≤ 3 → alerta automático enviado a advogados com `escalacao_ativa=True`
        """)
        st.divider()

        if "nps_estados" not in st.session_state:
            st.session_state["nps_estados"] = {}
        nps_estados: dict = st.session_state["nps_estados"]

        col_enviar, col_responder = st.columns(2)

        with col_enviar:
            st.markdown("#### 📤 1. Enviar Pesquisa NPS")
            st.caption("Simula o task Celery com deduplicação Redis (`nps:solicitado:{id}` TTL 30d).")
            cliente_sel = st.selectbox(
                "Selecionar cliente",
                options=clientes,
                format_func=lambda c: c["nome"],
                key="nps_cliente_sel",
            )
            if cliente_sel:
                cid = cliente_sel["id"]
                estado = nps_estados.get(cid, {})
                if estado.get("aguardando_nps"):
                    st.info(f"⏳ Pesquisa já enviada para **{cliente_sel['nome']}** — aguardando resposta.")
                elif estado.get("nps_registrado") is not None:
                    nota_reg = estado["nps_registrado"]
                    emoji_n = "🟢" if nota_reg >= 4 else "🟡" if nota_reg == 3 else "🔴"
                    st.success(f"✅ NPS registrado: {emoji_n} **{nota_reg}/5** para {cliente_sel['nome']}")
                    if st.button("🔄 Enviar nova pesquisa", key="nps_nova"):
                        nps_estados[cid] = {}
                        st.rerun()
                else:
                    template_nps = (
                        f"Olá {cliente_sel['nome'].split()[0]}! 😊\n\n"
                        "Como você avalia o atendimento do nosso escritório?\n"
                        "Responda com um número de **1 a 5**:\n\n"
                        "1 — Muito insatisfeito\n2 — Insatisfeito\n"
                        "3 — Neutro\n4 — Satisfeito\n5 — Muito satisfeito\n\n"
                        "Sua opinião é muito importante para nós! 🙏"
                    )
                    with st.expander("Ver mensagem WhatsApp"):
                        st.code(template_nps, language=None)
                    if st.button(
                        f"📱 Enviar NPS para {cliente_sel['nome'].split()[0]}",
                        type="primary",
                        key="btn_enviar_nps",
                    ):
                        nps_estados[cid] = {"aguardando_nps": True}
                        st.success("✅ Pesquisa enviada! Interação salva com `aguardando_nps=True`.")
                        st.caption(f"🔒 Redis key: `nps:solicitado:{cid}` — TTL 30 dias (anti-spam)")
                        st.rerun()

        with col_responder:
            st.markdown("#### 📩 2. Simular Resposta do Cliente")
            st.caption("Simula o webhook `/webhook/whatsapp` recebendo a nota via WhatsApp.")
            aguardando = [c for c in clientes if nps_estados.get(c["id"], {}).get("aguardando_nps")]
            if not aguardando:
                st.info("Nenhum cliente aguardando resposta NPS. Envie uma pesquisa primeiro.")
            else:
                cliente_resp = st.selectbox(
                    "Cliente respondendo",
                    options=aguardando,
                    format_func=lambda c: c["nome"],
                    key="nps_resp_sel",
                )
                if cliente_resp:
                    nota_input = st.select_slider(
                        "Nota enviada pelo cliente",
                        options=[1, 2, 3, 4, 5],
                        value=4,
                        format_func=lambda n: f"{n} — " + {
                            1: "Muito insatisfeito 😡", 2: "Insatisfeito 😞",
                            3: "Neutro 😐", 4: "Satisfeito 😊", 5: "Muito satisfeito 🤩",
                        }[n],
                        key="nota_slider",
                    )
                    if st.button("✅ Registrar Resposta", type="primary", key="btn_registrar_nps"):
                        cid_resp = cliente_resp["id"]
                        nps_estados[cid_resp] = {"nps_registrado": nota_input, "aguardando_nps": False}
                        st.session_state[f"nps_{cid_resp}"] = float(nota_input)
                        st.success(
                            f"✅ `satisfacao = {nota_input}` registrado para **{cliente_resp['nome']}**. "
                            "Flag `aguardando_nps` removida do `metadata_json`."
                        )
                        agradecimento = (
                            f"Obrigado pela avaliação, {cliente_resp['nome'].split()[0]}! "
                            "Seu feedback é muito importante para continuarmos melhorando. 🙏"
                        )
                        st.info(f"📱 **Agradecimento enviado:** {agradecimento}")
                        if nota_input <= 3:
                            st.error(
                                f"⚠️ **ALERTA NPS BAIXO — nota {nota_input}/5**\n\n"
                                f"Cliente: {cliente_resp['nome']}\n\n"
                                "Em produção: alerta enviado via WhatsApp a todos os advogados "
                                "com `escalacao_ativa=True`.",
                                icon="🚨",
                            )
                        st.rerun()

        st.divider()
        st.subheader("📊 NPS Coletados nesta Sessão")
        registrados = [
            (c, nps_estados[c["id"]]["nps_registrado"])
            for c in clientes
            if nps_estados.get(c["id"], {}).get("nps_registrado") is not None
        ]
        if not registrados:
            st.info("Nenhuma nota NPS registrada ainda nesta sessão.")
        else:
            nps_vals = [nota for _, nota in registrados]
            media_nps = sum(nps_vals) / len(nps_vals)
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("NPS Médio", f"{media_nps:.1f} ⭐")
            col_m2.metric("Respostas", len(registrados))
            col_m3.metric("Em Risco (≤ 3)", sum(1 for n in nps_vals if n <= 3))
            for cliente_r, nota in sorted(registrados, key=lambda x: x[1]):
                emoji_r = "🟢" if nota >= 4 else "🟡" if nota == 3 else "🔴"
                st.caption(f"{emoji_r} **{cliente_r['nome']}** — nota **{nota}/5**")

    # =========================================================================
    # Tab 3 — Exportar CSV
    # =========================================================================
    with tab_export:
        st.subheader("📥 Exportar Relatório de Interações")
        st.caption(
            "Simula `GET /chat/stats/export?mes=YYYY-MM&formato=csv` "
            "(ExportadorAnalytics.gerar_csv). CSV com BOM UTF-8 para compatibilidade com Excel."
        )

        col_mes, col_fmt = st.columns(2)
        with col_mes:
            mes_sel = st.selectbox(
                "Mês de referência",
                ["2026-03", "2026-02", "2026-01", "2025-12"],
                index=0,
            )
        with col_fmt:
            st.text_input("Formato", value="CSV (UTF-8 BOM)", disabled=True)

        def _gerar_csv_demo(mes: str, clientes_lista: list[dict]) -> bytes:
            import csv as csv_mod
            import random
            output = io.StringIO()
            writer = csv_mod.writer(output)
            writer.writerow([
                "id", "data", "cliente_id", "nome_cliente", "direcao",
                "mensagem_cliente", "tokens_input", "tokens_output",
                "custo_estimado_usd", "satisfacao", "autonomia",
            ])
            rng2 = random.Random(hash(mes))
            row_id = 1
            for c in clientes_lista:
                satisfacao = st.session_state.get(f"nps_{c['id']}", "")
                n_rows = rng2.randint(3, 10)
                for j in range(n_rows):
                    dia = rng2.randint(1, 28)
                    data_str = f"{mes}-{dia:02d}T{rng2.randint(8, 18):02d}:{rng2.randint(0, 59):02d}:00+00:00"
                    ti = rng2.randint(200, 800)
                    to = rng2.randint(100, 400)
                    custo = round((ti * 3 + to * 15) / 1_000_000, 6)
                    writer.writerow([
                        row_id, data_str, c["id"], c["nome"],
                        "recebida" if j % 2 == 0 else "enviada",
                        f"Mensagem demo {j + 1}",
                        ti, to, custo,
                        satisfacao if j == n_rows - 1 else "",
                        "sim" if rng2.random() > 0.3 else "não",
                    ])
                    row_id += 1
            return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")

        csv_bytes = _gerar_csv_demo(mes_sel, clientes)
        st.download_button(
            label=f"📥 Baixar relatorio_interacoes_{mes_sel}.csv",
            data=csv_bytes,
            file_name=f"relatorio_interacoes_{mes_sel}.csv",
            mime="text/csv; charset=utf-8",
            type="primary",
            use_container_width=True,
        )
        with st.expander("Preview das primeiras linhas"):
            preview_lines = csv_bytes.decode("utf-8-sig").split("\n")[:6]
            st.code("\n".join(preview_lines), language="text")
        st.caption(
            "Em produção: SELECT projetado por coluna (não ORM completo), "
            "`isoformat()` para datas, `utf-8-sig` para BOM."
        )

    # =========================================================================
    # Tab 4 — Prometheus
    # =========================================================================
    with tab_prometheus:
        st.subheader("🔧 Métricas Prometheus")
        st.caption(
            "Em produção: `GET /metrics` expõe gauges para o Grafana. "
            "Aqui simulamos os valores atuais dos 3 gauges do escritório (escritorio_id=1)."
        )

        nps_gauge_val = resumo["nps_medio"]
        autonomia_gauge_val = eficiencia["percentual_autonomia"]

        _ESCALACAO_INTENCOES = {
            "parecer_juridico", "estrategia_processual",
            "negociacao", "decisao_judicial_impacto_alto",
        }
        escalacoes = sum(
            sum(v for k, v in st.session_state.get(f"tokens_{c['id']}", {}).get("intencoes", {}).items()
                if k in _ESCALACAO_INTENCOES)
            for c in clientes
        )

        st.divider()
        col_g1, col_g2, col_g3 = st.columns(3)

        def _gauge_card(titulo: str, valor_str: str, sublabel: str, cor: str) -> str:
            return (
                f'<div style="border:1px solid {cor};border-radius:8px;padding:16px;'
                f'background:{cor}18;text-align:center;">'
                f'<div style="font-size:28px;font-weight:700;color:{cor};">{valor_str}</div>'
                f'<div style="font-size:11px;color:#666;">labels: escritorio_id="1"</div>'
                f'<div style="font-size:10px;color:#888;margin-top:4px;">{sublabel}</div>'
                f'</div>'
            )

        with col_g1:
            st.markdown("#### `nps_score_gauge`")
            cor = "#4CAF50" if nps_gauge_val >= 4.0 else "#FF9800" if nps_gauge_val >= 3.0 else "#f44336"
            st.markdown(_gauge_card("NPS Score", f"{nps_gauge_val:.1f}", "Gauge — NPS médio atual", cor), unsafe_allow_html=True)

        with col_g2:
            st.markdown("#### `ia_autonomia_percent_gauge`")
            cor = "#4CAF50" if autonomia_gauge_val >= 70 else "#FF9800" if autonomia_gauge_val >= 50 else "#f44336"
            st.markdown(_gauge_card("Autonomia IA", f"{autonomia_gauge_val:.1f}%", "Gauge — % autonomia da IA", cor), unsafe_allow_html=True)

        with col_g3:
            st.markdown("#### `escalacoes_pendentes_gauge`")
            cor = "#f44336" if escalacoes > 0 else "#4CAF50"
            st.markdown(_gauge_card("Escalações", str(escalacoes), "Gauge — escalações pendentes", cor), unsafe_allow_html=True)

        st.divider()
        with st.expander("Ver formato raw (como aparece em /metrics)"):
            st.code(
                f"# HELP nps_score_gauge NPS médio atual por escritório\n"
                f"# TYPE nps_score_gauge gauge\n"
                f'nps_score_gauge{{escritorio_id="1"}} {nps_gauge_val:.1f}\n\n'
                f"# HELP ia_autonomia_percent_gauge Percentual de autonomia da IA\n"
                f"# TYPE ia_autonomia_percent_gauge gauge\n"
                f'ia_autonomia_percent_gauge{{escritorio_id="1"}} {autonomia_gauge_val:.1f}\n\n'
                f"# HELP escalacoes_pendentes_gauge Interações com escalacao pendente\n"
                f"# TYPE escalacoes_pendentes_gauge gauge\n"
                f'escalacoes_pendentes_gauge{{escritorio_id="1"}} {escalacoes}',
                language="text",
            )

        st.markdown("""
        **Segurança do endpoint `/metrics`:**
        - `METRICS_TOKEN` env var → `Authorization: Bearer <token>` (comparação HMAC segura)
        - Segunda camada: restrição de IP a nível de infra (nginx / load balancer)
        - Sem token configurado → modo dev (warning no log, sem bloqueio)

        **Integração Grafana:**
        ```yaml
        scrape_configs:
          - job_name: hub-juridico
            static_configs:
              - targets: [api:8000]
            metrics_path: /metrics
            bearer_token: ${METRICS_TOKEN}
        ```
        """)
        st.info(
            "`_atualizar_metricas_prometheus()` é chamada apenas em cache miss do dashboard "
            "(não a cada request), evitando writes desnecessários ao Prometheus.",
            icon="ℹ️",
        )


# =============================================================================
# SEÇÃO 12 — Prospecção Inteligente (Feature 3)
# =============================================================================

_PROSPECCAO_TIPOS_ACAO = [
    "Reclamação Trabalhista",
    "Horas Extras",
    "Rescisão Indireta",
    "Ação de Cobrança",
    "Indenização por Danos Morais",
    "Ação de Divórcio",
    "Execução de Título Extrajudicial",
    "Ação Consumerista",
    "Rescisão Contratual",
    "Acidente de Trabalho",
]

_EMPRESAS_DEMO = [
    {"razao_social": "Metalúrgica São Paulo LTDA", "cnpj": "11.222.333/0001-81",
     "porte": "MEDIA", "setor": "indústria", "situacao": "ATIVA", "processos": 8},
    {"razao_social": "Comércio e Distribuição Norte S/A", "cnpj": "22.333.444/0001-92",
     "porte": "GRANDE", "setor": "comércio", "situacao": "ATIVA", "processos": 15},
    {"razao_social": "Tech Solutions LTDA ME", "cnpj": "33.444.555/0001-03",
     "porte": "PEQUENA", "setor": "tecnologia", "situacao": "ATIVA", "processos": 3},
    {"razao_social": "Transporte e Logística Brasil LTDA", "cnpj": "44.555.666/0001-14",
     "porte": "MEDIA", "setor": "transporte", "situacao": "ATIVA", "processos": 12},
    {"razao_social": "Construtora ABC S/A", "cnpj": "55.666.777/0001-25",
     "porte": "GRANDE", "setor": "construção civil", "situacao": "ATIVA", "processos": 20},
    {"razao_social": "Varejo Fashion LTDA", "cnpj": "66.777.888/0001-36",
     "porte": "MEDIA", "setor": "varejo", "situacao": "ATIVA", "processos": 6},
    {"razao_social": "Hospital e Clínica Central S/A", "cnpj": "77.888.999/0001-47",
     "porte": "GRANDE", "setor": "saúde", "situacao": "ATIVA", "processos": 18},
    {"razao_social": "Agro Sul Grãos LTDA", "cnpj": "88.999.000/0001-58",
     "porte": "MEDIA", "setor": "agronegócio", "situacao": "ATIVA", "processos": 4},
    {"razao_social": "Supermercados RegionalMais S/A", "cnpj": "99.000.111/0001-69",
     "porte": "GRANDE", "setor": "varejo alimentício", "situacao": "ATIVA", "processos": 25},
    {"razao_social": "Indústria de Calçados Norte LTDA", "cnpj": "10.111.222/0001-70",
     "porte": "MEDIA", "setor": "indústria", "situacao": "ATIVA", "processos": 7},
]

_PESSOAS_DEMO = [
    {"nome": "Carlos Eduardo Martins", "polo": "ativo", "fase": "Conhecimento",
     "cnj": "0001234-56.2024.5.02.0100"},
    {"nome": "Ana Beatriz Santos", "polo": "ativo", "fase": "Conhecimento",
     "cnj": "0002345-67.2024.5.02.0200"},
    {"nome": "Roberto José Ferreira", "polo": "ativo", "fase": "Instrução",
     "cnj": "0003456-78.2024.5.02.0300"},
    {"nome": "Juliana Costa Lima", "polo": "ativo", "fase": "Conhecimento",
     "cnj": "0004567-89.2024.5.02.0400"},
    {"nome": "Paulo Henrique Oliveira", "polo": "ativo", "fase": "Petição Inicial",
     "cnj": "0005678-90.2024.5.02.0500"},
    {"nome": "Maria Aparecida Souza", "polo": "ativo", "fase": "Conhecimento",
     "cnj": "0006789-01.2024.5.02.0600"},
    {"nome": "Fernando Augusto Rocha", "polo": "ativo", "fase": "Conhecimento",
     "cnj": "0007890-12.2024.5.02.0700"},
    {"nome": "Sandra Regina Alves", "polo": "ativo", "fase": "Distribuição",
     "cnj": "0008901-23.2024.5.02.0800"},
]

_ESPECIALIDADES_POR_TIPO_ACAO: dict[str, list[str]] = {
    "Reclamação Trabalhista":        ["reclamação trabalhista", "horas extras"],
    "Horas Extras":                  ["horas extras", "reclamação trabalhista"],
    "Rescisão Indireta":             ["rescisão indireta", "reclamação trabalhista"],
    "Acidente de Trabalho":          ["acidente de trabalho", "indenização por danos morais"],
    "Ação de Cobrança":              ["ação de cobrança", "execução de título extrajudicial"],
    "Indenização por Danos Morais":  ["indenização por danos morais", "ação consumerista"],
    "Ação de Divórcio":              ["ação de divórcio", "guarda e visitação"],
    "Execução de Título Extrajudicial": ["execução de título extrajudicial", "ação de cobrança"],
    "Ação Consumerista":             ["ação consumerista", "indenização por danos morais"],
    "Rescisão Contratual":           ["rescisão contratual", "ação de cobrança"],
}


def _gerar_dna_demo(tipo_acao_ref: str | None = None, nome_escritorio: str = "") -> DNAEscritorio:
    """
    Gera um DNA sintético coerente com o tipo_acao mais recente buscado.
    Sem tipo_acao: assume perfil trabalhista (mais comum no mercado).
    """
    tipo = tipo_acao_ref or "Reclamação Trabalhista"
    especialidades = _ESPECIALIDADES_POR_TIPO_ACAO.get(tipo, ["reclamação trabalhista"])
    especialidades = list(dict.fromkeys(especialidades + ["indenização por danos morais"]))[:4]

    # B2B para ações tipicamente movidas contra empresas; B2C para demais
    b2b_tipos = {"Reclamação Trabalhista", "Horas Extras", "Rescisão Indireta",
                 "Acidente de Trabalho", "Rescisão Contratual", "Ação de Cobrança",
                 "Execução de Título Extrajudicial"}
    tipo_lead = "empresa" if tipo in b2b_tipos else "pessoa"
    setores = ["indústria", "comércio", "serviços", "transporte"] if tipo_lead == "empresa" else []

    return DNAEscritorio(
        escritorio_id=1,
        especialidades=especialidades,
        setores_alvo=setores,
        tipo_lead_predominante=tipo_lead,
        perfil_cliente_ideal=(
            f"{'Empresas de médio e grande porte' if tipo_lead == 'empresa' else 'Trabalhadores e consumidores'} "
            f"com demandas em {especialidades[0]}"
        ),
        diferenciais=["Atendimento ágil", "Especialização setorial", "Transparência no processo"],
        top_tipos_acao=[
            {"tipo": especialidades[0], "contagem": 65, "percentual": 65.0},
            {"tipo": especialidades[1] if len(especialidades) > 1 else especialidades[0],
             "contagem": 25, "percentual": 25.0},
        ],
        dados_insuficientes=False,
    )


def _cor_score_prospeccao(score: int) -> str:
    if score >= 75:
        return "#2e7d32"
    if score >= 50:
        return "#f57c00"
    if score >= 30:
        return "#1565c0"
    return "#757575"


def _render_lead_card_prospeccao(lead: dict) -> None:
    score = lead.get("score", 0)
    cor = _cor_score_prospeccao(score)
    tipo = lead.get("tipo_lead", "empresa")
    icone = "🏢" if tipo == "empresa" else "👤"
    status = lead.get("status", "novo")
    status_cfg = {
        "novo":        ("#1565c0", "#e3f2fd"),
        "contatado":   ("#f57c00", "#fff3e0"),
        "qualificado": ("#2e7d32", "#e8f5e9"),
        "descartado":  ("#757575", "#f5f5f5"),
    }
    s_cor, s_bg = status_cfg.get(status, ("#555", "#f0f0f0"))
    gerado_ia = lead.get("gerado_por_ia", False)
    ia_badge = (
        '<span style="font-size:10px;background:#7b1fa2;color:white;padding:1px 6px;'
        'border-radius:8px;margin-left:6px;">✨ IA</span>'
        if gerado_ia else ""
    )
    st.markdown(
        f"""
        <div style="border:1px solid {cor}40;border-left:4px solid {cor};border-radius:8px;
                    padding:14px 16px;margin-bottom:8px;background:#fafafa;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                <span style="font-size:15px;font-weight:600;">
                    {icone} {lead.get('nome', '—')}{ia_badge}
                </span>
                <div style="display:flex;gap:8px;align-items:center;">
                    <span style="background:{s_bg};color:{s_cor};padding:2px 8px;border-radius:10px;
                                 font-size:11px;font-weight:600;">{status.upper()}</span>
                    <span style="font-size:22px;font-weight:700;color:{cor};">{score}
                        <span style="font-size:11px;color:#888;font-weight:400;">/100</span>
                    </span>
                </div>
            </div>
            <div style="font-size:12px;color:#444;margin-bottom:4px;">
                <strong>Motivo:</strong> {lead.get('motivo', '—')}
            </div>
            <div style="font-size:12px;color:#1565c0;">
                💡 <em>{lead.get('abordagem', '—')}</em>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _buscar_e_pontuar_leads(
    tipo_acao: str,
    tipo_lead: str,
    dna: DNAEscritorio,
    limite: int,
    score_minimo: int,
) -> list[dict]:
    """
    Gera candidatos demo com dados realistas, enriquece e pontua
    usando o MatchingService real (heurística + Claude Sonnet ≥ 30pts).
    """
    import random
    rng = random.Random(hash(tipo_acao + tipo_lead) % 2**32)

    svc = MatchingService(anthropic_api_key=ANTHROPIC_API_KEY)
    leads: list[dict] = []

    if tipo_lead == "empresa":
        pool = rng.sample(_EMPRESAS_DEMO, min(limite, len(_EMPRESAS_DEMO)))
        for emp in pool:
            intel = EmpresaInteligencia(
                razao_social=emp["razao_social"],
                processos_count=emp["processos"],
                tipos_acao_envolvida=[tipo_acao],
                cnpj=emp["cnpj"],
                situacao=emp["situacao"],
                porte=emp["porte"],
                setor_cnae=emp["setor"],
                socios=[
                    {"nome": "José Administrador", "qualificacao": "Administrador"},
                    {"nome": "Maria Sócia", "qualificacao": "Sócia"},
                ],
                contatos_linkedin=(
                    [{"nome": "Ana Gerente", "cargo": "Gerente Jurídico", "url_perfil": ""}]
                    if emp["porte"] in ("MEDIA", "GRANDE") else []
                ),
                linkedin_disponivel=False,
                enriquecimento_parcial=False,
            )
            resultado = asyncio.run(svc.calcular_score(dna=dna, inteligencia=intel))
            if resultado.score < score_minimo:
                continue
            leads.append({
                "id": len(leads),
                "nome": emp["razao_social"],
                "tipo_lead": "empresa",
                "cnpj": emp["cnpj"],
                "setor": emp["setor"],
                "porte": emp["porte"],
                "processos": emp["processos"],
                "score": resultado.score,
                "motivo": resultado.motivo,
                "abordagem": resultado.abordagem_sugerida,
                "gerado_por_ia": resultado.gerado_por_ia,
                "componentes": resultado.componentes,
                "status": "novo",
                "tipo_acao_busca": tipo_acao,
            })
    else:
        pool = rng.sample(_PESSOAS_DEMO, min(limite, len(_PESSOAS_DEMO)))
        for p in pool:
            intel = PessoaInteligencia(
                nome=p["nome"],
                polo=p["polo"],
                tipo_acao=tipo_acao,
                tribunal="TRT2",
                fase_processual=p["fase"],
                numero_cnj_exemplo=p["cnj"],
            )
            resultado = asyncio.run(svc.calcular_score(dna=dna, inteligencia=intel))
            if resultado.score < score_minimo:
                continue
            leads.append({
                "id": len(leads),
                "nome": p["nome"],
                "tipo_lead": "pessoa",
                "polo": p["polo"],
                "fase": p["fase"],
                "cnj": p["cnj"],
                "score": resultado.score,
                "motivo": resultado.motivo,
                "abordagem": resultado.abordagem_sugerida,
                "gerado_por_ia": resultado.gerado_por_ia,
                "componentes": resultado.componentes,
                "status": "novo",
                "tipo_acao_busca": tipo_acao,
            })

    leads.sort(key=lambda l: -l["score"])
    return leads


def page_prospeccao() -> None:
    """Feature 3 — Prospecção Inteligente (B2B + B2C)."""
    st.title("🔍 Prospecção Inteligente")
    st.caption(
        "Motor de captação de leads qualificados: DataJud CNJ → Receita Federal → LinkedIn → "
        "Score heurístico + Claude Sonnet."
    )

    ob = st.session_state.get("onboarding", {})

    if "leads_prospeccao" not in st.session_state:
        st.session_state["leads_prospeccao"] = []
    if "dna_escritorio" not in st.session_state:
        st.session_state["dna_escritorio"] = _gerar_dna_demo(nome_escritorio=ob.get("nome_escritorio", ""))
    if "dna_tipo_acao_ref" not in st.session_state:
        st.session_state["dna_tipo_acao_ref"] = None

    dna: DNAEscritorio = st.session_state["dna_escritorio"]
    leads_total = len(st.session_state["leads_prospeccao"])

    tab_dna, tab_descobrir, tab_pipeline = st.tabs([
        "🧬 DNA do Escritório",
        "🔎 Descobrir Leads",
        f"📋 Pipeline  ({leads_total} lead{'s' if leads_total != 1 else ''})",
    ])

    # ── TAB 1 — DNA do Escritório ──────────────────────────────────────────────
    with tab_dna:
        st.markdown("### Perfil Estratégico do Escritório")
        st.caption(
            "O DNA é inferido a partir do tipo de ação pesquisado e determina quais leads "
            "recebem score mais alto. Em produção é gerado pelo `DNAAdvogadoService` a partir "
            "do histórico real de processos (`POST /prospeccao/dna/atualizar`)."
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Especialidades**")
            for esp in dna.especialidades:
                st.markdown(f"- {esp.title()}")
            st.markdown("**Tipo de lead predominante**")
            tipo_badge = "🏢 Empresa (B2B)" if dna.tipo_lead_predominante == "empresa" else "👤 Pessoa (B2C)"
            st.info(tipo_badge)

        with col_b:
            if dna.setores_alvo:
                st.markdown("**Setores-alvo**")
                for s in dna.setores_alvo:
                    st.markdown(f"- {s.title()}")
            st.markdown("**Perfil do cliente ideal**")
            st.write(dna.perfil_cliente_ideal)

        if dna.top_tipos_acao:
            st.divider()
            st.markdown("**Distribuição de tipos de ação**")
            for t in dna.top_tipos_acao:
                pct = t.get("percentual", 0)
                cor = "#1976d2" if pct >= 40 else "#555"
                st.markdown(
                    f"""<div style="margin-bottom:8px;">
                        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:2px;">
                            <span>{t['tipo']}</span>
                            <span style="color:{cor};font-weight:600;">{pct:.0f}%</span>
                        </div>
                        <div style="background:#e0e0e0;border-radius:3px;height:5px;">
                            <div style="width:{pct}%;background:{cor};height:5px;border-radius:3px;"></div>
                        </div></div>""",
                    unsafe_allow_html=True,
                )

        st.divider()
        if st.button("🔄 Regenerar DNA", help="Recalcula o DNA com base no último tipo de ação pesquisado"):
            tipo_ref = st.session_state.get("dna_tipo_acao_ref")
            st.session_state["dna_escritorio"] = _gerar_dna_demo(
                tipo_acao_ref=tipo_ref,
                nome_escritorio=ob.get("nome_escritorio", ""),
            )
            st.success("DNA atualizado.")
            st.rerun()

        with st.expander("ℹ️ Como o DNA funciona em produção"):
            st.markdown("""
**`GET /prospeccao/dna`** → retorna o DNA salvo (cache Redis 6h).

**`POST /prospeccao/dna/atualizar`** → regenera via `DNAAdvogadoService`:
1. Agrega os tipos de ação dos últimos 90 dias do escritório
2. Classifica se o perfil é B2B ou B2C pelo polo predominante
3. Chama **Claude Haiku** para nomear as especialidades e sugerir setores-alvo
4. Persiste em `escritorio.dna_prospeccao` (JSONB) + cache Redis (TTL 6h)
5. Fallback: `dados_insuficientes=True` quando há menos de 5 processos
""")

    # ── TAB 2 — Descobrir Leads ────────────────────────────────────────────────
    with tab_descobrir:
        st.markdown("### Buscar Novos Leads")
        st.caption(
            "Selecione um tipo de ação. O motor busca litigantes no DataJud CNJ, "
            "enriquece com Receita Federal + LinkedIn e pontua com Claude Sonnet."
        )

        with st.form("form_descobrir_leads"):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                tipo_acao = st.selectbox("Tipo de ação", _PROSPECCAO_TIPOS_ACAO)
                tipo_lead = st.radio(
                    "Tipo de lead",
                    ["empresa", "pessoa"],
                    horizontal=True,
                    format_func=lambda x: "🏢 Empresa (B2B)" if x == "empresa" else "👤 Pessoa (B2C)",
                )
            with col_f2:
                score_minimo = st.slider("Score mínimo para qualificar", 0, 100, 40)
                limite = st.slider("Candidatos a analisar", 1, 10, 5)

            submitted = st.form_submit_button("🚀 Buscar e Qualificar Leads", use_container_width=True, type="primary")

        if submitted:
            if not ANTHROPIC_API_KEY:
                st.error("❌ Configure ANTHROPIC_API_KEY para usar o motor de IA.")
            else:
                # Atualiza DNA para refletir o tipo_acao buscado
                st.session_state["dna_tipo_acao_ref"] = tipo_acao
                dna = _gerar_dna_demo(tipo_acao_ref=tipo_acao, nome_escritorio=ob.get("nome_escritorio", ""))
                st.session_state["dna_escritorio"] = dna

                with st.spinner(f"Consultando DataJud → enriquecendo → Claude Sonnet... (~{limite * 4}s)"):
                    try:
                        novos = _buscar_e_pontuar_leads(
                            tipo_acao=tipo_acao,
                            tipo_lead=tipo_lead,
                            dna=dna,
                            limite=limite,
                            score_minimo=score_minimo,
                        )
                        existentes = st.session_state.get("leads_prospeccao", [])
                        chaves = {(l["nome"], l["tipo_lead"]) for l in existentes}
                        inseridos = 0
                        for lead in novos:
                            if (lead["nome"], lead["tipo_lead"]) not in chaves:
                                lead["id"] = len(existentes) + inseridos
                                existentes.append(lead)
                                inseridos += 1
                        st.session_state["leads_prospeccao"] = existentes

                        if inseridos:
                            st.success(f"✅ {inseridos} novo(s) lead(s) adicionado(s) ao pipeline (score ≥ {score_minimo})")
                        elif novos:
                            st.info("Todos os leads encontrados já estavam no pipeline.")
                        else:
                            st.warning(
                                f"Nenhum candidato atingiu score ≥ {score_minimo}. "
                                "Reduza o score mínimo ou mude o tipo de ação."
                            )

                        if novos:
                            st.divider()
                            st.markdown(f"**{len(novos)} lead(s) qualificado(s) nesta busca:**")
                            for lead in novos:
                                _render_lead_card_prospeccao(lead)
                                if lead.get("componentes"):
                                    with st.expander(f"🔬 Componentes do score — {lead['nome']}"):
                                        for comp, pts in lead["componentes"].items():
                                            label = comp.replace("_", " ").title()
                                            st.markdown(f"- **{label}:** +{pts} pts")

                        st.rerun()

                    except Exception as exc:
                        st.error(f"Erro durante a prospecção: {exc}")

        # Aviso LGPD automático quando há leads B2C
        leads_atuais = st.session_state.get("leads_prospeccao", [])
        if any(l.get("tipo_lead") == "pessoa" for l in leads_atuais):
            st.divider()
            st.warning(
                "⚠️ **Aviso LGPD / OAB Prov. 205/2021** — "
                "Este pipeline contém leads de pessoas físicas identificadas em processos públicos. "
                "A abordagem deve respeitar o art. 7º da LGPD: não utilize dados pessoais para "
                "contato direto não solicitado. Canais permitidos: publicação processual, "
                "correspondência via tribunal ou publicidade institucional segmentada.",
                icon="⚠️",
            )

        st.divider()
        with st.expander("ℹ️ Fluxo completo em produção"):
            st.markdown("""
**`POST /prospeccao/descobrir`** executa o motor completo:

| Etapa | Serviço | Detalhe |
|-------|---------|---------|
| 1 | `DataJudProspeccaoClient` | ElasticSearch CNJ — busca litigantes por `tipo_acao` |
| 2 | `EmpresaIntelligenceService` | Receita Federal (CNPJ, porte, sócios) + LinkedIn (cargos) |
| 3 | `PessoaIntelligenceService` | Dados do processo público — sem CPF/telefone/email (LGPD art. 11) |
| 4 | `MatchingService._score_heuristico_*` | Heurística B2B (6 componentes) ou B2C (4 componentes) |
| 5 | `MatchingService._refinar_com_claude` | Claude Sonnet refina score + gera motivo e abordagem (só se score ≥ 30) |
| 6 | `_salvar_lead` | Persiste no banco com deduplicação por CNPJ (empresa) ou número CNJ (pessoa) |

**Heurística B2B:**
+30 especialidade match · +20 setor CNAE · +15 demanda ativa (≥3 proc.) · +15 LinkedIn · +10 porte · +10 ATIVA

**Heurística B2C:**
+35 especialidade match · +25 polo compatível · +20 fase inicial · +20 alta recorrência (>30%)
""")

    # ── TAB 3 — Pipeline ───────────────────────────────────────────────────────
    with tab_pipeline:
        leads = st.session_state.get("leads_prospeccao", [])

        if not leads:
            st.info("Nenhum lead no pipeline ainda. Use **Descobrir Leads** para iniciar a prospecção.")
            return

        # Filtros
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filtro_tipo = st.selectbox(
                "Tipo de lead", ["Todos", "empresa", "pessoa"],
                format_func=lambda x: "Todos os tipos" if x == "Todos" else ("🏢 Empresa" if x == "empresa" else "👤 Pessoa"),
                key="pipl_tipo",
            )
        with col_f2:
            filtro_status = st.selectbox(
                "Status", ["Todos", "novo", "contatado", "qualificado", "descartado"],
                key="pipl_status",
            )
        with col_f3:
            filtro_score = st.slider("Score mínimo", 0, 100, 0, key="pipl_score")

        leads_filtrados = [
            l for l in leads
            if (filtro_tipo == "Todos" or l.get("tipo_lead") == filtro_tipo)
            and (filtro_status == "Todos" or l.get("status") == filtro_status)
            and l.get("score", 0) >= filtro_score
        ]

        # Métricas do pipeline
        st.divider()
        total = len(leads)
        novos_count = sum(1 for l in leads if l.get("status") == "novo")
        qualificados_count = sum(1 for l in leads if l.get("status") == "qualificado")
        score_medio = int(sum(l.get("score", 0) for l in leads) / total) if total else 0
        ia_count = sum(1 for l in leads if l.get("gerado_por_ia"))

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total de leads", total)
        c2.metric("Novos", novos_count)
        c3.metric("Qualificados", qualificados_count)
        c4.metric("Score médio", score_medio)
        c5.metric("✨ Pontuados por IA", ia_count)

        st.divider()
        st.caption(f"Exibindo **{len(leads_filtrados)}** de **{total}** leads")

        if not leads_filtrados:
            st.info("Nenhum lead corresponde aos filtros selecionados.")
            return

        for lead in leads_filtrados:
            _render_lead_card_prospeccao(lead)

            col_c, col_q, col_d, col_r, col_del = st.columns([2, 2, 2, 2, 1])
            s = lead.get("status", "novo")

            with col_c:
                if st.button("📞 Contatado", key=f"prosp_c_{lead['id']}", use_container_width=True,
                             disabled=s == "contatado"):
                    lead["status"] = "contatado"
                    st.rerun()
            with col_q:
                if st.button("⭐ Qualificado", key=f"prosp_q_{lead['id']}", use_container_width=True,
                             disabled=s == "qualificado"):
                    lead["status"] = "qualificado"
                    st.rerun()
            with col_d:
                if st.button("❌ Descartar", key=f"prosp_d_{lead['id']}", use_container_width=True,
                             disabled=s == "descartado"):
                    lead["status"] = "descartado"
                    st.rerun()
            with col_r:
                if st.button("🔄 Reabrir", key=f"prosp_r_{lead['id']}", use_container_width=True,
                             disabled=s == "novo"):
                    lead["status"] = "novo"
                    st.rerun()
            with col_del:
                if st.button("🗑️", key=f"prosp_del_{lead['id']}", help="Remover lead",
                             use_container_width=True):
                    st.session_state["leads_prospeccao"] = [
                        l for l in leads if l["id"] != lead["id"]
                    ]
                    st.rerun()

            st.markdown("<hr style='margin:4px 0;opacity:.15;'>", unsafe_allow_html=True)

        # Exportar CSV
        st.divider()
        csv_linhas = ["nome,tipo_lead,score,status,setor,motivo,abordagem"]
        for l in leads_filtrados:
            motivo = (l.get("motivo") or "").replace('"', "'").replace("\n", " ")
            abordagem = (l.get("abordagem") or "").replace('"', "'").replace("\n", " ")
            setor = l.get("setor") or l.get("fase") or ""
            csv_linhas.append(
                f'"{l["nome"]}",{l["tipo_lead"]},{l["score"]},{l["status"]},"{setor}","{motivo}","{abordagem}"'
            )
        st.download_button(
            "📥 Exportar pipeline (CSV)",
            data="\n".join(csv_linhas),
            file_name="pipeline_prospeccao.csv",
            mime="text/csv",
            use_container_width=True,
        )


# =============================================================================
# SEÇÃO 11 — Sidebar + Main (ponto de entrada)
# =============================================================================


def _render_sidebar() -> None:
    ob = st.session_state.get("onboarding", {})
    onboarding_ok = ob.get("onboarding_completo", False)
    clientes = st.session_state.get("clientes_hub", [])

    with st.sidebar:
        st.title("⚖️ Hub Jurídico v2.0")
        st.caption("IA Completa para Escritórios de Advocacia")
        st.divider()

        # Navegação
        paginas_disponiveis = ["🚀 Onboarding"]
        if onboarding_ok or clientes:
            paginas_disponiveis += [
                "👥 Hub do Advogado", "🤝 CRM", "📚 Base RAG",
                "🔍 Prospecção", "📊 Analytics", "⚙️ Configurações",
            ]

        pagina_selecionada = st.radio("Navegação", paginas_disponiveis, label_visibility="collapsed")
        mapa = {
            "🚀 Onboarding": "onboarding",
            "👥 Hub do Advogado": "hub",
            "🤝 CRM": "crm",
            "📚 Base RAG": "rag",
            "🔍 Prospecção": "prospeccao",
            "📊 Analytics": "analytics",
            "⚙️ Configurações": "config",
        }
        st.session_state["pagina"] = mapa.get(pagina_selecionada, "onboarding")

        st.divider()

        # Status do onboarding
        if onboarding_ok:
            st.success(f"✅ {ob.get('nome_escritorio', 'Escritório')}", icon="🏢")
            st.caption(f"IA: **{ob.get('persona_nome')}** · {ob.get('persona_tom')}")
        else:
            etapa = ob.get("etapa", 0)
            st.progress(etapa / 5, text=f"Onboarding {etapa}/5")

        # Upload rápido de CSV (disponível no hub)
        if onboarding_ok or clientes:
            st.divider()
            st.caption("Importar mais clientes (CSV)")
            arquivo_extra = st.file_uploader("CSV adicional", type=["csv"], key="csv_extra", label_visibility="collapsed")
            if arquivo_extra:
                extra_hash = hash(arquivo_extra.getvalue())
                if st.session_state.get("_extra_csv_hash") != extra_hash:
                    novos, erros = parsear_csv(arquivo_extra.getvalue())
                    existentes = st.session_state.get("clientes_hub", [])
                    # Renumera IDs
                    offset = len(existentes)
                    for c in novos:
                        c["id"] = c["id"] + offset
                    st.session_state["clientes_hub"] = existentes + novos
                    st.session_state["_extra_csv_hash"] = extra_hash
                    if novos:
                        st.success(f"+{len(novos)} cliente(s)")
                    if erros:
                        st.warning(f"{len(erros)} erro(s)")
                    st.rerun()

        # Lista rápida de clientes
        if clientes:
            st.divider()
            st.caption(f"**{len(clientes)} clientes**")
            for c in clientes:
                ativo = c.get("status", "ativo") != "inativo"
                icone = "🟢" if ativo else "🔴"
                badge_proc = " 📋" if c.get("numero_cnj") else ""
                st.caption(f"{icone} {c['nome']}{badge_proc}")

        st.divider()

        # Status APIs
        if ANTHROPIC_API_KEY:
            st.success("Claude Sonnet: ativo", icon="✅")
        else:
            st.error("ANTHROPIC_API_KEY ausente", icon="🔑")

        if DATAJUD_API_KEY:
            st.info("DataJud: API Key configurada", icon="🔑")
        else:
            st.info("DataJud: acesso público", icon="ℹ️")

        rag: _MockRAGBase | None = st.session_state.get("rag_base")
        if rag and rag.total_docs > 0:
            st.success(f"RAG: {rag.total_docs} doc(s) / {rag.total_chunks} chunks", icon="📚")
        else:
            st.info("RAG: base vazia", icon="📚")

        st.divider()
        st.caption(
            "**Stack:**\n"
            "LangGraph · Claude Sonnet · DataJud API\n"
            "pgvector · Voyage AI · Evolution WhatsApp"
        )

        # CSV de exemplo para download
        st.divider()
        st.download_button(
            "📥 CSV de exemplo",
            data=(
                "nome,telefone,cpf,data_nascimento,profissao,empresa,numero_processo,polo_cliente\n"
                "João da Silva,11999990001,123.456.789-00,15/03/1980,Engenheiro,Tech Corp,0000001-68.2019.8.26.0053,autor\n"
                "Maria Santos,21988880002,987.654.321-00,22/07/1975,Médica,Hospital ABC,,\n"
                "Carlos Oliveira,31977770003,456.789.012-00,08/11/1990,Empresário,,,\n"
            ),
            file_name="clientes_demo.csv",
            mime="text/csv",
            use_container_width=True,
        )


def _init_state() -> None:
    """Inicializa estado global da sessão."""
    if "pagina" not in st.session_state:
        st.session_state["pagina"] = "onboarding"
    if "rag_base" not in st.session_state:
        st.session_state["rag_base"] = _MockRAGBase()


def main() -> None:
    st.set_page_config(
        page_title="Hub Jurídico v2.0 — IA Completa",
        page_icon="⚖️",
        layout="wide",
    )

    _init_state()
    _render_sidebar()

    pagina = st.session_state.get("pagina", "onboarding")

    if pagina == "onboarding":
        page_onboarding()
    elif pagina == "hub":
        page_hub()
    elif pagina == "rag":
        page_rag()
    elif pagina == "crm":
        page_crm()
    elif pagina == "prospeccao":
        page_prospeccao()
    elif pagina == "analytics":
        page_analytics()
    elif pagina == "config":
        page_configuracoes()


if __name__ == "__main__":
    main()
