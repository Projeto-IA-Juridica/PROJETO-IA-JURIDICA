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

import anthropic as _anthropic

from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
from feature_1_ia_personalizada.services.ai.memory import ConversationMemory
from feature_1_ia_personalizada.services.ai.orchestrator import ConversationOrchestrator
from feature_1_ia_personalizada.services.ai.prompts import (
    gerar_instrucao_persona,
    SYSTEM_PROMPT_HUB_ADVOGADO_BASE,
    SYSTEM_PROMPT_HUB_ANALISE_PETICAO,
    SYSTEM_PROMPT_HUB_PESQUISA_JURISPRUDENCIA,
    SYSTEM_PROMPT_HUB_INSIGHT_CLIENTE,
    SYSTEM_PROMPT_HUB_RESUMO_PROCESSO,
)
from feature_1_ia_personalizada.services.ai.translator import JuridicalTranslator
from feature_1_ia_personalizada.services.ai.hub_advogado_classifier import (
    HubAdvogadoClassificador,
    IntencaoAdvogado,
)
from feature_1_ia_personalizada.services.legal_data.datajud_client import DataJudClient
from feature_1_ia_personalizada.services.legal_data.score_risco import ScoreRiscoCalculator
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

# ── Modelo barato para demo (troca por claude-opus-4-6 em produção) ───────────
# Haiku 4.5 custa ~$0.80/M input e $4/M output — ideal para testes sem gastar.
_MODELO_HUB_DEMO = "claude-haiku-4-5-20251001"

# ── Instâncias globais (stateless, seguras para reuso) ────────────────────────

_score_calculator = ScoreRiscoCalculator()
_hub_classificador = HubAdvogadoClassificador()


# =============================================================================
# SEÇÃO HUB DO ADVOGADO — Cliente leve para o demo (modelo Haiku)
# =============================================================================


class _EscalacaoDemo:
    """
    Substituto leve do EscalationClient para o demo Streamlit.

    Usa o modelo Haiku (barato/rápido) em vez do Opus para não consumir tokens
    desnecessariamente durante testes. A interface é idêntica ao EscalacaoClient
    real — trocar _MODELO_HUB_DEMO por "claude-opus-4-6" ativa a versão produção.
    """

    _MAX_TOKENS = 1024  # suficiente para testes; Opus usa 2048

    def __init__(self) -> None:
        self._client = _anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    async def gerar_resposta(self, system_prompt: str, mensagem: str) -> dict:
        """Retorna dict com conteudo, tokens_input, tokens_output."""
        inicio = time.perf_counter()
        resp = await self._client.messages.create(
            model=_MODELO_HUB_DEMO,
            max_tokens=self._MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": mensagem}],
        )
        latencia = int((time.perf_counter() - inicio) * 1000)
        texto = "".join(b.text for b in resp.content if hasattr(b, "text"))
        return {
            "conteudo": texto,
            "tokens_input": resp.usage.input_tokens,
            "tokens_output": resp.usage.output_tokens,
            "latencia_ms": latencia,
            "modelo": _MODELO_HUB_DEMO,
        }

    async def analisar_peticao(self, texto_pdf: str) -> dict:
        """Analisa petição PDF. Retorna dict com os campos estruturados."""
        system = SYSTEM_PROMPT_HUB_ANALISE_PETICAO.format(
            data_hoje=date.today().strftime("%d/%m/%Y")
        )
        prompt = (
            "Analise a petição abaixo e responda EXATAMENTE no formato JSON:\n"
            "{\n"
            '  "tipo_peca": "...",\n'
            '  "pontos_fortes": ["...", "..."],\n'
            '  "vulnerabilidades": ["...", "..."],\n'
            '  "argumentos_ausentes": ["..."],\n'
            '  "precedentes_relevantes": ["..."],\n'
            '  "sugestoes": ["..."],\n'
            '  "score_geral": 75\n'
            "}\n\n"
            f"PETIÇÃO:\n{texto_pdf[:8000]}"
        )
        resultado = await self.gerar_resposta(system, prompt)
        conteudo = resultado["conteudo"].strip()
        # Extrair JSON do bloco de markdown se presente
        if "```json" in conteudo:
            conteudo = conteudo.split("```json")[1].split("```")[0].strip()
        elif "```" in conteudo:
            conteudo = conteudo.split("```")[1].split("```")[0].strip()
        try:
            import json as _json

            dados = _json.loads(conteudo)
        except Exception:
            dados = {
                "tipo_peca": "Não identificado",
                "pontos_fortes": [],
                "vulnerabilidades": ["Não foi possível estruturar a análise"],
                "argumentos_ausentes": [],
                "precedentes_relevantes": [],
                "sugestoes": ["Tente reenviar o documento"],
                "score_geral": 0,
            }
        dados["tokens_input"] = resultado["tokens_input"]
        dados["tokens_output"] = resultado["tokens_output"]
        dados["latencia_ms"] = resultado.get("latencia_ms", 0)
        return dados

    async def pesquisar_jurisprudencia(self, query: str, tribunais: str = "STJ, STF, TJs") -> dict:
        """Pesquisa jurisprudência sobre a query informada."""
        system = SYSTEM_PROMPT_HUB_PESQUISA_JURISPRUDENCIA.format(
            query=query,
            tribunais=tribunais,
            periodo="últimos 5 anos",
        )
        return await self.gerar_resposta(system, f"Pesquise jurisprudência sobre: {query}")


class _SessoesEmRam:
    """Histórico de sessões Hub do Advogado armazenado em memória (demo)."""

    def __init__(self) -> None:
        self._sessoes: list[dict] = []

    def registrar(
        self,
        intencao: str,
        mensagem: str,
        resposta: str,
        tokens_in: int,
        tokens_out: int,
    ) -> None:
        self._sessoes.append(
            {
                "id": len(self._sessoes) + 1,
                "intencao": intencao,
                "mensagem_preview": mensagem[:100],
                "mensagem_completa": mensagem,
                "resposta": resposta,
                "tokens_input": tokens_in,
                "tokens_output": tokens_out,
                "custo_usd": round((tokens_in * 0.8 + tokens_out * 4.0) / 1_000_000, 6),
                "criado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
            }
        )

    @property
    def todas(self) -> list[dict]:
        return list(reversed(self._sessoes))

    @property
    def total_tokens(self) -> tuple[int, int]:
        return (
            sum(s["tokens_input"] for s in self._sessoes),
            sum(s["tokens_output"] for s in self._sessoes),
        )

    @property
    def custo_total(self) -> float:
        return sum(s["custo_usd"] for s in self._sessoes)

    def contagem_por_intencao(self) -> dict[str, int]:
        contagem: dict[str, int] = {}
        for s in self._sessoes:
            contagem[s["intencao"]] = contagem.get(s["intencao"], 0) + 1
        return contagem


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
        return (
            f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:]}"
        )
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
            resp = await client.post(
                url, json={"query": {"match": {"numeroProcesso": digits}}}, headers=headers
            )
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
        "tempo_medio_tramitacao_dias": (
            dados_dj.get("tempo_medio_tramitacao_dias") if dados_dj else None
        ),
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
    return {"baixo": "#2e7d32", "moderado": "#f57c00", "alto": "#c62828", "critico": "#6a1b9a"}.get(
        nivel, "#555"
    )


def _explicacao_nivel(nivel: str) -> str:
    return {
        "baixo": (
            "Este processo apresenta **baixo risco**. As condições são favoráveis: "
            "o tipo de ação tem bom histórico neste tribunal, o prazo estimado é razoável "
            "e não há fatores agravantes identificados. Você pode atender este cliente "
            "com tranquilidade."
        ),
        "moderado": (
            "Este processo tem **risco moderado**. Há alguns pontos de atenção — como o tipo "
            "de ação ou o histórico da vara — que merecem acompanhamento próximo. "
            "Recomendamos manter o cliente bem informado sobre cada andamento."
        ),
        "alto": (
            "Este processo apresenta **alto risco**. Fatores como complexidade da ação, "
            "valor em disputa ou histórico desfavorável no tribunal aumentam a incerteza. "
            "Vale redobrar a atenção e alinhar expectativas reais com o cliente."
        ),
        "critico": (
            "Atenção: este processo está em situação **crítica**. Múltiplos fatores de risco "
            "foram identificados simultaneamente. É importante conversar pessoalmente com o "
            "cliente, revisando a estratégia e os riscos envolvidos com transparência."
        ),
    }.get(nivel, "Análise disponível após consulta ao tribunal.")


