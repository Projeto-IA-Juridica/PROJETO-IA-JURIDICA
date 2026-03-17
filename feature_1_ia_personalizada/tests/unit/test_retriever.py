# feature_1_ia_personalizada/tests/unit/test_retriever.py
"""
Testes unitários do RAGRetriever e funções auxiliares.

Cobre:
  - Retorna string vazia quando nenhum candidato passa o threshold
  - MMR seleciona chunks relevantes E diversos (não duplicados)
  - Fallback sem filtro quando filtro retorna poucos resultados
  - Formatação do contexto em XML bem estruturado
  - _tokenizar e _jaccard funcionam corretamente
  - _mmr com k >= len(candidatos) retorna todos sem erro
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from feature_1_ia_personalizada.services.rag.retriever import (
    RAGRetriever,
    _formatar_contexto,
    _jaccard,
    _mmr,
    _tokenizar,
)
from feature_1_ia_personalizada.services.rag.vector_store import ResultadoBusca

# ---------------------------------------------------------------------------
# Fábrica de ResultadoBusca para testes
# ---------------------------------------------------------------------------


def _resultado(
    id: int,
    conteudo: str,
    distancia: float = 0.10,
    titulo: str = "Doc Teste",
    tipo: str = "sentenca",
) -> ResultadoBusca:
    return ResultadoBusca(
        id=id,
        escritorio_id=1,
        titulo=titulo,
        tipo=tipo,
        conteudo=conteudo,
        distancia=distancia,
        metadata_json={},
        doc_hash=f"hash{id}",
        chunk_index=0,
    )


def _make_store_mock(retornos: list[ResultadoBusca]) -> AsyncMock:
    mock = AsyncMock()
    mock.buscar_por_texto = AsyncMock(return_value=retornos)
    return mock


# ---------------------------------------------------------------------------
# Testes — threshold de relevância
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retorna_vazio_quando_sem_resultado_relevante():
    """Quando todos os candidatos têm distância > 0.25, retorna string vazia."""
    candidatos = [
        _resultado(1, "texto irrelevante A", distancia=0.30),
        _resultado(2, "texto irrelevante B", distancia=0.40),
        _resultado(3, "texto irrelevante C", distancia=0.50),
    ]
    store = _make_store_mock(candidatos)
    retriever = RAGRetriever(vector_store=store)

    resultado = await retriever.buscar(query="prazo recursal", escritorio_id=1)

    assert resultado == ""


@pytest.mark.asyncio
async def test_retorna_contexto_quando_ha_resultado_relevante():
    """Candidatos com distância ≤ 0.25 devem gerar bloco de contexto."""
    candidatos = [
        _resultado(1, "Sentença condenando ao pagamento de danos morais.", distancia=0.10),
        _resultado(2, "Recurso desprovido. Mantida a sentença.", distancia=0.15),
        _resultado(3, "Prazo de 15 dias para interposição de recurso.", distancia=0.20),
    ]
    store = _make_store_mock(candidatos)
    retriever = RAGRetriever(vector_store=store)

    resultado = await retriever.buscar(query="recurso de apelação", escritorio_id=1)

    assert "<contexto_juridico_escritorio>" in resultado
    assert "</contexto_juridico_escritorio>" in resultado
    assert resultado != ""


@pytest.mark.asyncio
async def test_threshold_exato_incluido():
    """Candidato com distância exatamente igual a _MAX_DISTANCIA (0.25) deve ser incluído."""
    candidatos = [
        _resultado(1, "Tese jurídica sobre prescrição.", distancia=0.25),
    ]
    store = _make_store_mock(candidatos)
    retriever = RAGRetriever(vector_store=store)

    resultado = await retriever.buscar(query="prazo prescricional", escritorio_id=1)

    assert resultado != ""


# ---------------------------------------------------------------------------
# Testes — MMR (diversidade)
# ---------------------------------------------------------------------------


def test_mmr_seleciona_k_itens():
    """_mmr deve retornar exatamente k itens quando candidatos > k."""
    candidatos = [
        _resultado(i, f"Texto jurídico diferente sobre tema {i}", distancia=0.1 * i)
        for i in range(1, 8)
    ]
    resultado = _mmr(candidatos, k=3)
    assert len(resultado) == 3


def test_mmr_sem_duplicidade():
    """_mmr não deve retornar o mesmo candidato duas vezes."""
    candidatos = [
        _resultado(i, f"Conteúdo texto jurídico item {i}", distancia=0.05 * i) for i in range(1, 6)
    ]
    resultado = _mmr(candidatos, k=3)
    ids = [r.id for r in resultado]
    assert len(ids) == len(set(ids))


def test_mmr_k_maior_que_candidatos_retorna_todos():
    """Se k >= len(candidatos), retorna todos sem erro."""
    candidatos = [
        _resultado(1, "Único chunk disponível", distancia=0.10),
    ]
    resultado = _mmr(candidatos, k=5)
    assert len(resultado) == 1


def test_mmr_prefere_diversidade():
    """
    Dado um chunk muito similar ao primeiro selecionado, MMR deve preferir
    um chunk mais diferente no segundo slot.
    """
    # Chunk 1 e 2 têm conteúdo quase idêntico
    texto_base = "responsabilidade civil dano moral indenização contrato"
    chunk_similar = _resultado(1, texto_base, distancia=0.15)
    chunk_duplicado = _resultado(2, texto_base + " réu autor", distancia=0.16)
    # Chunk 3 é diferente (fala de outro tema)
    chunk_diferente = _resultado(
        3, "prazo recursal apelação contrarrazões tribunal", distancia=0.17
    )

    resultado = _mmr([chunk_similar, chunk_duplicado, chunk_diferente], k=2)

    # O primeiro deve ser o mais relevante (distância menor)
    assert resultado[0].id == 1
    # O segundo deve ser o diferente, não o quase-duplicado
    assert resultado[1].id == 3


# ---------------------------------------------------------------------------
# Testes — fallback sem filtro
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_sem_filtro_quando_poucos_candidatos():
    """
    Se busca com filtro retorna menos de RAG_TOP_K_FINAL resultados,
    deve fazer busca sem filtro para complementar.
    """
    candidato_filtrado = _resultado(1, "Sentença por dano moral.", distancia=0.10)
    candidato_sem_filtro = _resultado(2, "Recurso desprovido.", distancia=0.12)

    store = AsyncMock()
    # Primeira chamada (com filtro): retorna apenas 1 item
    # Segunda chamada (sem filtro): retorna 2 itens
    store.buscar_por_texto = AsyncMock(
        side_effect=[
            [candidato_filtrado],
            [candidato_filtrado, candidato_sem_filtro],
        ]
    )

    retriever = RAGRetriever(vector_store=store)
    resultado = await retriever.buscar(
        query="dano moral",
        escritorio_id=1,
        contexto_processo={"tipo_acao": "Ação de Indenização"},
    )

    # Deve ter feito 2 chamadas ao store
    assert store.buscar_por_texto.call_count == 2
    # O contexto deve incluir ambos os documentos
    assert resultado != ""


@pytest.mark.asyncio
async def test_sem_contexto_processo_nao_usa_filtro():
    """Sem contexto_processo, deve fazer apenas 1 busca sem filtros."""
    store = _make_store_mock([_resultado(1, "Conteúdo jurídico relevante.", distancia=0.10)])
    retriever = RAGRetriever(vector_store=store)

    await retriever.buscar(query="prazo recursal", escritorio_id=1, contexto_processo=None)

    store.buscar_por_texto.assert_called_once()
    # Verifica que foi chamado sem filtros
    call_kwargs = store.buscar_por_texto.call_args.kwargs
    assert call_kwargs.get("filtros") is None


# ---------------------------------------------------------------------------
# Testes — formatação
# ---------------------------------------------------------------------------


def test_formatar_contexto_estrutura_xml():
    """_formatar_contexto deve gerar XML com abertura, conteúdo e fechamento corretos."""
    chunks = [
        _resultado(1, "Texto da sentença aqui.", titulo="Sentença TJSP", tipo="sentenca"),
        _resultado(2, "Texto da petição aqui.", titulo="Petição Inicial", tipo="peticao"),
    ]
    contexto = _formatar_contexto(chunks)

    assert contexto.startswith("<contexto_juridico_escritorio>")
    assert contexto.endswith("</contexto_juridico_escritorio>")
    assert "[1] Sentenca — Sentença TJSP" in contexto
    assert "[2] Peticao — Petição Inicial" in contexto
    assert "Texto da sentença aqui." in contexto
    assert "Texto da petição aqui." in contexto


def test_formatar_contexto_lista_vazia():
    """_formatar_contexto com lista vazia deve gerar XML vazio mas válido."""
    contexto = _formatar_contexto([])
    assert "<contexto_juridico_escritorio>" in contexto
    assert "</contexto_juridico_escritorio>" in contexto


# ---------------------------------------------------------------------------
# Testes — funções auxiliares (_tokenizar, _jaccard)
# ---------------------------------------------------------------------------


def test_tokenizar_filtra_palavras_curtas():
    """_tokenizar deve ignorar palavras com menos de 3 caracteres."""
    tokens = _tokenizar("a de ou em petição recurso")
    assert "a" not in tokens
    assert "de" not in tokens
    assert "ou" not in tokens
    assert "em" not in tokens
    assert "petição" in tokens
    assert "recurso" in tokens


def test_tokenizar_case_insensitive():
    """_tokenizar deve normalizar para minúsculas."""
    tokens = _tokenizar("SENTENÇA Recurso APELAÇÃO")
    assert "sentença" in tokens
    assert "recurso" in tokens
    assert "apelação" in tokens


def test_jaccard_conjuntos_identicos():
    """Jaccard de dois conjuntos iguais deve ser 1.0."""
    a = frozenset(["recurso", "apelação", "sentença"])
    assert _jaccard(a, a) == 1.0


def test_jaccard_conjuntos_disjuntos():
    """Jaccard de conjuntos sem interseção deve ser 0.0."""
    a = frozenset(["recurso", "apelação"])
    b = frozenset(["contrato", "locação"])
    assert _jaccard(a, b) == 0.0


def test_jaccard_conjuntos_vazios():
    """Dois conjuntos vazios devem retornar 1.0 (convenção)."""
    assert _jaccard(frozenset(), frozenset()) == 1.0


def test_jaccard_parcial():
    """Jaccard parcial deve estar entre 0 e 1."""
    a = frozenset(["recurso", "apelação", "tribunal"])
    b = frozenset(["tribunal", "sentença", "juiz"])
    j = _jaccard(a, b)
    assert 0.0 < j < 1.0
    # interseção = {"tribunal"} (1); união = 5 → 1/5 = 0.2
    assert abs(j - 1 / 5) < 1e-9
