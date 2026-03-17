# feature_1_ia_personalizada/services/rag/ingestion.py
"""
DocumentoIngester — pipeline de ingestão de documentos jurídicos no RAG.

Fluxo para PDF:
  1. Extração de texto via PyMuPDF (fitz)
  2. Limpeza: remove cabeçalhos, rodapés, numeração de página, artefatos
  3. Deduplicação: SHA256 do texto original — aborta se já ingerido
  4. Chunking: 512 tokens / 50 de overlap (RecursiveCharacterTextSplitter)
  5. Extração de metadados: regex primeiro; Claude apenas para campos não encontrados
  6. Embeddings em batch via EmbeddingGenerator (uma chamada de API)
  7. Inserção em transação única no banco (documentos_rag)

Para texto simples (ingerir_texto): mesmo fluxo sem etapa 1.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

import structlog
from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from feature_1_ia_personalizada.services.rag.embeddings import EmbeddingGenerator
from shared.config.settings import settings
from shared.models.documento_rag import TIPOS_VALIDOS, DocumentoRag

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes de chunking
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 512  # tokens por chunk
_CHUNK_OVERLAP = 50  # tokens de sobreposição entre chunks consecutivos

# Expressões regulares para extração de metadados jurídicos
_RE_CNJ = re.compile(r"\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b")
_RE_TRIBUNAL = re.compile(
    r"\b(STF|STJ|TST|TSE|STM|TRF\d|TJ[A-Z]{2,3}|TRT\d{1,2}|TRE-[A-Z]{2})\b",
    re.IGNORECASE,
)
_RE_DATA = re.compile(r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{1,2}\s+de\s+\w+\s+de\s+\d{4})\b")

# Padrões de limpeza de texto extraído por OCR / digital
_RE_PAGINA = re.compile(r"^\s*[Pp][áa]g(?:ina)?\.?\s*\d+\s*$", re.MULTILINE)
_RE_RODAPE = re.compile(r"_{5,}.*?_{5,}", re.DOTALL)
_RE_LINHA_VAZIA_EXCESSIVA = re.compile(r"\n{3,}")


# ---------------------------------------------------------------------------
# Resultado da ingestão
# ---------------------------------------------------------------------------


@dataclass
class IngestaoResultado:
    doc_hash: str
    titulo: str
    tipo: str
    escritorio_id: int
    chunks_gerados: int
    metadata_extraida: dict[str, Any]
    duplicata: bool = False
    erro: str | None = None

    @property
    def sucesso(self) -> bool:
        return self.erro is None and not self.duplicata


# ---------------------------------------------------------------------------
# DocumentoIngester
# ---------------------------------------------------------------------------


class DocumentoIngester:
    """
    Realiza a ingestão de documentos jurídicos no banco vetorial.

    Instanciar uma vez e reutilizar (compartilha EmbeddingGenerator).
    """

    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._embeddings = embedding_generator
        self._session_factory = session_factory
        self._anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    # -----------------------------------------------------------------------
    # API pública
    # -----------------------------------------------------------------------

    async def ingerir_pdf(
        self,
        arquivo_bytes: bytes,
        escritorio_id: int,
        titulo: str,
        tipo: str,
        metadata: dict[str, Any] | None = None,
    ) -> IngestaoResultado:
        """
        Ingere um PDF completo.

        Args:
            arquivo_bytes: conteúdo binário do arquivo PDF.
            escritorio_id: tenant.
            titulo: nome do documento (ex: "Sentença - Vara Cível SP 001").
            tipo: peticao | sentenca | jurisprudencia | tese | parecer
            metadata: dict opcional com campos conhecidos (tribunal, vara, etc.)
        """
        try:
            texto = _extrair_texto_pdf(arquivo_bytes)
        except Exception as exc:
            logger.error("ingestao_pdf_extracao_falhou", erro=str(exc))
            return IngestaoResultado(
                doc_hash="",
                titulo=titulo,
                tipo=tipo,
                escritorio_id=escritorio_id,
                chunks_gerados=0,
                metadata_extraida={},
                erro=f"Falha na extração do PDF: {exc}",
            )

        return await self.ingerir_texto(
            texto=texto,
            escritorio_id=escritorio_id,
            titulo=titulo,
            tipo=tipo,
            metadata=metadata,
        )

    async def ingerir_texto(
        self,
        texto: str,
        escritorio_id: int,
        titulo: str,
        tipo: str,
        metadata: dict[str, Any] | None = None,
    ) -> IngestaoResultado:
        """
        Ingere texto puro (já extraído).

        Mesmo fluxo do ingerir_pdf, sem etapa de extração PyMuPDF.
        """
        if tipo not in TIPOS_VALIDOS:
            return IngestaoResultado(
                doc_hash="",
                titulo=titulo,
                tipo=tipo,
                escritorio_id=escritorio_id,
                chunks_gerados=0,
                metadata_extraida={},
                erro=f"Tipo inválido '{tipo}'. Use: {', '.join(sorted(TIPOS_VALIDOS))}",
            )

        log = logger.bind(escritorio_id=escritorio_id, titulo=titulo, tipo=tipo)

        # 1. Limpa texto
        texto_limpo = _limpar_texto(texto)

        # 2. Hash para deduplicação — calculado do texto LIMPO, não do original.
        # Motivo: o mesmo PDF pode gerar textos com pequenas diferenças de OCR
        # (espaços extras, numeração de página), mas após _limpar_texto o conteúdo
        # semântico é idêntico e o hash vai bater corretamente.
        doc_hash = hashlib.sha256(texto_limpo.encode()).hexdigest()

        # 3. Verifica duplicata
        if await self._ja_ingerido(doc_hash, escritorio_id):
            log.info("ingestao_duplicata_ignorada", doc_hash=doc_hash[:16])
            return IngestaoResultado(
                doc_hash=doc_hash,
                titulo=titulo,
                tipo=tipo,
                escritorio_id=escritorio_id,
                chunks_gerados=0,
                metadata_extraida=metadata or {},
                duplicata=True,
            )

        # 4. Extrai metadados (regex + Claude para campos ausentes)
        metadata_final = await self._extrair_metadata(texto_limpo, metadata or {})
        metadata_final.setdefault("titulo", titulo)
        metadata_final.setdefault("tipo", tipo)

        # 5. Chunking
        chunks = _chunkar(texto_limpo)
        if not chunks:
            return IngestaoResultado(
                doc_hash=doc_hash,
                titulo=titulo,
                tipo=tipo,
                escritorio_id=escritorio_id,
                chunks_gerados=0,
                metadata_extraida=metadata_final,
                erro="Documento vazio após limpeza.",
            )

        log.info("ingestao_chunks_gerados", n_chunks=len(chunks))

        # 6. Embeddings em batch (uma chamada de API para todos os chunks)
        embeddings = await self._embeddings.gerar_batch(chunks)

        # 7. Insere todos os chunks em transação única
        await self._salvar_chunks(
            escritorio_id=escritorio_id,
            titulo=titulo,
            tipo=tipo,
            doc_hash=doc_hash,
            chunks=chunks,
            embeddings=embeddings,
            metadata=metadata_final,
        )

        log.info("ingestao_concluida", n_chunks=len(chunks))
        return IngestaoResultado(
            doc_hash=doc_hash,
            titulo=titulo,
            tipo=tipo,
            escritorio_id=escritorio_id,
            chunks_gerados=len(chunks),
            metadata_extraida=metadata_final,
        )

    # -----------------------------------------------------------------------
    # Internos
    # -----------------------------------------------------------------------

    async def _ja_ingerido(self, doc_hash: str, escritorio_id: int) -> bool:
        """Verifica se o doc_hash já existe para este escritório."""
        async with self._session_factory() as session:
            stmt = (
                select(DocumentoRag.id)
                .where(
                    DocumentoRag.doc_hash == doc_hash,
                    DocumentoRag.escritorio_id == escritorio_id,
                    DocumentoRag.ativo.is_(True),
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar() is not None

    async def _extrair_metadata(
        self, texto: str, metadata_existente: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Extrai metadados jurídicos do texto.
        Regex primeiro; Claude apenas para campos não encontrados.
        """
        meta = dict(metadata_existente)

        # Regex — rápido e sem custo de token
        if "numero_cnj" not in meta:
            match = _RE_CNJ.search(texto)
            if match:
                meta["numero_cnj"] = match.group(1)

        if "tribunal" not in meta:
            match = _RE_TRIBUNAL.search(texto)
            if match:
                meta["tribunal"] = match.group(1).upper()

        if "data_doc" not in meta:
            match = _RE_DATA.search(texto)
            if match:
                meta["data_doc"] = match.group(1)

        # Claude — somente se ainda faltam campos importantes
        campos_faltando = [c for c in ("numero_cnj", "tribunal", "tipo_acao") if c not in meta]
        if campos_faltando:
            trecho = texto[:2000]  # primeiras 2000 chars são suficientes para metadados
            meta.update(await self._extrair_metadata_claude(trecho, campos_faltando))

        return meta

    async def _extrair_metadata_claude(self, trecho: str, campos: list[str]) -> dict[str, Any]:
        """Extrai campos específicos via Claude Haiku (barato e rápido)."""
        campos_str = ", ".join(campos)
        prompt = (
            f"Extraia do trecho jurídico abaixo os seguintes campos: {campos_str}.\n"
            "Responda SOMENTE com JSON válido. Se não encontrar um campo, use null.\n"
            f"Trecho:\n{trecho}"
        )
        try:
            resp = await self._anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            import json

            raw = resp.content[0].text

            # Extrai o objeto JSON usando regex — robusto contra filler conversacional
            # e markdown (ex: "Aqui está o JSON: {...}").
            match = re.search(r"\{.*?\}", raw, re.DOTALL)
            if not match:
                logger.warning("ingestao_metadata_claude_sem_json", raw=raw[:200])
                return {}

            parsed: dict[str, Any] = json.loads(match.group())
            # Filtra apenas campos pedidos e não-nulos
            return {k: v for k, v in parsed.items() if k in campos and v is not None}
        except Exception as exc:
            logger.warning("ingestao_metadata_claude_falhou", erro=str(exc))
            return {}

    async def _salvar_chunks(
        self,
        escritorio_id: int,
        titulo: str,
        tipo: str,
        doc_hash: str,
        chunks: list[str],
        embeddings: list[list[float]],
        metadata: dict[str, Any],
    ) -> None:
        """Insere todos os chunks em uma única transação."""
        async with self._session_factory() as session:
            objetos = [
                DocumentoRag(
                    escritorio_id=escritorio_id,
                    titulo=titulo,
                    tipo=tipo,
                    conteudo=chunk,
                    embedding=embedding,
                    metadata_json=metadata,
                    chunk_index=i,
                    doc_hash=doc_hash,
                    ativo=True,
                )
                for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False))
            ]
            session.add_all(objetos)
            await session.commit()


# ---------------------------------------------------------------------------
# Funções utilitárias puras
# ---------------------------------------------------------------------------


def _extrair_texto_pdf(arquivo_bytes: bytes) -> str:
    """Extrai texto de um PDF em bytes via PyMuPDF."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=arquivo_bytes, filetype="pdf")
    paginas: list[str] = []
    for pagina in doc:
        paginas.append(pagina.get_text("text"))
    doc.close()
    return "\n".join(paginas)


def _limpar_texto(texto: str) -> str:
    """Remove artefatos comuns de PDFs jurídicos digitalizados."""
    texto = _RE_PAGINA.sub("", texto)
    texto = _RE_RODAPE.sub("", texto)
    texto = _RE_LINHA_VAZIA_EXCESSIVA.sub("\n\n", texto)
    return texto.strip()


def _chunkar(texto: str) -> list[str]:
    """
    Divide o texto em chunks de 512 tokens com 50 de overlap.
    Usa RecursiveCharacterTextSplitter do LangChain (incluso via langchain==0.2.16).
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",  # tokenizador compatível com OpenAI e Voyage
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP,
    )
    return splitter.split_text(texto)