def _render_score_card(score_data: dict) -> None:
    score = score_data["score"]
    nivel = score_data["nivel"]
    comp = score_data["componentes"]
    cor = _cor_nivel(nivel)
    emojis = {"baixo": "🟢", "moderado": "🟡", "alto": "🔴", "critico": "🟣"}
    emoji = emojis.get(nivel, "⚪")
    rotulos = {
        "baixo": "RISCO BAIXO — Processo favorável",
        "moderado": "RISCO MODERADO — Atenção recomendada",
        "alto": "RISCO ALTO — Acompanhamento próximo necessário",
        "critico": "RISCO CRÍTICO — Ação imediata recomendada",
    }
    rotulo = rotulos.get(nivel, nivel.upper())
    st.markdown(
        f"""
        <div style="border:1.5px solid {cor};border-radius:10px;padding:14px 18px;
                    background:{cor}18;margin-bottom:8px;">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
                <span style="font-size:13px;font-weight:600;color:{cor};text-transform:uppercase;
                             letter-spacing:.05em;">{emoji} Análise de Risco do Processo</span>
                <span style="font-size:22px;font-weight:700;color:{cor};">
                    {rotulo.split('—')[0].strip()}
                </span>
            </div>
            <div style="background:#e0e0e0;border-radius:4px;height:7px;margin-bottom:10px;">
                <div style="width:{score}%;background:{cor};height:7px;border-radius:4px;"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(_explicacao_nivel(nivel))
    with st.expander("Como chegamos a esta análise? Ver detalhes"):
        nomes = {
            "complexidade_juridica": (
                "Complexidade da Ação",
                "Quão complexo é este tipo de processo juridicamente",
            ),
            "duracao_estimada": (
                "Tempo Estimado",
                "Quanto tempo processos similares costumam durar neste tribunal",
            ),
            "historico_vara": (
                "Histórico da Vara",
                "Como este juízo costuma decidir casos parecidos",
            ),
            "valor_causa": ("Valor em Disputa", "O impacto financeiro da causa no resultado"),
            "fase_processual": (
                "Fase do Processo",
                "Em que momento o processo se encontra atualmente",
            ),
        }
        for chave, valor in comp.items():
            label, descricao = nomes.get(chave, (chave, ""))
            bc = _cor_nivel("alto" if valor >= 75 else "moderado" if valor >= 40 else "baixo")
            nivel_fator = "alto" if valor >= 75 else "moderado" if valor >= 40 else "baixo"
            texto_nivel = {"baixo": "favorável", "moderado": "atenção", "alto": "desfavorável"}.get(
                nivel_fator, ""
            )
            st.markdown(
                f"""<div style="margin-bottom:10px;">
                    <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
                        <span style="color:#444;font-weight:600;">{label}</span>
                        <span style="font-weight:600;color:{bc};">{texto_nivel}</span>
                    </div>
                    <div style="background:#e0e0e0;border-radius:3px;height:5px;margin-bottom:3px;">
                        <div style="width:{valor}%;background:{bc};height:5px;border-radius:3px;"></div>
                    </div>
                    <div style="font-size:11px;color:#888;">{descricao}</div>
                    </div>""",
                unsafe_allow_html=True,
            )
        st.caption(
            "⚠️ Esta análise é de uso interno do advogado e não representa previsão de resultado (OAB Provimento 205/2021)."
        )


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
            self._chunks.append(
                {
                    "id": f"{hashlib.md5(chunk.encode()).hexdigest()[:8]}",
                    "titulo": titulo,
                    "tipo": tipo,
                    "texto": chunk,
                    "keywords": self._keywords(chunk),
                }
            )
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
        return "<contexto_juridico>\n" + "\n\n---\n\n".join(partes) + "\n</contexto_juridico>"

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


def _fake_datajud(dados_dj: dict | None) -> DataJudClient:
    client = AsyncMock(spec=DataJudClient)
    if dados_dj:
        movimentos = dados_dj.get("movimentos", [])
        andamentos = [
            {"descricao": m.get("nome", ""), "data": (m.get("dataHora") or "")[:10]}
            for m in movimentos
            if isinstance(m, dict) and m.get("nome")
        ]
    else:
        andamentos = []
    client.buscar_andamentos_async = AsyncMock(return_value=andamentos)
    return client


def _fake_cache() -> MagicMock:
    cache = AsyncMock()
    cache._redis = AsyncMock()
    cache._redis.get = AsyncMock(return_value=None)  # cache miss → gera persona do escritorio
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
      - _fake_datajud: andamentos do DataJud injetados no cliente fake
      - _fake_cache: cache miss → orchestrator busca dados frescos
      - _MockRAGRetriever: conecta _MockRAGBase ao pipeline do orchestrator
        (await self._rag.buscar → injeção do bloco <contexto_juridico> no system_prompt)
      - FactChecker: habilitado com session_factory mockada que retorna dados reais
    """
    memoria = _MemoriaEmRam()

    # RAG: envolve a base in-memory com a interface que o orchestrator espera
    rag_retriever = (
        _MockRAGRetriever(rag_base) if (rag_base and rag_base.total_chunks > 0) else None
    )

    orchestrator = ConversationOrchestrator(
        claude_client=ClaudeClient(api_key=ANTHROPIC_API_KEY),
        memory=memoria,
        translator=JuridicalTranslator(),
        datajud_client=_fake_datajud(dados_dj),
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


def _fragmentar_resposta(texto: str) -> list[str]:
    """
    Divide uma resposta longa em partes menores para simular digitação humana.

    Regras:
    - Divide por parágrafos (\\n\\n)
    - Agrupa partes muito curtas (< 80 chars) com a seguinte para evitar bolhas pequenas demais
    - Nunca divide no meio de uma frase
    - Retorna lista com 1 a 4 partes no máximo
    """
    partes_raw = [p.strip() for p in texto.split("\n\n") if p.strip()]
    if len(partes_raw) <= 1:
        return [texto.strip()] if texto.strip() else []

    resultado: list[str] = []
    acumulado = ""
    for parte in partes_raw:
        if not acumulado:
            acumulado = parte
        elif len(acumulado) < 80:
            # Parte muito curta: junta com a próxima
            acumulado = acumulado + "\n\n" + parte
        else:
            resultado.append(acumulado)
            acumulado = parte
    if acumulado:
        resultado.append(acumulado)

    # Limita a 4 bolhas para não fragmentar demais
    if len(resultado) > 4:
        meio = "\n\n".join(resultado[1:-1])
        resultado = [resultado[0], meio, resultado[-1]]

    return resultado


def _delay_digitacao(texto: str) -> float:
    """
    Calcula um delay realista de 'digitando' com base no tamanho do texto.
    Simula velocidade humana (~45 palavras/min), entre 1.0s e 3.5s.
    """
    palavras = len(texto.split())
    return max(1.0, min(3.5, palavras * 0.09))


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
            nomes_comp = [
                c.get("nome", "") for c in complementos if isinstance(c, dict) and c.get("nome")
            ]
            if nomes_comp:
                desc_extra = f" — {', '.join(nomes_comp[:2])}"
        st.markdown(f"- **{data}** — {nome}{desc_extra}")


# =============================================================================
# SEÇÃO 6 — PÁGINA: Onboarding (Feature 4)
# =============================================================================


def page_onboarding() -> None:
    ob = st.session_state.setdefault(
        "onboarding",
        {
            "etapa": 0,
            "onboarding_completo": False,
            "nome_escritorio": "",
            "cnpj": "",
            "email_admin": "",
            "nome_responsavel": "",
            "oab_responsavel": "",
            "persona_nome": "Assistente Jurídico",
            "persona_tom": "formal",
            "horario_inicio": "08:00",
            "horario_fim": "18:00",
            "clientes_importados": [],
            "erros_importacao": [],
            "whatsapp_ok": False,
            "template_boas_vindas": "Olá {nome_cliente}! Seja bem-vindo(a) ao nosso escritório. Como posso ajudar?",
            "template_atualizacao": "Olá {nome_cliente}! Há novidades no seu processo: {resumo_andamento}",
            "template_sem_novidade": "Olá {nome_cliente}, consultamos seu processo e não há novidades por enquanto.",
        },
    )

    st.title("🚀 Configure seu Escritório")
    st.caption(
        "Siga as 5 etapas abaixo e em 30 minutos sua IA estará pronta para atender seus clientes."
    )

    etapa = ob["etapa"]
    nomes_etapas = [
        "📋 Cadastro",
        "🤖 Configurar IA",
        "📂 Importar Clientes",
        "💬 WhatsApp",
        "📝 Templates",
        "🚀 Go-Live",
    ]
    progress = etapa / 5.0
    st.progress(progress, text=f"Etapa {etapa}/5 — {nomes_etapas[min(etapa, 5)]}")
    st.divider()

    # ── Etapa 0: Cadastro do Escritório ──────────────────────────────────────
    if etapa == 0:
        st.subheader("📋 Etapa 1 — Dados do Escritório")
        st.caption(
            "Crie a conta do seu escritório. Esta etapa é pública — nenhum token necessário."
        )
        with st.form("form_register"):
            col1, col2 = st.columns(2)
            with col1:
                nome_esc = st.text_input(
                    "Nome do Escritório *", value=ob.get("nome_escritorio", "")
                )
                cnpj = st.text_input(
                    "CNPJ *", value=ob.get("cnpj", ""), placeholder="11.222.333/0001-81"
                )
                email = st.text_input("E-mail do Administrador *", value=ob.get("email_admin", ""))
            with col2:
                nome_resp = st.text_input(
                    "Nome do Responsável *", value=ob.get("nome_responsavel", "")
                )
                oab = st.text_input(
                    "OAB do Responsável *",
                    value=ob.get("oab_responsavel", ""),
                    placeholder="SP123456",
                )
                senha = st.text_input("Senha *", type="password", help="Mínimo 8 caracteres")

            st.caption("(*) Campos obrigatórios")
            submitted = st.form_submit_button(
                "Registrar Escritório →", use_container_width=True, type="primary"
            )

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
                ob.update(
                    {
                        "etapa": 1,
                        "nome_escritorio": nome_esc.strip(),
                        "cnpj": cnpj_digits,
                        "email_admin": email.strip(),
                        "nome_responsavel": nome_resp.strip(),
                        "oab_responsavel": oab.upper().strip(),
                    }
                )
                st.success("✅ Escritório cadastrado! Avançando para configuração da IA...")
                time.sleep(0.5)
                st.rerun()

    # ── Etapa 1: Configurar IA / Persona ─────────────────────────────────────
    elif etapa == 1:
        st.subheader("🤖 Etapa 2 — Configure como a IA vai se apresentar")
        st.caption(
            "Dê um nome e uma personalidade para a sua IA. "
            "Ela vai usar essa identidade em todas as conversas com seus clientes."
        )

        with st.container(border=True):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Identidade da IA**")
                prev_nome = st.text_input(
                    "Como a IA vai se chamar?",
                    value=ob.get("persona_nome", "Assistente Jurídico"),
                    help='Ex: "Dra. Camila", "Atendimento Jurídico", "Assistente do Escritório"',
                )
                prev_tom = st.selectbox(
                    "Tom de voz",
                    ["formal", "amigavel", "neutro"],
                    index=["formal", "amigavel", "neutro"].index(ob.get("persona_tom", "formal")),
                    format_func=lambda x: {
                        "formal": "Formal (protocolar, distante)",
                        "amigavel": "Amigável (próximo, acolhedor)",
                        "neutro": "Neutro (equilibrado)",
                    }.get(x, x),
                )
            with col2:
                st.markdown("**Horário de Atendimento Automático**")
                h_ini = st.text_input(
                    "A partir de", value=ob.get("horario_inicio", "08:00"), placeholder="HH:MM"
                )
                h_fim = st.text_input(
                    "Até", value=ob.get("horario_fim", "18:00"), placeholder="HH:MM"
                )
                st.caption(
                    "Fora deste horário, a IA informa o cliente que o escritório está fechado."
                )

        # Preview humano da persona
        _preview_tom = {
            "formal": "de forma formal e protocolar",
            "amigavel": "de forma próxima e acolhedora",
            "neutro": "com linguagem equilibrada e profissional",
        }.get(prev_tom, "")
        st.markdown("**Como a IA vai se comportar:**")
        st.info(
            f'A IA vai se apresentar como **"{prev_nome}"**, atender {_preview_tom} '
            f"e responder mensagens entre **{h_ini}** e **{h_fim}**."
        )

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
                    ob.update(
                        {
                            "etapa": 2,
                            "persona_nome": prev_nome.strip(),
                            "persona_tom": prev_tom,
                            "horario_inicio": h_ini,
                            "horario_fim": h_fim,
                        }
                    )
                    st.success(f"✅ IA '{prev_nome}' configurada (tom: {prev_tom})")
                    time.sleep(0.5)
                    st.rerun()

    # ── Etapa 2: Importar Clientes / Processos ────────────────────────────────
    elif etapa == 2:
        st.subheader("📂 Etapa 3 — Importar Clientes e Processos")
        st.caption("Faça upload do CSV. O sistema valida o CNJ e consulta o DataJud em tempo real.")

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
                st.info(
                    f"📋 {len(com_cnj)} com número de processo (CNJ) — serão consultados no DataJud"
                )

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
                                nome_classe = (
                                    classe.get("nome", "—")
                                    if isinstance(classe, dict)
                                    else str(classe)
                                )
                                tribunal = dados.get("tribunal", {})
                                nome_trib = (
                                    tribunal.get("nome", "—")
                                    if isinstance(tribunal, dict)
                                    else str(tribunal)
                                )
                                st.caption(f"   ✅ DataJud: {nome_classe} — {nome_trib}")
                            else:
                                st.caption(
                                    f"   ⚠️ DataJud: processo `{c['numero_cnj']}` não encontrado"
                                )
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
            if st.button(
                "Salvar e Avançar →",
                use_container_width=True,
                type="primary",
                disabled=not pode_avancar,
            ):
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
                st.markdown(
                    """
                **Em produção:**
                1. Abra o WhatsApp Business no celular
                2. Acesse Configurações → Dispositivos Vinculados
                3. Escaneie o QR code ao lado
                4. Aguarde a conexão (≈ 10 segundos)

                **Tecnologia:** Evolution API v2 + webhook para recebimento de mensagens
                """
                )
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
        st.caption(
            "Personalize as mensagens automáticas. Use `{nome_cliente}` e `{resumo_andamento}` como placeholders."
        )

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
            submitted = st.form_submit_button(
                "Salvar Templates →", type="primary", use_container_width=True
            )

        if submitted:
            erros = []
            if "{nome_cliente}" not in t_bv:
                erros.append("Template de boas-vindas deve conter {nome_cliente}")
            if "{nome_cliente}" not in t_at or "{resumo_andamento}" not in t_at:
                erros.append(
                    "Template de atualização deve conter {nome_cliente} e {resumo_andamento}"
                )
            if "{nome_cliente}" not in t_sn:
                erros.append("Template 'sem novidade' deve conter {nome_cliente}")
            if erros:
                for e in erros:
                    st.error(e)
            else:
                ob.update(
                    {
                        "etapa": 5,
                        "template_boas_vindas": t_bv,
                        "template_atualizacao": t_at,
                        "template_sem_novidade": t_sn,
                    }
                )
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

        st.markdown(
            """
        ### Seu escritório está pronto!

        | O que foi configurado | Status |
        |-----------------------|--------|
        | IA com identidade do seu escritório | ✅ Configurada |
        | Análise automática de risco dos processos | ✅ Ativa |
        | Personalização com documentos do escritório | ✅ Pronta para receber documentos |
        | Cadastro e configuração do escritório | ✅ Concluído |
        """
        )

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
    if (
        orch_key not in st.session_state
        or st.session_state.get(rag_chunks_key, -1) != rag_chunks_agora
    ):
        if ANTHROPIC_API_KEY:
            orchestrator, memoria = criar_orchestrator(ob, cliente, dados_dj, rag_base=rag_base)
            st.session_state[orch_key] = orchestrator
            st.session_state[f"mem_{cid}"] = memoria
            st.session_state[rag_chunks_key] = rag_chunks_agora
        else:
            st.session_state[orch_key] = None
        if (
            orch_key not in st.session_state
            or st.session_state.get(rag_chunks_key, -1) != rag_chunks_agora
        ):
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
        st.markdown(
            _tabela_md(
                [
                    ("Nome", cliente["nome"]),
                    ("Telefone", f"`{cliente['telefone']}`"),
                    ("CPF", cliente["cpf"]),
                    ("Nascimento", cliente.get("data_nascimento") or "—"),
                    ("Profissão", cliente.get("profissao") or "—"),
                    ("Empresa", cliente.get("empresa") or "—"),
                    ("Status", "🟢 Ativo" if cliente.get("status") != "inativo" else "🔴 Inativo"),
                ]
            )
        )

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
            assunto_str = (
                ", ".join(
                    a.get("nome", "") if isinstance(a, dict) else str(a) for a in assuntos[:2]
                )
                or "—"
            )
            movimentos = dados_dj.get("movimentos", [])
            ultimo = movimentos[0] if movimentos else {}
            data_ajuiz = (dados_dj.get("dataAjuizamento") or "")[:10] or "—"
            st.markdown(
                _tabela_md(
                    [
                        ("CNJ", f"`{cliente['numero_cnj']}`"),
                        ("Tribunal", nome_trib),
                        ("Classe", nome_classe),
                        ("Assunto(s)", assunto_str),
                        ("Polo", (cliente.get("polo_cliente") or "—").upper()),
                        ("Ajuizamento", data_ajuiz),
                        (
                            "Último Andamento",
                            (ultimo.get("nome", "—") if isinstance(ultimo, dict) else "—"),
                        ),
                        (
                            "Data",
                            (
                                (ultimo.get("dataHora") or "")[:10]
                                if isinstance(ultimo, dict)
                                else "—"
                            ),
                        ),
                    ]
                )
            )
            st.success("Dados do processo consultados no tribunal com sucesso.", icon="✅")

            if len(movimentos) > 1:
                with st.expander("📜 Ver andamentos anteriores do processo"):
                    _render_andamentos(dados_dj)
        else:
            st.markdown(
                _tabela_md(
                    [
                        ("CNJ", f"`{cliente['numero_cnj']}`"),
                        ("Polo", (cliente.get("polo_cliente") or "—").upper()),
                        ("DataJud", "Processo não encontrado"),
                    ]
                )
            )
            st.warning(
                "Processo não encontrado no DataJud. O orchestrator responde com dados do cadastro.",
                icon="⚠️",
            )

    # ── Score de Risco ────────────────────────────────────────────────────────
    if cliente.get("numero_cnj"):
        st.markdown("#### 🔒 Análise de Risco — Painel do Advogado")
        score_data = _calcular_score(cliente, dados_dj)
        if score_data:
            _render_score_card(score_data)
        else:
            st.info("Score disponível após consulta ao DataJud com dados de classe processual.")

    # ── Status documentos do escritório ──────────────────────────────────────
    if rag_base and rag_base.total_chunks > 0:
        query_preview = f"{dados_dj.get('classe', {}).get('nome', '') if dados_dj else ''} {cliente.get('profissao', '')}"
        chunks_preview = rag_base.buscar(query_preview.strip() or "jurídico", top_k=3)
        if chunks_preview:
            _TIPO_LABEL_HUB = {
                "peticao": "Petição",
                "sentenca": "Sentença",
                "jurisprudencia": "Jurisprudência",
                "tese": "Tese / Argumento",
                "parecer": "Parecer / FAQ",
            }
            with st.expander(
                f"📚 IA personalizada com {rag_base.total_docs} documento(s) do seu escritório — clique para ver quais serão usados"
            ):
                st.caption(
                    "Estes são os documentos que a IA vai consultar ao responder perguntas sobre este cliente:"
                )
                for ch in chunks_preview:
                    tipo_nome = _TIPO_LABEL_HUB.get(ch["tipo"], ch["tipo"])
                    st.markdown(f"**{tipo_nome}: {ch['titulo']}**")
                    st.caption(ch["texto"][:250] + "..." if len(ch["texto"]) > 250 else ch["texto"])
        else:
            st.info(
                f"📚 {rag_base.total_docs} documento(s) do escritório disponíveis — nenhum específico para este processo ainda."
            )
    elif rag_base is not None:
        st.caption(
            "📚 Nenhum documento enviado ainda — acesse **Documentos do Escritório** para personalizar a IA."
        )

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
        st.session_state[chat_key].append(
            {
                "role": "assistant",
                "content": boas_vindas,
                "meta": {"intencao": intencao_bv, "fallback": fallback_bv},
            }
        )
        st.session_state[welcome_key] = True

    # Header do chat
    st.markdown(f"#### 💬 Converse com {ob.get('persona_nome', 'o Assistente Jurídico')}")
    st.caption(
        f"A IA está configurada com a identidade **{ob.get('persona_nome')}** "
        f"e tom de voz **{ob.get('persona_tom')}**. Ela verifica fatos antes de responder."
    )

    _ROTULOS_INTENCAO = {
        "saudacao": "Boas-vindas",
        "status_processo": "Consulta de andamento",
        "duvida_termo": "Dúvida sobre termo jurídico",
        "perspectivas": "Perspectivas do caso",
        "parecer_juridico": "Pedido de parecer jurídico",
        "estrategia_processual": "Estratégia processual",
        "negociacao": "Negociação / acordo",
        "decisao_judicial_impacto_alto": "Decisão de alto impacto",
        "prazo": "Consulta de prazo",
        "honorarios": "Honorários",
        "outro": "Atendimento geral",
        "erro": "Resposta de fallback",
    }

    # Histórico
    for msg in st.session_state[chat_key]:
        avatar = "⚖️" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            # Partes de continuação (bolhas 2+) não mostram badges
            if (
                msg["role"] == "assistant"
                and msg.get("meta")
                and not msg["meta"].get("continuation")
            ):
                meta = msg["meta"]
                badges = []
                intencao = meta.get("intencao", "")
                rotulo = _ROTULOS_INTENCAO.get(intencao, "")
                if rotulo:
                    badges.append(f"_{rotulo}_")
                if meta.get("rag_ativo"):
                    badges.append("📚 Usando documentos do escritório")
                _ESCALACAO_INTENCOES = {
                    "parecer_juridico",
                    "estrategia_processual",
                    "negociacao",
                    "decisao_judicial_impacto_alto",
                }
                if intencao in _ESCALACAO_INTENCOES:
                    badges.append("🚨 Questão importante — advogado notificado")
                if badges:
                    st.caption(" · ".join(badges))

    # ── Buffer de mensagens ───────────────────────────────────────────────────
    # Guarda mensagens enviadas em sequência rápida antes de processar.
    # Quando o usuário envia várias mensagens, elas são combinadas em uma só
    # antes de chegarem à IA — igual ao comportamento humano no WhatsApp.
    buffer_key = f"buffer_{cid}"
    buffer_ts_key = f"buffer_ts_{cid}"
    if buffer_key not in st.session_state:
        st.session_state[buffer_key] = []

    # Input
    prompt = st.chat_input(
        "Pergunte sobre o processo, termos jurídicos ou tire dúvidas...",
        key=f"input_{cid}",
    )

    if prompt and orchestrator:
        # ── 1. Adiciona ao buffer ─────────────────────────────────────────────
        st.session_state[buffer_key].append(prompt)
        st.session_state[buffer_ts_key] = time.time()

        # Mostra mensagem do usuário imediatamente
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)

        # ── 2. Delay de leitura — IA "está lendo" ────────────────────────────
        # Simula o tempo que um humano levaria para ler a mensagem antes de começar a digitar.
        with st.chat_message("assistant", avatar="⚖️"):
            _ph_lendo = st.empty()
            _ph_lendo.markdown("_lendo..._")
            _delay_leitura = max(0.8, min(2.0, len(prompt.split()) * 0.12))
            time.sleep(_delay_leitura)
            _ph_lendo.empty()

        # ── 3. Consolida buffer ───────────────────────────────────────────────
        # Junta todas as mensagens pendentes em uma só antes de enviar à IA.
        msgs_buffer = st.session_state[buffer_key]
        if len(msgs_buffer) > 1:
            mensagem_consolidada = "\n\n".join(msgs_buffer)
        else:
            mensagem_consolidada = msgs_buffer[0]
        st.session_state[buffer_key] = []  # Limpa buffer

        # ── 4. Processa com a IA ──────────────────────────────────────────────
        resposta = ""
        intencao, ti, to, fallback, rag_ativo = "outro", 0, 0, False, False
        with st.chat_message("assistant", avatar="⚖️"):
            _ph_digitando = st.empty()
            _ph_digitando.markdown("_digitando..._")
            try:
                resultado = asyncio.run(
                    orchestrator.processar(
                        escritorio_id=1,
                        cliente_id=1,
                        mensagem=mensagem_consolidada,
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
                resposta = f"Desculpe, ocorreu um erro interno. Tente novamente."
                intencao, ti, to, fallback, rag_ativo = "erro", 0, 0, True, False
            _ph_digitando.empty()

        # ── 5. Divide resposta em partes e exibe com delay de digitação ───────
        _ESCALACAO_INTENCOES = {
            "parecer_juridico",
            "estrategia_processual",
            "negociacao",
            "decisao_judicial_impacto_alto",
        }
        partes_resposta = _fragmentar_resposta(resposta)

        for i, parte in enumerate(partes_resposta):
            # Delay de digitação antes de cada parte (exceto a primeira que já
            # apareceu no lugar do "digitando..." acima)
            if i > 0:
                with st.chat_message("assistant", avatar="⚖️"):
                    _ph_pt = st.empty()
                    _ph_pt.markdown("_digitando..._")
                    time.sleep(_delay_digitacao(parte))
                    _ph_pt.empty()

            with st.chat_message("assistant", avatar="⚖️"):
                st.markdown(parte)
                # Metadata badge apenas na primeira parte
                if i == 0:
                    badges = []
                    rotulo = _ROTULOS_INTENCAO.get(intencao, "")
                    if rotulo:
                        badges.append(f"_{rotulo}_")
                    if rag_ativo:
                        badges.append("📚 Usando documentos do escritório")
                    if intencao in _ESCALACAO_INTENCOES:
                        badges.append("🚨 Questão importante — advogado notificado")
                    if badges:
                        st.caption(" · ".join(badges))

            # Salva cada parte no histórico
            st.session_state[chat_key].append(
                {
                    "role": "assistant",
                    "content": parte,
                    "meta": {
                        "intencao": intencao if i == 0 else None,
                        "tokens_in": ti if i == 0 else 0,
                        "tokens_out": to if i == 0 else 0,
                        "fallback": fallback if i == 0 else False,
                        "rag_ativo": rag_ativo if i == 0 else False,
                        "continuation": i > 0,
                    },
                }
            )

        st.rerun()


# =============================================================================
# SEÇÃO 8 — PÁGINA: Base de Conhecimento RAG (Feature 3)
# =============================================================================


def page_rag() -> None:
    st.title("📚 Personalize a IA com os Documentos do Seu Escritório")
    st.caption(
        "Envie documentos jurídicos do seu escritório — petições, jurisprudências, teses, pareceres. "
        "A IA aprende com eles e passa a responder usando a linguagem e os argumentos que você usa no dia a dia."
    )

    # Inicializa base RAG na sessão
    if "rag_base" not in st.session_state:
        st.session_state["rag_base"] = _MockRAGBase()
    rag: _MockRAGBase = st.session_state["rag_base"]

    # ── Métricas ──────────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    col1.metric("Documentos enviados", rag.total_docs)
    col2.metric("Trechos aprendidos pela IA", rag.total_chunks)

    st.divider()

    # ── Upload ────────────────────────────────────────────────────────────────
    col_upload, col_config = st.columns([2, 1])

    with col_upload:
        st.subheader("📤 Enviar Documento")
        arquivo = st.file_uploader(
            "Selecione um arquivo PDF ou TXT",
            type=["pdf", "txt"],
            help=f"PDF {'✅ suportado' if _FITZ_OK else '⚠️ instale pymupdf para PDF'} · TXT sempre suportado",
        )

        if arquivo:
            col_t, col_tipo = st.columns(2)
            with col_t:
                titulo = st.text_input("Nome do documento", value=arquivo.name.rsplit(".", 1)[0])
            with col_tipo:
                tipo = st.selectbox(
                    "Categoria",
                    ["peticao", "sentenca", "jurisprudencia", "tese", "parecer"],
                    format_func=lambda x: {
                        "peticao": "Petição",
                        "sentenca": "Sentença",
                        "jurisprudencia": "Jurisprudência",
                        "tese": "Tese / Argumento",
                        "parecer": "Parecer / FAQ",
                    }.get(x, x),
                )

            if st.button("📥 Ensinar à IA", type="primary"):
                with st.spinner("Lendo e aprendendo com o documento..."):
                    texto = _extrair_texto(arquivo.getvalue(), arquivo.name)
                    if not texto.strip():
                        st.error("Não foi possível ler o arquivo. Verifique se ele contém texto.")
                    else:
                        n_chunks = rag.adicionar(titulo, tipo, texto)
                        st.success(
                            f"✅ Documento '{titulo}' adicionado com sucesso! "
                            f"A IA já pode usar este material nas respostas."
                        )
                        st.rerun()

    with col_config:
        st.subheader("💡 Como funciona?")
        st.markdown(
            """
        Quando o advogado ou o cliente faz uma pergunta, a IA:

        1. **Identifica** quais documentos do seu escritório são relevantes para aquela pergunta
        2. **Lê** os trechos mais pertinentes automaticamente
        3. **Responde** usando o raciocínio e a linguagem desses documentos

        Quanto mais documentos do seu escritório você enviar, mais a IA vai soar como **você**.
        """
        )

    st.divider()

    # ── Guia: O que colocar na base ───────────────────────────────────────────
    with st.expander(
        "📋 O que enviar para a IA aprender? (recomendações práticas)", expanded=rag.total_docs == 0
    ):
        st.markdown(
            """
        A IA identifica automaticamente a área jurídica do processo do cliente e busca os documentos
        mais relevantes. Por isso, quanto mais focados forem os documentos, melhor ela responde.
        """
        )

        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.markdown("#### Por tipo de documento")
            st.markdown(
                """
🟡 **Jurisprudência** — maior impacto nas respostas
- Acórdãos do TJSP/TRT/STJ da sua área de atuação
- Súmulas aplicáveis aos seus casos
- Decisões similares aos processos dos seus clientes

🟠 **Tese / Argumento** — segundo maior impacto
- Os argumentos que você usa nas suas petições
- Pontos fortes e fracos de cada tipo de ação
- Estratégias que funcionam bem no tribunal

🟢 **Sentença** — contexto processual
- Sentenças em casos similares (anonimizadas)
- Como os juízes da sua comarca costumam fundamentar
- Decisões interlocutórias frequentes no tribunal

🟣 **Parecer / FAQ** — respostas técnicas prontas
- Perguntas frequentes dos seus clientes respondidas
- O que acontece em cada fase do processo
- Explicações que você dá no dia a dia

🔵 **Petição** — linguagem do escritório
- Petições iniciais com os seus argumentos
- Contestações nas suas áreas principais
            """
            )

        with col_g2:
            st.markdown("#### Por área de atuação")
            st.markdown(
                """
⚖️ **Trabalhista**
→ Súmulas do TST · Teses de rescisão indireta e dano moral

🏥 **Cível / Indenizatório**
→ Acórdãos do TJSP por comarca · Como a vara calcula danos morais

💊 **Previdenciário**
→ Jurisprudência do TRF · Teses por tipo de benefício

👨‍👩‍👧 **Família**
→ Jurisprudência sobre pensão e guarda · FAQ de procedimentos

🛒 **Consumidor**
→ Súmulas do STJ aplicadas · Decisões da sua região
            """
            )

            st.markdown("#### Tamanho ideal")
            st.markdown(
                """
Documentos entre **1 e 10 páginas** funcionam melhor.

Para sentenças longas (mais de 40 páginas): envie apenas
os **fundamentos da decisão** (3 a 5 páginas). Isso é suficiente.
            """
            )

        st.markdown("---")
        st.markdown("#### ❌ O que **não** enviar")
        col_n1, col_n2 = st.columns(2)
        with col_n1:
            st.markdown(
                """
- Documentos com CPF, RG ou dados pessoais identificáveis (anonimize antes)
- Artigos genéricos da internet sem aplicação prática
            """
            )
        with col_n2:
            st.markdown(
                """
- Texto puro de lei — a IA já conhece a legislação; envie a **aplicação** dela nos seus casos
- Jurisprudências muito antigas (mais de 5 anos) sem revisão — o entendimento muda
            """
            )

    st.divider()

    # ── Documentos Indexados ──────────────────────────────────────────────────
    st.subheader("📂 Documentos que a IA já aprendeu")
    docs = rag.listar_documentos()
    _TIPO_LABEL = {
        "peticao": "Petição",
        "sentenca": "Sentença",
        "jurisprudencia": "Jurisprudência",
        "tese": "Tese / Argumento",
        "parecer": "Parecer / FAQ",
    }
    if not docs:
        st.info("Nenhum documento enviado ainda. Clique em 'Enviar Documento' acima para começar.")
    else:
        for doc in docs:
            col_doc, col_del = st.columns([5, 1])
            with col_doc:
                tipo_badge = {
                    "peticao": "🔵",
                    "sentenca": "🟢",
                    "jurisprudencia": "🟡",
                    "tese": "🟠",
                    "parecer": "🟣",
                }.get(doc["tipo"], "⚪")
                tipo_nome = _TIPO_LABEL.get(doc["tipo"], doc["tipo"])
                st.markdown(f"{tipo_badge} **{doc['titulo']}** · {tipo_nome}")
            with col_del:
                if st.button("🗑️", key=f"del_{doc['titulo']}", help="Remover documento"):
                    removidos = rag.remover(doc["titulo"])
                    st.info(f"Documento '{doc['titulo']}' removido.")
                    st.rerun()

    st.divider()

    # ── Teste de Busca ────────────────────────────────────────────────────────
    st.subheader("🔍 Testar o Conhecimento da IA")
    st.caption(
        "Digite uma pergunta para ver quais documentos do seu escritório a IA usaria para responder."
    )

    query = st.text_input(
        "Pergunta de teste",
        placeholder="ex: prescrição trabalhista, rescisão indireta, pensão alimentícia...",
    )

    if query and rag.total_chunks > 0:
        chunks = rag.buscar(query, top_k=3)
        if chunks:
            st.success(f"✅ {len(chunks)} documento(s) relevante(s) encontrado(s)")
            for i, c in enumerate(chunks, 1):
                tipo_nome = _TIPO_LABEL.get(c["tipo"], c["tipo"])
                with st.expander(f"Documento {i} — {tipo_nome}: {c['titulo']}"):
                    st.write(c["texto"])
        else:
            st.warning(
                "Nenhum documento relevante encontrado para esta pergunta. Tente outros termos."
            )
    elif query and rag.total_chunks == 0:
        st.warning(
            "Você ainda não enviou nenhum documento. Adicione documentos acima para começar."
        )


# =============================================================================
# SEÇÃO 9 — PÁGINA: Configurações (editar persona + templates após go-live)
# =============================================================================


def page_configuracoes() -> None:
    st.title("⚙️ Configurações do Escritório")
    ob = st.session_state.get("onboarding", {})
    if not ob:
        st.warning("Complete o Onboarding primeiro.")
        return

    tab_persona, tab_templates, tab_status = st.tabs(
        ["🤖 Persona IA", "📝 Templates", "📊 Status do Sistema"]
    )

    with tab_persona:
        st.subheader("Configurar Persona da IA")
        st.caption("Alterações aqui reinicializam os orchestrators existentes.")
        with st.form("form_persona"):
            novo_nome = st.text_input(
                "Nome da IA", value=ob.get("persona_nome", "Assistente Jurídico")
            )
            novo_tom = st.selectbox(
                "Tom de voz",
                ["formal", "amigavel", "neutro"],
                index=["formal", "amigavel", "neutro"].index(ob.get("persona_tom", "formal")),
            )
            novo_ini = st.text_input("Horário Início", value=ob.get("horario_inicio", "08:00"))
            novo_fim = st.text_input("Horário Fim", value=ob.get("horario_fim", "18:00"))
            if st.form_submit_button("Salvar Persona", type="primary"):
                ob.update(
                    {
                        "persona_nome": novo_nome,
                        "persona_tom": novo_tom,
                        "horario_inicio": novo_ini,
                        "horario_fim": novo_fim,
                    }
                )
                # Reinicializa orchestrators para pegar nova persona
                for key in list(st.session_state.keys()):
                    if key.startswith(("orch_", "welcome_")):
                        del st.session_state[key]
                st.success("✅ Persona atualizada. Orchestrators reinicializados.")
                st.rerun()

        st.markdown("**Preview da instrução atual:**")
        st.code(
            gerar_instrucao_persona(
                ob.get("persona_nome", "Assistente"), ob.get("persona_tom", "formal")
            ),
            language="xml",
        )

    with tab_templates:
        st.subheader("Templates de Mensagem WhatsApp")
        with st.form("form_templates_config"):
            t_bv = st.text_area("Boas-Vindas", value=ob.get("template_boas_vindas", ""), height=80)
            t_at = st.text_area("Atualização", value=ob.get("template_atualizacao", ""), height=80)
            t_sn = st.text_area(
                "Sem Novidade", value=ob.get("template_sem_novidade", ""), height=80
            )
            if st.form_submit_button("Salvar Templates", type="primary"):
                ob.update(
                    {
                        "template_boas_vindas": t_bv,
                        "template_atualizacao": t_at,
                        "template_sem_novidade": t_sn,
                    }
                )
                st.success("✅ Templates salvos")

        # Preview com dados reais do cliente
        st.subheader("Preview com dados reais")
        clientes = st.session_state.get("clientes_hub", [])
        if clientes:
            c = clientes[0]
            preview_bv = ob.get("template_boas_vindas", "").replace("{nome_cliente}", c["nome"])
            preview_at = (
                ob.get("template_atualizacao", "")
                .replace("{nome_cliente}", c["nome"])
                .replace(
                    "{resumo_andamento}",
                    "Despacho publicado em 18/03/2026 — aguardando designação de audiência",
                )
            )
            st.markdown(f"**Boas-vindas:** {preview_bv}")
            st.markdown(f"**Atualização:** {preview_at}")

    with tab_status:
        st.subheader("Status do Sistema")
        col1, col2, col3 = st.columns(3)
        col1.metric("Claude", "✅ Online" if ANTHROPIC_API_KEY else "❌ Sem chave")
        col2.metric("DataJud", "✅ Público" if not DATAJUD_API_KEY else "✅ Com API Key")
        col3.metric("WhatsApp", "✅ Simulado" if ob.get("whatsapp_ok") else "⚠️ Não conectado")

        st.subheader("O que os clientes mais perguntam")
        _ROTULOS_STATUS = {
            "saudacao": "Boas-vindas",
            "status_processo": "Consulta de andamento do processo",
            "duvida_termo": "Dúvida sobre termo jurídico",
            "perspectivas": "Perspectivas do caso",
            "parecer_juridico": "Pedido de parecer jurídico",
            "estrategia_processual": "Estratégia processual",
            "negociacao": "Negociação / acordo",
            "decisao_judicial_impacto_alto": "Decisão de alto impacto",
            "prazo": "Consulta de prazo",
            "honorarios": "Honorários",
            "outro": "Atendimento geral",
            "erro": "Resposta automática de fallback",
        }
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
                rotulo = _ROTULOS_STATUS.get(intent, intent)
                st.progress(cnt / max(total_intencoes.values()), text=f"{rotulo} — {cnt}x")
        else:
            st.info("Nenhuma conversa registrada ainda.")


# =============================================================================
# =============================================================================
# SEÇÃO 9B — PÁGINA: CRM Inteligente (Feature 7)
# =============================================================================

_CRM_CORES = {
    "excelente": "#2ecc71",
    "satisfeito": "#27ae60",
    "neutro": "#f39c12",
    "em_risco": "#e67e22",
    "critico": "#e74c3c",
}

_CRM_ICONES = {
    "excelente": "🟢",
    "satisfeito": "🟢",
    "neutro": "🟡",
    "em_risco": "🟠",
    "critico": "🔴",
}


def _calcular_crm_mock(cliente: dict) -> dict:
    """
    Calcula score CRM mockado a partir dos dados do cliente na sessão.
    Usa o CRMScoreCalculator real com um CRMContexto sintético.
    """
    from feature_1_ia_personalizada.services.crm.aggregator import (
        CRMContexto,
        NPSRegistro,
        ProcessoResumo,
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
        [
            ProcessoResumo(
                numero_cnj=cliente["numero_cnj"],
                tipo_acao=cliente.get("tipo_acao"),
                fase_processual=None,
                score_nivel=rng.choice(["baixo", "moderado", "alto"]),
                score_interpretacao=None,
            )
        ]
        if tem_processo
        else []
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


_CRM_NIVEL_LABEL = {
    "excelente": "Excelente",
    "satisfeito": "Satisfeito",
    "neutro": "Neutro",
    "em_risco": "Em Risco",
    "critico": "Crítico",
}


def page_crm() -> None:
    """Relacionamento com Clientes."""
    st.title("🤝 Relacionamento com Clientes")
    st.caption(
        "Veja quais clientes precisam de atenção agora, quais estão satisfeitos "
        "e o que fazer em cada caso — tudo calculado automaticamente pela IA."
    )

    clientes = st.session_state.get("clientes_hub", [])
    if not clientes:
        st.warning("Nenhum cliente carregado. Faça o onboarding primeiro.")
        return

    # ── Controles ─────────────────────────────────────────────────────────────
    col_btn, col_filtro, col_busca = st.columns([2, 2, 3])
    with col_btn:
        analisar = st.button("🔄 Atualizar análise", use_container_width=True)
    with col_filtro:
        filtro_nivel = st.selectbox(
            "Filtrar por situação",
            ["Todos", "critico", "em_risco", "neutro", "satisfeito", "excelente"],
            label_visibility="collapsed",
            format_func=lambda x: "Todos" if x == "Todos" else _CRM_NIVEL_LABEL.get(x, x),
        )
    with col_busca:
        busca = st.text_input(
            "Buscar por nome", placeholder="Digite o nome...", label_visibility="collapsed"
        )

    # Dispara ou carrega análises
    if analisar or "crm_resultados" not in st.session_state:
        with st.spinner("Analisando situação dos clientes..."):
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
            label_nivel = _CRM_NIVEL_LABEL.get(nivel, nivel.replace("_", " ").title())
            st.markdown(
                f'<div style="border-left:4px solid {cor};padding-left:8px">'
                f'<div style="font-size:1.6em;font-weight:bold">{total}</div>'
                f'<div style="color:{cor};font-size:0.85em">{label_nivel}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Tabela de clientes ─────────────────────────────────────────────────────
    clientes_filtrados = [
        c
        for c in clientes
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
                label_nivel_card = _CRM_NIVEL_LABEL.get(nivel, nivel)
                st.metric("Situação", label_nivel_card)
                st.caption(
                    f"⏱ {r['dias_contato']} dias sem contato · 💬 {r['interacoes_30d']} mensagens/mês"
                )

            with col_detalhe:
                with st.expander("Por que esta classificação?"):
                    _FATOR_LABEL = {
                        "engajamento": "Frequência de contato",
                        "satisfacao": "Satisfação (NPS)",
                        "risco_processo": "Risco do processo",
                        "recencia": "Há quanto tempo sem contato",
                        "escalacoes": "Escalações pendentes",
                    }
                    for nome_fator, dados in r["fatores"].items():
                        label_fator = _FATOR_LABEL.get(
                            nome_fator, nome_fator.replace("_", " ").title()
                        )
                        st.progress(
                            min(dados["pontos"] / 100, 1.0),
                            text=label_fator,
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
    total_interacoes = (
        sum(
            max(1, st.session_state.get(f"tokens_{c['id']}", {}).get("in", 0) // 500)
            + rng.randint(4, 18)
            for c in clientes
        )
        if clientes
        else rng.randint(40, 120)
    )

    clientes_ativos = max(1, n - rng.randint(0, max(0, n - 1)))

    # NPS: usa notas reais coletadas na sessão; completa com sintéticas
    nps_reais = [
        st.session_state[f"nps_{c['id']}"] for c in clientes if f"nps_{c['id']}" in st.session_state
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
    pct_autonomia = (
        round(interacoes_sem_humano / total_interacoes * 100, 1) if total_interacoes else 0.0
    )
    horas_eco = round(interacoes_sem_humano * 8 / 60, 1)
    custo_total = round(
        sum(
            (
                st.session_state.get(f"tokens_{c['id']}", {}).get("in", 0) * 3
                + st.session_state.get(f"tokens_{c['id']}", {}).get("out", 0) * 15
            )
            / 1_000_000
            for c in clientes
        )
        or rng.uniform(0.10, 2.50),
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
        tendencia.append(
            {
                "semana": label,
                "total_interacoes": tot,
                "nps_medio": round(rng.uniform(3.0, 5.0), 1),
                "autonomia_pct": round(saidas / tot * 100, 1),
            }
        )

    # ── Ranking de clientes ───────────────────────────────────────────────────
    ranking = []
    for c in clientes:
        nps_cli = st.session_state.get(f"nps_{c['id']}")
        if nps_cli is None:
            nps_cli = rng.choice([None, None, round(rng.uniform(1.0, 5.0), 1)])
        ultimo_contato_dias = rng.randint(1, 60)
        sem_contato_recente = ultimo_contato_dias > 30
        em_risco = sem_contato_recente and nps_cli is not None and nps_cli <= 3
        ranking.append(
            {
                "cliente_id": c["id"],
                "nome": c["nome"],
                "nps_medio": nps_cli,
                "total_interacoes": rng.randint(3, 25),
                "ultimo_contato_dias": ultimo_contato_dias,
                "em_risco": em_risco,
                "sem_avaliacao": nps_cli is None,
            }
        )
    ranking.sort(
        key=lambda r: (
            not r["em_risco"],
            not r["sem_avaliacao"],
            r["nps_medio"] if r["nps_medio"] is not None else 999,
        )
    )

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
            f"</div>"
            f'<span style="font-size:8px;color:#888;">W{semana_label}</span>'
            f"</div>"
        )
    bars += "</div>"
    bars += '<div style="font-size:10px;color:#888;margin-top:4px;">🟢 NPS≥4 · 🟠 NPS≥3 · 🔴 NPS&lt;3 — altura = volume de interações</div>'
    st.markdown(bars, unsafe_allow_html=True)


def page_analytics() -> None:
    """Painel de Resultados."""
    st.title("📊 Painel de Resultados do Escritório")
    st.caption(
        "Veja como seus clientes estão sendo atendidos, quais são os mais satisfeitos "
        "e onde a IA está ajudando a economizar tempo."
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

    tab_dash, tab_nps, tab_export = st.tabs(
        [
            "📈 Painel Geral",
            "⭐ Satisfação dos Clientes",
            "📥 Exportar Relatório",
        ]
    )

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
        st.subheader("⚡ Quanto tempo a IA está economizando")
        ce1, ce2, ce3, ce4 = st.columns(4)
        ce1.metric(
            "Tempo médio de resposta",
            f"{eficiencia['tempo_resposta_medio_ms']} ms",
            help="Tempo que a IA leva para responder um cliente",
        )
        ce2.metric(
            "Atendimentos feitos pela IA",
            eficiencia["interacoes_sem_humano"],
            help="Mensagens respondidas sem precisar do advogado",
        )
        ce3.metric(
            "IA respondeu sozinha",
            f"{eficiencia['percentual_autonomia']:.1f}%",
            help="Porcentagem dos atendimentos resolvidos automaticamente",
        )
        ce4.metric(
            "Horas economizadas",
            f"{eficiencia['horas_economizadas_estimadas']:.1f}h",
            help="Estimativa de horas do advogado poupadas pela IA",
        )

        pct = eficiencia["percentual_autonomia"]
        cor_auto = "#4CAF50" if pct >= 70 else "#FF9800" if pct >= 50 else "#f44336"
        st.markdown(
            f"""<div style="margin:8px 0;">
                <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">
                    <span>Atendimentos resolvidos pela IA sem intervenção do advogado</span>
                    <span style="font-weight:600;color:{cor_auto};">{pct:.1f}%</span>
                </div>
                <div style="background:#e0e0e0;border-radius:4px;height:10px;">
                    <div style="width:{pct}%;background:{cor_auto};height:10px;border-radius:4px;"></div>
                </div>
                <div style="font-size:11px;color:#888;margin-top:3px;">
                    {eficiencia['interacoes_sem_humano']} de {resumo['total_interacoes']} mensagens
                    respondidas sem precisar do advogado
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
                emoji_nps = (
                    "🟢" if t["nps_medio"] >= 4.0 else "🟠" if t["nps_medio"] >= 3.0 else "🔴"
                )
                st.caption(
                    f"**{t['semana']}** — {t['total_interacoes']} interações · "
                    f"NPS {emoji_nps} {t['nps_medio']:.1f} · Autonomia {t['autonomia_pct']:.1f}%"
                )

        st.divider()

        # Ranking de clientes
        st.subheader("👥 Ranking de Clientes")
        st.caption(
            "Em risco (NPS baixo + sem contato recente) aparece primeiro; sem avaliação em segundo."
        )
        for r in ranking:
            cor_card = (
                "#ffebee" if r["em_risco"] else "#fff8e1" if r["sem_avaliacao"] else "#f1f8e9"
            )
            borda = "#ef9a9a" if r["em_risco"] else "#ffe082" if r["sem_avaliacao"] else "#a5d6a7"
            status_icon = (
                "🔴 Em Risco"
                if r["em_risco"]
                else ("⚪ Sem Avaliação" if r["sem_avaliacao"] else "🟢 Ok")
            )
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
            ("baixo", "🟢"),
            ("moderado", "🟡"),
            ("alto", "🔴"),
            ("critico", "🟣"),
        ]
        for col, (nivel, emoji) in zip(st.columns(4), niveis):
            qtd = score_dist.get(nivel, 0)
            col.metric(
                f"{emoji} {nivel.capitalize()}",
                qtd,
                help=f"{qtd / total_score * 100:.0f}% dos processos",
            )

    # =========================================================================
    # Tab 2 — Pesquisa NPS
    # =========================================================================
    with tab_nps:
        st.subheader("⭐ Pesquisa de Satisfação NPS")
        st.markdown(
            """
        Simula o fluxo completo de coleta NPS via WhatsApp (Feature 5):
        1. Advogado dispara pesquisa → `solicitar_nps_cliente` (Celery) envia mensagem
        2. Cliente responde 1–5 → webhook detecta, salva `satisfacao`, remove `aguardando_nps`
        3. Nota ≤ 3 → alerta automático enviado a advogados com `escalacao_ativa=True`
        """
        )
        st.divider()

        if "nps_estados" not in st.session_state:
            st.session_state["nps_estados"] = {}
        nps_estados: dict = st.session_state["nps_estados"]

        col_enviar, col_responder = st.columns(2)

        with col_enviar:
            st.markdown("#### 📤 1. Enviar Pesquisa NPS")
            st.caption(
                "Simula o task Celery com deduplicação Redis (`nps:solicitado:{id}` TTL 30d)."
            )
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
                    st.info(
                        f"⏳ Pesquisa já enviada para **{cliente_sel['nome']}** — aguardando resposta."
                    )
                elif estado.get("nps_registrado") is not None:
                    nota_reg = estado["nps_registrado"]
                    emoji_n = "🟢" if nota_reg >= 4 else "🟡" if nota_reg == 3 else "🔴"
                    st.success(
                        f"✅ NPS registrado: {emoji_n} **{nota_reg}/5** para {cliente_sel['nome']}"
                    )
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
                        st.success(
                            "✅ Pesquisa enviada! Interação salva com `aguardando_nps=True`."
                        )
                        st.caption(
                            f"🔒 Redis key: `nps:solicitado:{cid}` — TTL 30 dias (anti-spam)"
                        )
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
                        format_func=lambda n: f"{n} — "
                        + {
                            1: "Muito insatisfeito 😡",
                            2: "Insatisfeito 😞",
                            3: "Neutro 😐",
                            4: "Satisfeito 😊",
                            5: "Muito satisfeito 🤩",
                        }[n],
                        key="nota_slider",
                    )
                    if st.button("✅ Registrar Resposta", type="primary", key="btn_registrar_nps"):
                        cid_resp = cliente_resp["id"]
                        nps_estados[cid_resp] = {
                            "nps_registrado": nota_input,
                            "aguardando_nps": False,
                        }
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
        st.subheader("📥 Exportar Relatório de Atendimentos")
        st.caption(
            "Baixe um relatório completo de todos os atendimentos do mês. "
            "O arquivo é compatível com Excel."
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
            writer.writerow(
                [
                    "id",
                    "data",
                    "cliente_id",
                    "nome_cliente",
                    "direcao",
                    "mensagem_cliente",
                    "tokens_input",
                    "tokens_output",
                    "custo_estimado_usd",
                    "satisfacao",
                    "autonomia",
                ]
            )
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
                    writer.writerow(
                        [
                            row_id,
                            data_str,
                            c["id"],
                            c["nome"],
                            "recebida" if j % 2 == 0 else "enviada",
                            f"Mensagem demo {j + 1}",
                            ti,
                            to,
                            custo,
                            satisfacao if j == n_rows - 1 else "",
                            "sim" if rng2.random() > 0.3 else "não",
                        ]
                    )
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
            "O relatório inclui todos os atendimentos, notas de satisfação e se a IA respondeu sozinha ou precisou do advogado."
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
    {
        "razao_social": "Metalúrgica São Paulo LTDA",
        "cnpj": "11.222.333/0001-81",
        "porte": "MEDIA",
        "setor": "indústria",
        "situacao": "ATIVA",
        "processos": 8,
    },
    {
        "razao_social": "Comércio e Distribuição Norte S/A",
        "cnpj": "22.333.444/0001-92",
        "porte": "GRANDE",
        "setor": "comércio",
        "situacao": "ATIVA",
        "processos": 15,
    },
    {
        "razao_social": "Tech Solutions LTDA ME",
        "cnpj": "33.444.555/0001-03",
        "porte": "PEQUENA",
        "setor": "tecnologia",
        "situacao": "ATIVA",
        "processos": 3,
    },
    {
        "razao_social": "Transporte e Logística Brasil LTDA",
        "cnpj": "44.555.666/0001-14",
        "porte": "MEDIA",
        "setor": "transporte",
        "situacao": "ATIVA",
        "processos": 12,
    },
    {
        "razao_social": "Construtora ABC S/A",
        "cnpj": "55.666.777/0001-25",
        "porte": "GRANDE",
        "setor": "construção civil",
        "situacao": "ATIVA",
        "processos": 20,
    },
    {
        "razao_social": "Varejo Fashion LTDA",
        "cnpj": "66.777.888/0001-36",
        "porte": "MEDIA",
        "setor": "varejo",
        "situacao": "ATIVA",
        "processos": 6,
    },
    {
        "razao_social": "Hospital e Clínica Central S/A",
        "cnpj": "77.888.999/0001-47",
        "porte": "GRANDE",
        "setor": "saúde",
        "situacao": "ATIVA",
        "processos": 18,
    },
    {
        "razao_social": "Agro Sul Grãos LTDA",
        "cnpj": "88.999.000/0001-58",
        "porte": "MEDIA",
        "setor": "agronegócio",
        "situacao": "ATIVA",
        "processos": 4,
    },
    {
        "razao_social": "Supermercados RegionalMais S/A",
        "cnpj": "99.000.111/0001-69",
        "porte": "GRANDE",
        "setor": "varejo alimentício",
        "situacao": "ATIVA",
        "processos": 25,
    },
    {
        "razao_social": "Indústria de Calçados Norte LTDA",
        "cnpj": "10.111.222/0001-70",
        "porte": "MEDIA",
        "setor": "indústria",
        "situacao": "ATIVA",
        "processos": 7,
    },
]

_PESSOAS_DEMO = [
    {
        "nome": "Carlos Eduardo Martins",
        "polo": "ativo",
        "fase": "Conhecimento",
        "cnj": "0001234-56.2024.5.02.0100",
    },
    {
        "nome": "Ana Beatriz Santos",
        "polo": "ativo",
        "fase": "Conhecimento",
        "cnj": "0002345-67.2024.5.02.0200",
    },
    {
        "nome": "Roberto José Ferreira",
        "polo": "ativo",
        "fase": "Instrução",
        "cnj": "0003456-78.2024.5.02.0300",
    },
    {
        "nome": "Juliana Costa Lima",
        "polo": "ativo",
        "fase": "Conhecimento",
        "cnj": "0004567-89.2024.5.02.0400",
    },
    {
        "nome": "Paulo Henrique Oliveira",
        "polo": "ativo",
        "fase": "Petição Inicial",
        "cnj": "0005678-90.2024.5.02.0500",
    },
    {
        "nome": "Maria Aparecida Souza",
        "polo": "ativo",
        "fase": "Conhecimento",
        "cnj": "0006789-01.2024.5.02.0600",
    },
    {
        "nome": "Fernando Augusto Rocha",
        "polo": "ativo",
        "fase": "Conhecimento",
        "cnj": "0007890-12.2024.5.02.0700",
    },
    {
        "nome": "Sandra Regina Alves",
        "polo": "ativo",
        "fase": "Distribuição",
        "cnj": "0008901-23.2024.5.02.0800",
    },
]

_ESPECIALIDADES_POR_TIPO_ACAO: dict[str, list[str]] = {
    "Reclamação Trabalhista": ["reclamação trabalhista", "horas extras"],
    "Horas Extras": ["horas extras", "reclamação trabalhista"],
    "Rescisão Indireta": ["rescisão indireta", "reclamação trabalhista"],
    "Acidente de Trabalho": ["acidente de trabalho", "indenização por danos morais"],
    "Ação de Cobrança": ["ação de cobrança", "execução de título extrajudicial"],
    "Indenização por Danos Morais": ["indenização por danos morais", "ação consumerista"],
    "Ação de Divórcio": ["ação de divórcio", "guarda e visitação"],
    "Execução de Título Extrajudicial": ["execução de título extrajudicial", "ação de cobrança"],
    "Ação Consumerista": ["ação consumerista", "indenização por danos morais"],
    "Rescisão Contratual": ["rescisão contratual", "ação de cobrança"],
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
    b2b_tipos = {
        "Reclamação Trabalhista",
        "Horas Extras",
        "Rescisão Indireta",
        "Acidente de Trabalho",
        "Rescisão Contratual",
        "Ação de Cobrança",
        "Execução de Título Extrajudicial",
    }
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
            {
                "tipo": especialidades[1] if len(especialidades) > 1 else especialidades[0],
                "contagem": 25,
                "percentual": 25.0,
            },
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
        "novo": ("#1565c0", "#e3f2fd"),
        "contatado": ("#f57c00", "#fff3e0"),
        "qualificado": ("#2e7d32", "#e8f5e9"),
        "descartado": ("#757575", "#f5f5f5"),
    }
    s_cor, s_bg = status_cfg.get(status, ("#555", "#f0f0f0"))
    gerado_ia = lead.get("gerado_por_ia", False)
    ia_badge = (
        '<span style="font-size:10px;background:#7b1fa2;color:white;padding:1px 6px;'
        'border-radius:8px;margin-left:6px;">✨ IA</span>'
        if gerado_ia
        else ""
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
                    if emp["porte"] in ("MEDIA", "GRANDE")
                    else []
                ),
                linkedin_disponivel=False,
                enriquecimento_parcial=False,
            )
            resultado = asyncio.run(svc.calcular_score(dna=dna, inteligencia=intel))
            if resultado.score < score_minimo:
                continue
            leads.append(
                {
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
                }
            )
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
            leads.append(
                {
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
                }
            )

    leads.sort(key=lambda l: -l["score"])
    return leads


def page_prospeccao() -> None:
    """Captação de Novos Clientes."""
    st.title("🔍 Captação de Novos Clientes")
    st.caption(
        "Descubra empresas e pessoas com processos judiciais que combinam com a sua área de atuação. "
        "A IA analisa o perfil de cada candidato e indica quem tem mais chance de virar cliente."
    )

    ob = st.session_state.get("onboarding", {})

    if "leads_prospeccao" not in st.session_state:
        st.session_state["leads_prospeccao"] = []
    if "dna_escritorio" not in st.session_state:
        st.session_state["dna_escritorio"] = _gerar_dna_demo(
            nome_escritorio=ob.get("nome_escritorio", "")
        )
    if "dna_tipo_acao_ref" not in st.session_state:
        st.session_state["dna_tipo_acao_ref"] = None

    dna: DNAEscritorio = st.session_state["dna_escritorio"]
    leads_total = len(st.session_state["leads_prospeccao"])

    tab_dna, tab_descobrir, tab_pipeline = st.tabs(
        [
            "🧬 Perfil do Escritório",
            "🔎 Buscar Candidatos",
            f"📋 Minha Lista  ({leads_total} candidato{'s' if leads_total != 1 else ''})",
        ]
    )

    # ── TAB 1 — DNA do Escritório ──────────────────────────────────────────────
    with tab_dna:
        st.markdown("### Qual é o perfil do seu escritório?")
        st.caption(
            "Com base no tipo de ação que você busca, identificamos as áreas de maior força do seu escritório. "
            "Esse perfil é usado para pontuar quais candidatos têm mais chances de virar clientes."
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Especialidades**")
            for esp in dna.especialidades:
                st.markdown(f"- {esp.title()}")
            st.markdown("**Tipo de lead predominante**")
            tipo_badge = (
                "🏢 Empresa (B2B)" if dna.tipo_lead_predominante == "empresa" else "👤 Pessoa (B2C)"
            )
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
        if st.button(
            "🔄 Regenerar DNA", help="Recalcula o DNA com base no último tipo de ação pesquisado"
        ):
            tipo_ref = st.session_state.get("dna_tipo_acao_ref")
            st.session_state["dna_escritorio"] = _gerar_dna_demo(
                tipo_acao_ref=tipo_ref,
                nome_escritorio=ob.get("nome_escritorio", ""),
            )
            st.success("DNA atualizado.")
            st.rerun()

        with st.expander("ℹ️ De onde vem este perfil?"):
            st.markdown(
                """
O perfil é calculado automaticamente com base nos tipos de ação que você pesquisa aqui.
Em produção, ele é gerado a partir do histórico real dos últimos 90 dias de processos do seu escritório.

A IA analisa:
- Quais tipos de ação você trabalha mais
- Se o seu perfil é mais voltado para empresas ou para pessoas físicas
- Quais setores têm mais a ver com o seu histórico
- Qual é o perfil ideal de cliente para o seu escritório
"""
            )

    # ── TAB 2 — Descobrir Leads ────────────────────────────────────────────────
    with tab_descobrir:
        st.markdown("### Encontrar novos clientes em potencial")
        st.caption(
            "Escolha o tipo de ação. A IA busca empresas e pessoas com processos parecidos nos tribunais, "
            "analisa o perfil de cada uma e indica quem tem mais chance de precisar do seu escritório."
        )

        with st.form("form_descobrir_leads"):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                tipo_acao = st.selectbox("Tipo de ação", _PROSPECCAO_TIPOS_ACAO)
                tipo_lead = st.radio(
                    "Tipo de lead",
                    ["empresa", "pessoa"],
                    horizontal=True,
                    format_func=lambda x: (
                        "🏢 Empresa (B2B)" if x == "empresa" else "👤 Pessoa (B2C)"
                    ),
                )
            with col_f2:
                score_minimo = st.slider("Score mínimo para qualificar", 0, 100, 40)
                limite = st.slider("Candidatos a analisar", 1, 10, 5)

            submitted = st.form_submit_button(
                "🚀 Buscar e Qualificar Leads", use_container_width=True, type="primary"
            )

        if submitted:
            if not ANTHROPIC_API_KEY:
                st.error("❌ Configure ANTHROPIC_API_KEY para usar o motor de IA.")
            else:
                # Atualiza DNA para refletir o tipo_acao buscado
                st.session_state["dna_tipo_acao_ref"] = tipo_acao
                dna = _gerar_dna_demo(
                    tipo_acao_ref=tipo_acao, nome_escritorio=ob.get("nome_escritorio", "")
                )
                st.session_state["dna_escritorio"] = dna

                with st.spinner(f"Buscando e analisando candidatos com a IA... (~{limite * 4}s)"):
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
                            st.success(
                                f"✅ {inseridos} novo(s) candidato(s) adicionado(s) à sua lista"
                            )
                        elif novos:
                            st.info("Todos os candidatos encontrados já estavam na sua lista.")
                        else:
                            st.warning(
                                f"Nenhum candidato atingiu a pontuação mínima de {score_minimo}. "
                                "Reduza o mínimo ou mude o tipo de ação."
                            )

                        if novos:
                            st.divider()
                            st.markdown(f"**{len(novos)} candidato(s) encontrado(s) nesta busca:**")
                            for lead in novos:
                                _render_lead_card_prospeccao(lead)
                                if lead.get("componentes"):
                                    with st.expander(f"Por que esta pontuação? — {lead['nome']}"):
                                        for comp, pts in lead["componentes"].items():
                                            label = comp.replace("_", " ").title()
                                            st.markdown(f"- **{label}:** +{pts} pontos")

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
        with st.expander("ℹ️ Como a pontuação é calculada?"):
            st.markdown(
                """
A IA analisa cada candidato em até 6 critérios e atribui uma pontuação de 0 a 100:

**Para empresas:**
- Área jurídica da empresa bate com a sua especialidade (+30 pts)
- Setor da empresa é compatível com o seu histórico (+20 pts)
- A empresa tem vários processos ativos — alta demanda (+15 pts)
- Contato identificado no LinkedIn (+15 pts)
- Porte da empresa (médio/grande = mais potencial) (+10 pts)
- Empresa regularmente ativa na Receita Federal (+10 pts)

**Para pessoas físicas:**
- Tipo de ação bate com sua especialidade (+35 pts)
- A pessoa está no polo que você costuma atender (+25 pts)
- Processo ainda em fase inicial — oportunidade de entrada (+20 pts)
- Alta recorrência de processos similares (+20 pts)

Candidatos com 75+ são os mais quentes. Entre 40 e 74, valem uma abordagem cuidadosa.
"""
            )

    # ── TAB 3 — Pipeline ───────────────────────────────────────────────────────
    with tab_pipeline:
        leads = st.session_state.get("leads_prospeccao", [])

        if not leads:
            st.info(
                "Nenhum lead no pipeline ainda. Use **Descobrir Leads** para iniciar a prospecção."
            )
            return

        # Filtros
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filtro_tipo = st.selectbox(
                "Tipo de lead",
                ["Todos", "empresa", "pessoa"],
                format_func=lambda x: (
                    "Todos os tipos"
                    if x == "Todos"
                    else ("🏢 Empresa" if x == "empresa" else "👤 Pessoa")
                ),
                key="pipl_tipo",
            )
        with col_f2:
            filtro_status = st.selectbox(
                "Status",
                ["Todos", "novo", "contatado", "qualificado", "descartado"],
                key="pipl_status",
            )
        with col_f3:
            filtro_score = st.slider("Score mínimo", 0, 100, 0, key="pipl_score")

        leads_filtrados = [
            l
            for l in leads
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
                if st.button(
                    "📞 Contatado",
                    key=f"prosp_c_{lead['id']}",
                    use_container_width=True,
                    disabled=s == "contatado",
                ):
                    lead["status"] = "contatado"
                    st.rerun()
            with col_q:
                if st.button(
                    "⭐ Qualificado",
                    key=f"prosp_q_{lead['id']}",
                    use_container_width=True,
                    disabled=s == "qualificado",
                ):
                    lead["status"] = "qualificado"
                    st.rerun()
            with col_d:
                if st.button(
                    "❌ Descartar",
                    key=f"prosp_d_{lead['id']}",
                    use_container_width=True,
                    disabled=s == "descartado",
                ):
                    lead["status"] = "descartado"
                    st.rerun()
            with col_r:
                if st.button(
                    "🔄 Reabrir",
                    key=f"prosp_r_{lead['id']}",
                    use_container_width=True,
                    disabled=s == "novo",
                ):
                    lead["status"] = "novo"
                    st.rerun()
            with col_del:
                if st.button(
                    "🗑️",
                    key=f"prosp_del_{lead['id']}",
                    help="Remover lead",
                    use_container_width=True,
                ):
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


# =============================================================================
# SEÇÃO — Hub do Advogado (integração Harvey / Claude Opus)
# =============================================================================


def _get_hub_client() -> _EscalacaoDemo:
    """Retorna instância singleton do cliente Hub (criada uma vez por sessão)."""
    if "hub_client" not in st.session_state:
        st.session_state["hub_client"] = _EscalacaoDemo()
    return st.session_state["hub_client"]


def _get_hub_sessoes() -> _SessoesEmRam:
    """Retorna o histórico de sessões Hub (criado uma vez por sessão)."""
    if "hub_sessoes" not in st.session_state:
        st.session_state["hub_sessoes"] = _SessoesEmRam()
    return st.session_state["hub_sessoes"]


def _render_hub_metrica(label: str, valor: str, detalhe: str = "") -> None:
    st.markdown(
        f"""<div style="border:1px solid #e0e0e0;border-radius:8px;padding:12px 16px;
                       background:#fafafa;text-align:center;">
            <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.05em;">{label}</div>
            <div style="font-size:22px;font-weight:700;color:#1a1a2e;margin:4px 0;">{valor}</div>
            <div style="font-size:11px;color:#aaa;">{detalhe}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def page_hub_advogado() -> None:
    """
    Hub do Advogado — consulta jurídica com Claude (modelo Haiku para testes).

    Integra as 5 fases do Harvey:
      Fase 1 — EscalationClient (aqui: _EscalacaoDemo com Haiku barato)
      Fase 2 — HubAdvogadoClassificador (classifica intenção do advogado)
      Fase 3 — Consulta livre via WhatsApp / interface web
      Fase 4 — Análise de petições PDF
      Fase 5 — Pesquisa de jurisprudência + histórico de sessões
    """
    ob = st.session_state.get("onboarding", {})
    nome_advogado = ob.get("nome_responsavel") or "Advogado"
    nome_escritorio = ob.get("nome_escritorio") or "Escritório"

    if not ANTHROPIC_API_KEY:
        st.error("🔑 **ANTHROPIC_API_KEY** não configurada. Defina no `.env` e reinicie.")
        return

    hub = _get_hub_client()
    sessoes = _get_hub_sessoes()

    # ── Header ────────────────────────────────────────────────────────────────
    col_tit, col_model = st.columns([3, 1])
    with col_tit:
        st.title("⚖️ Hub do Advogado")
        st.caption(
            f"Dr(a). **{nome_advogado}** · {nome_escritorio} · "
            f"Modelo: `{_MODELO_HUB_DEMO}` *(barato — trocar por `claude-opus-4-6` em prod)*"
        )
    with col_model:
        tin, tout = sessoes.total_tokens
        st.metric("Tokens usados", f"{tin + tout:,}", help=f"In: {tin:,} | Out: {tout:,}")

    st.divider()

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_consulta, tab_peticao, tab_juris, tab_historico = st.tabs(
        [
            "💬 Consulta Jurídica",
            "📄 Analisar Petição",
            "🔍 Jurisprudência",
            "📊 Histórico",
        ]
    )

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 1 — Consulta Jurídica livre
    # ──────────────────────────────────────────────────────────────────────────
    with tab_consulta:
        st.markdown("### 💬 Consulta Jurídica")
        st.caption(
            "Faça qualquer pergunta jurídica. O classificador detecta a intenção automaticamente "
            "e direciona para o handler correto."
        )

        pergunta = st.text_area(
            "Sua pergunta",
            placeholder=(
                "Ex: Qual o prazo para apelar? • Quais os efeitos do CPC art. 485? "
                "• Resumo do cliente João Silva • Status do escritório"
            ),
            height=100,
            key="hub_pergunta",
        )

        col_btn, col_cls = st.columns([1, 2])
        with col_btn:
            enviar = st.button(
                "Consultar →", type="primary", use_container_width=True, key="hub_btn_consulta"
            )
        with col_cls:
            if st.session_state.get("hub_ultima_intencao"):
                intencao_label = {
                    "duvida_juridica": "⚖️ Dúvida jurídica",
                    "resumo_processo": "📋 Resumo de processo",
                    "insight_cliente": "👤 Insight de cliente",
                    "pesquisa_jurisprudencia": "🔍 Jurisprudência",
                    "rascunho_mensagem": "✍️ Rascunho",
                    "status_escritorio": "📊 Status",
                    "analise_peticao": "📄 Petição",
                }.get(
                    st.session_state["hub_ultima_intencao"], st.session_state["hub_ultima_intencao"]
                )
                st.info(f"Intenção detectada: **{intencao_label}**", icon="🤖")

        if enviar and pergunta.strip():
            with st.spinner("Classificando intenção..."):
                classificacao = asyncio.run(
                    _hub_classificador.classificar(pergunta.strip(), tipo_media="texto")
                )

            st.session_state["hub_ultima_intencao"] = classificacao.intencao.value

            system_prompt = SYSTEM_PROMPT_HUB_ADVOGADO_BASE.format(
                nome_usuario=nome_advogado,
                nome_escritorio=nome_escritorio,
                data_hoje=date.today().strftime("%d/%m/%Y"),
            )

            # Handler por intenção
            if classificacao.intencao == IntencaoAdvogado.STATUS_ESCRITORIO:
                clientes = st.session_state.get("clientes_hub", [])
                tin_hist, tout_hist = sessoes.total_tokens
                resposta_txt = (
                    f"**📊 Status do Escritório — {date.today().strftime('%d/%m/%Y')}**\n\n"
                    f"- Clientes cadastrados: **{len(clientes)}**\n"
                    f"- Com processo ativo: **{sum(1 for c in clientes if c.get('numero_cnj'))}**\n"
                    f"- Sessões Hub hoje: **{len(sessoes.todas)}**\n"
                    f"- Tokens consumidos: **{tin_hist + tout_hist:,}** (in: {tin_hist:,} | out: {tout_hist:,})\n"
                    f"- Custo estimado: **${sessoes.custo_total:.4f} USD**\n"
                    f"- Modelo em uso: `{_MODELO_HUB_DEMO}`"
                )
                tokens_in, tokens_out = 0, 0
            else:
                # Enriquecer mensagem com dados disponíveis em sessão
                contexto_extra = ""
                if classificacao.cliente_nome:
                    clientes = st.session_state.get("clientes_hub", [])
                    encontrado = next(
                        (
                            c
                            for c in clientes
                            if classificacao.cliente_nome.lower() in c["nome"].lower()
                        ),
                        None,
                    )
                    if encontrado:
                        contexto_extra = (
                            f"\nCliente encontrado: {encontrado['nome']} "
                            f"(processo: {encontrado.get('numero_cnj') or 'não cadastrado'})"
                        )

                mensagem_final = pergunta.strip() + contexto_extra

                with st.spinner(f"Consultando `{_MODELO_HUB_DEMO}`..."):
                    resultado = asyncio.run(hub.gerar_resposta(system_prompt, mensagem_final))

                resposta_txt = resultado["conteudo"]
                tokens_in = resultado["tokens_input"]
                tokens_out = resultado["tokens_output"]

            # Salvar no histórico
            sessoes.registrar(
                intencao=classificacao.intencao.value,
                mensagem=pergunta.strip(),
                resposta=resposta_txt,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )

            # Exibir resposta
            st.markdown("---")
            st.markdown("#### Resposta")
            st.markdown(resposta_txt)

            if tokens_in or tokens_out:
                st.caption(
                    f"Tokens: {tokens_in} in / {tokens_out} out · Latência: {resultado.get('latencia_ms', 0)} ms"
                )

            st.rerun()

        # Histórico rápido da tab
        if sessoes.todas:
            with st.expander(f"Últimas {min(3, len(sessoes.todas))} consultas"):
                for s in sessoes.todas[:3]:
                    st.markdown(f"**{s['criado_em']}** — `{s['intencao']}`")
                    st.markdown(f"> {s['mensagem_preview']}")
                    st.caption(f"Tokens: {s['tokens_input']} in / {s['tokens_output']} out")
                    st.divider()

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 2 — Análise de Petição PDF
    # ──────────────────────────────────────────────────────────────────────────
    with tab_peticao:
        st.markdown("### 📄 Análise de Petição")
        st.caption(
            "Faça upload de uma petição em PDF ou TXT. O modelo analisa estrutura, "
            "pontos fortes, vulnerabilidades e retorna score de qualidade."
        )

        arquivo = st.file_uploader(
            "Petição (PDF ou TXT, máx. 10 MB)",
            type=["pdf", "txt"],
            key="hub_peticao_upload",
        )

        if arquivo:
            tamanho_mb = len(arquivo.getvalue()) / (1024 * 1024)
            if tamanho_mb > 10:
                st.error(f"Arquivo muito grande ({tamanho_mb:.1f} MB). Limite: 10 MB.")
            else:
                st.success(f"✅ {arquivo.name} ({tamanho_mb:.2f} MB)")

                if st.button("🔍 Analisar Petição", type="primary", key="hub_btn_peticao"):
                    with st.spinner("Extraindo texto do documento..."):
                        texto = _extrair_texto(arquivo.getvalue(), arquivo.name)

                    if len(texto.strip()) < 50:
                        st.error(
                            "Documento vazio ou apenas com imagens (OCR não suportado neste demo)."
                        )
                    else:
                        texto_truncado = len(texto) > 8000
                        st.info(
                            f"📄 {len(texto):,} chars extraídos"
                            + (" · **truncado em 8.000** para o demo" if texto_truncado else "")
                        )

                        with st.spinner(f"Analisando com `{_MODELO_HUB_DEMO}`..."):
                            analise = asyncio.run(hub.analisar_peticao(texto))

                        # Salvar no histórico
                        sessoes.registrar(
                            intencao="analise_peticao",
                            mensagem=f"[PDF] {arquivo.name}",
                            resposta=str(analise),
                            tokens_in=analise.get("tokens_input", 0),
                            tokens_out=analise.get("tokens_output", 0),
                        )

                        # Renderizar resultado
                        score = analise.get("score_geral", 0)
                        cor_score = (
                            "#2e7d32" if score >= 70 else "#f57c00" if score >= 40 else "#c62828"
                        )
                        st.markdown(
                            f"""<div style="border:1.5px solid {cor_score};border-radius:10px;
                                           padding:14px 18px;background:{cor_score}18;margin-bottom:12px;">
                                <span style="font-size:13px;font-weight:600;color:{cor_score};">
                                    SCORE DE QUALIDADE
                                </span>
                                <span style="font-size:28px;font-weight:700;color:{cor_score};float:right;">
                                    {score}/100
                                </span>
                                <div style="background:#e0e0e0;border-radius:4px;height:7px;margin-top:10px;">
                                    <div style="width:{score}%;background:{cor_score};height:7px;border-radius:4px;"></div>
                                </div>
                            </div>""",
                            unsafe_allow_html=True,
                        )

                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.markdown(f"**Tipo:** {analise.get('tipo_peca', '—')}")
                            st.markdown("**✅ Pontos Fortes**")
                            for p in analise.get("pontos_fortes", []):
                                st.markdown(f"- {p}")
                            st.markdown("**📌 Sugestões**")
                            for s in analise.get("sugestoes", []):
                                st.markdown(f"- {s}")
                        with col_b:
                            st.markdown("**⚠️ Vulnerabilidades**")
                            for v in analise.get("vulnerabilidades", []):
                                st.markdown(f"- {v}")
                            st.markdown("**➕ Argumentos Ausentes**")
                            for a in analise.get("argumentos_ausentes", []):
                                st.markdown(f"- {a}")
                            st.markdown("**⚖️ Precedentes Relevantes**")
                            for pr in analise.get("precedentes_relevantes", []):
                                st.markdown(f"- {pr}")

                        st.caption(
                            f"Tokens: {analise.get('tokens_input', 0)} in / "
                            f"{analise.get('tokens_output', 0)} out · "
                            f"Latência: {analise.get('latencia_ms', 0)} ms"
                        )

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 3 — Pesquisa de Jurisprudência
    # ──────────────────────────────────────────────────────────────────────────
    with tab_juris:
        st.markdown("### 🔍 Pesquisa de Jurisprudência")
        st.caption(
            "O modelo sintetiza jurisprudência sobre o tema informado com base no seu "
            "treinamento até agosto/2025. Para julgados mais recentes, consulte o DataJud."
        )

        col_q, col_t = st.columns([2, 1])
        with col_q:
            query_juris = st.text_input(
                "Tema ou tese jurídica",
                placeholder="Ex: dano moral em relação de consumo • prescrição trabalhista • CPC art. 485",
                key="hub_juris_query",
            )
        with col_t:
            tribunais_sel = st.multiselect(
                "Tribunais",
                ["STJ", "STF", "TST", "TRF", "TJs Estaduais"],
                default=["STJ", "STF"],
                key="hub_juris_tribunais",
            )

        if st.button("🔍 Pesquisar", type="primary", key="hub_btn_juris") and query_juris.strip():
            tribunais_str = ", ".join(tribunais_sel) if tribunais_sel else "STJ, STF"
            with st.spinner(f"Pesquisando com `{_MODELO_HUB_DEMO}`..."):
                resultado = asyncio.run(
                    hub.pesquisar_jurisprudencia(query_juris.strip(), tribunais_str)
                )

            sessoes.registrar(
                intencao="pesquisa_jurisprudencia",
                mensagem=query_juris.strip(),
                resposta=resultado["conteudo"],
                tokens_in=resultado["tokens_input"],
                tokens_out=resultado["tokens_output"],
            )

            st.markdown("---")
            st.markdown(resultado["conteudo"])
            st.caption(
                f"Tokens: {resultado['tokens_input']} in / {resultado['tokens_output']} out · "
                f"Latência: {resultado.get('latencia_ms', 0)} ms"
            )

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 4 — Histórico de Sessões
    # ──────────────────────────────────────────────────────────────────────────
    with tab_historico:
        st.markdown("### 📊 Histórico de Sessões Hub")

        todas = sessoes.todas
        if not todas:
            st.info("Nenhuma consulta realizada ainda. Use as abas acima para começar.")
            return

        # Métricas resumidas
        tin_tot, tout_tot = sessoes.total_tokens
        contagem = sessoes.contagem_por_intencao()
        top_intencao = max(contagem, key=contagem.get) if contagem else "—"

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _render_hub_metrica("Consultas", str(len(todas)), "total na sessão")
        with col2:
            _render_hub_metrica(
                "Tokens", f"{tin_tot + tout_tot:,}", f"in: {tin_tot:,} · out: {tout_tot:,}"
            )
        with col3:
            _render_hub_metrica(
                "Custo estimado", f"${sessoes.custo_total:.4f}", "USD · modelo Haiku"
            )
        with col4:
            _render_hub_metrica("Mais usado", top_intencao, f"{contagem.get(top_intencao, 0)}x")

        st.divider()

        # Lista de sessões
        rotulos = {
            "duvida_juridica": "⚖️ Dúvida jurídica",
            "resumo_processo": "📋 Resumo processo",
            "insight_cliente": "👤 Insight cliente",
            "pesquisa_jurisprudencia": "🔍 Jurisprudência",
            "rascunho_mensagem": "✍️ Rascunho",
            "status_escritorio": "📊 Status",
            "analise_peticao": "📄 Petição",
        }

        for sessao in todas:
            label = rotulos.get(sessao["intencao"], sessao["intencao"])
            with st.expander(
                f"{label} · {sessao['criado_em']} · {sessao['tokens_input'] + sessao['tokens_output']} tokens",
                expanded=False,
            ):
                st.markdown(f"**Pergunta:** {sessao['mensagem_completa']}")
                st.markdown("**Resposta:**")
                st.markdown(sessao["resposta"])
                st.caption(
                    f"Tokens: {sessao['tokens_input']} in / {sessao['tokens_output']} out · "
                    f"Custo: ${sessao['custo_usd']:.6f} USD"
                )


def _render_sidebar() -> None:
    ob = st.session_state.get("onboarding", {})
    onboarding_ok = ob.get("onboarding_completo", False)
    clientes = st.session_state.get("clientes_hub", [])

    with st.sidebar:
        st.title("⚖️ Assistente Jurídico")
        st.caption("IA para o seu escritório de advocacia")
        st.divider()

        # Navegação
        paginas_disponiveis = ["🚀 Configuração Inicial"]
        if onboarding_ok or clientes:
            paginas_disponiveis += [
                "👥 Meus Clientes",
                "⚖️ Hub do Advogado",
                "🤝 Relacionamento",
                "📚 Documentos do Escritório",
                "🔍 Captar Novos Clientes",
                "📊 Painel de Resultados",
                "⚙️ Configurações",
            ]
        elif ANTHROPIC_API_KEY:
            # Hub disponível mesmo sem onboarding completo (só precisa da API key)
            paginas_disponiveis.append("⚖️ Hub do Advogado")

        pagina_selecionada = st.radio(
            "Navegação", paginas_disponiveis, label_visibility="collapsed"
        )
        mapa = {
            "🚀 Configuração Inicial": "onboarding",
            "👥 Meus Clientes": "hub",
            "⚖️ Hub do Advogado": "hub_advogado",
            "🤝 Relacionamento": "crm",
            "📚 Documentos do Escritório": "rag",
            "🔍 Captar Novos Clientes": "prospeccao",
            "📊 Painel de Resultados": "analytics",
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
            arquivo_extra = st.file_uploader(
                "CSV adicional", type=["csv"], key="csv_extra", label_visibility="collapsed"
            )
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
            st.success("Claude ativo", icon="✅")
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

        # Status Hub do Advogado
        hub_sessoes: _SessoesEmRam | None = st.session_state.get("hub_sessoes")
        if hub_sessoes and hub_sessoes.todas:
            tin, tout = hub_sessoes.total_tokens
            st.success(
                f"Hub: {len(hub_sessoes.todas)} sessão(ões) · {tin + tout:,} tokens",
                icon="⚖️",
            )
        else:
            st.info(f"Hub: modelo `{_MODELO_HUB_DEMO}`", icon="⚖️")

        st.divider()
        st.caption(
            "**Stack:**\n"
            "LangGraph · Claude Haiku/Opus · DataJud API\n"
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
    elif pagina == "hub_advogado":
        page_hub_advogado()
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
