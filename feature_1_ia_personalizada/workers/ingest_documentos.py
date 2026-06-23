# feature_1_ia_personalizada/workers/ingest_documentos.py
"""
Tasks Celery de ingestão de documentos jurídicos no RAG.

Tasks:
  ingest_documento              — ingere um arquivo PDF/DOCX/TXT em background
  ingest_jurisprudencia_publica — pré-popula base RAG com jurisprudência do DataJud

Fila: "ia" (definida em celery_app.py)
Base: DLQTask — em caso de falha após retries, encaminha para dead_letter.

Transferência de arquivo:
  O arquivo é armazenado pelo endpoint de upload no Redis (chave f1:rag:file:{job_id},
  TTL 30 min) e lido pelo worker a partir daí — sem dependência de /tmp compartilhado
  entre containers (web e worker rodam em containers separados no Railway).

  O worker deleta a chave Redis imediatamente após a leitura (antes do processamento
  assíncrono). Em caso de retry, a chave já não existe; o handler detecta isso via
  self.request.retries > 0 e encerra sem nova tentativa.

Async em Celery:
  DocumentoIngester usa AsyncSession — executado via asyncio.run() dentro
  da task síncrona do Celery. Padrão recomendado para Celery 5.x sem
  necessidade de celery[asyncio].
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import redis as _redis_sync
import structlog

from feature_1_ia_personalizada.workers.celery_app import DLQTask, celery_app
from shared.config.settings import settings
from shared.database.connection import async_session_factory

logger = structlog.get_logger(__name__)

# Cliente Redis síncrono — leitura de bytes do arquivo e atualização de status
_redis_sync_client = _redis_sync.from_url(
    settings.REDIS_URL,
    decode_responses=False,  # bytes para poder ler o conteúdo do arquivo
    socket_connect_timeout=2,
    socket_timeout=2,
)
_redis_sync_str = _redis_sync.from_url(
    settings.REDIS_URL,
    decode_responses=True,  # strings para status dos jobs
    socket_connect_timeout=2,
    socket_timeout=2,
)

_JOB_KEY_PREFIX = "f1:rag:job:"
_FILE_KEY_PREFIX = "f1:rag:file:"
_JOB_TTL = 60 * 60 * 24  # 24 horas


def _atualizar_job(job_id: str, updates: dict[str, Any]) -> None:
    """Atualiza campos do job no Redis (sync — dentro de task Celery)."""
    try:
        raw = _redis_sync_str.get(f"{_JOB_KEY_PREFIX}{job_id}")
        dados: dict[str, Any] = json.loads(raw) if raw else {}
        dados.update(updates)
        _redis_sync_str.setex(
            f"{_JOB_KEY_PREFIX}{job_id}",
            _JOB_TTL,
            json.dumps(dados),
        )
    except Exception as exc:
        logger.warning("ingest_job_update_falhou", job_id=job_id, erro=str(exc))


def _ler_e_deletar_arquivo_redis(job_id: str, log: Any) -> bytes | None:
    """
    Lê os bytes do arquivo do Redis e deleta a chave.
    Retorna None se a chave não existir (retry sem arquivo).
    """
    key = f"{_FILE_KEY_PREFIX}{job_id}"
    try:
        conteudo: bytes | None = _redis_sync_client.getdel(key)
        if conteudo:
            log.debug("ingest_arquivo_lido_do_redis", bytes=len(conteudo))
        return conteudo
    except Exception as exc:
        log.warning("ingest_arquivo_redis_falhou", erro=str(exc))
        return None


# ---------------------------------------------------------------------------
# Task principal: ingest_documento
# ---------------------------------------------------------------------------


@celery_app.task(
    name="feature_1_ia_personalizada.workers.ingest_documentos.ingest_documento",
    base=DLQTask,
    bind=True,
    queue="ia",
    max_retries=2,
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_jitter=True,
)
def ingest_documento(
    self: Any,
    escritorio_id: int,
    titulo: str,
    tipo: str,
    job_id: str,
    extensao: str = "pdf",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Ingere um documento jurídico no banco vetorial.

    Fluxo:
      1. Marca job como "em_andamento" no Redis.
      2. Lê os bytes do arquivo da chave Redis f1:rag:file:{job_id} e a deleta.
      3. Chama DocumentoIngester.ingerir_pdf() (async via asyncio.run).
      4. Marca job como "concluido", "duplicata" ou "erro".

    Em caso de retry após falha no passo 3, a chave Redis já foi deletada.
    O handler detecta self.request.retries > 0 e encerra sem nova tentativa.
    """
    log = logger.bind(job_id=job_id, escritorio_id=escritorio_id, titulo=titulo)
    log.info("ingest_documento_iniciado", tentativa=self.request.retries)

    _atualizar_job(job_id, {"status": "em_andamento"})

    arquivo_bytes = _ler_e_deletar_arquivo_redis(job_id, log)

    if arquivo_bytes is None:
        if self.request.retries > 0:
            log.warning("ingest_retry_arquivo_ausente", tentativa=self.request.retries)
            _atualizar_job(
                job_id,
                {
                    "status": "erro",
                    "erro": "Processamento falhou e arquivo já foi removido do Redis (retry impossível).",
                },
            )
            return {"job_id": job_id, "status": "erro"}
        raise FileNotFoundError(f"Arquivo não encontrado no Redis para job_id={job_id}")

    try:
        resultado = asyncio.run(
            _ingerir_async(
                arquivo_bytes=arquivo_bytes,
                escritorio_id=escritorio_id,
                titulo=titulo,
                tipo=tipo,
                metadata=metadata or {},
            )
        )

        if resultado.duplicata:
            log.info("ingest_documento_duplicata", doc_hash=resultado.doc_hash[:16])
            _atualizar_job(
                job_id,
                {"status": "duplicata", "chunks": 0, "doc_hash": resultado.doc_hash},
            )
        elif resultado.erro:
            log.error("ingest_documento_erro_logico", erro=resultado.erro)
            _atualizar_job(job_id, {"status": "erro", "erro": resultado.erro})
        else:
            log.info("ingest_documento_concluido", chunks=resultado.chunks_gerados)
            _atualizar_job(
                job_id,
                {
                    "status": "concluido",
                    "chunks": resultado.chunks_gerados,
                    "doc_hash": resultado.doc_hash,
                    "metadata": resultado.metadata_extraida,
                },
            )

        status_final = "duplicata" if resultado.duplicata else "concluido"
        return {"job_id": job_id, "status": status_final, "chunks": resultado.chunks_gerados}

    except Exception as exc:
        log.error("ingest_documento_excecao", erro=str(exc))
        _atualizar_job(job_id, {"status": "erro", "erro": str(exc)})
        raise  # DLQTask / autoretry_for captura e faz retry


async def _ingerir_async(
    arquivo_bytes: bytes,
    escritorio_id: int,
    titulo: str,
    tipo: str,
    metadata: dict[str, Any],
) -> Any:
    """Coroutine que instancia os serviços e executa a ingestão."""
    import redis.asyncio as redis_async

    from feature_1_ia_personalizada.services.rag.embeddings import EmbeddingGenerator
    from feature_1_ia_personalizada.services.rag.ingestion import DocumentoIngester

    redis_client = redis_async.from_url(settings.REDIS_URL, decode_responses=True)
    emb = EmbeddingGenerator(redis_client=redis_client)
    ingester = DocumentoIngester(
        embedding_generator=emb,
        session_factory=async_session_factory,
    )

    try:
        return await ingester.ingerir_pdf(
            arquivo_bytes=arquivo_bytes,
            escritorio_id=escritorio_id,
            titulo=titulo,
            tipo=tipo,
            metadata=metadata,
        )
    finally:
        await emb.aclose()
        await redis_client.aclose()


# ---------------------------------------------------------------------------
# Task auxiliar: ingest_jurisprudencia_publica
# ---------------------------------------------------------------------------


@celery_app.task(
    name="feature_1_ia_personalizada.workers.ingest_documentos.ingest_jurisprudencia_publica",
    base=DLQTask,
    bind=True,
    queue="ia",
    max_retries=1,
    autoretry_for=(Exception,),
    retry_backoff=60,
)
def ingest_jurisprudencia_publica(
    self: Any,
    tipo_acao: str,
    tribunal: str,
    escritorio_id: int,
) -> dict[str, Any]:
    """
    Pré-popula a base RAG do escritório com jurisprudência pública do DataJud.

    Chamado automaticamente no go-live do onboarding (Feature 4) para que
    novos escritórios já tenham contexto base disponível desde o primeiro dia.

    Nota: Jusbrasil não está ativo no momento — usa apenas DataJud.
    """
    log = logger.bind(escritorio_id=escritorio_id, tipo_acao=tipo_acao, tribunal=tribunal)
    log.info("ingest_jurisprudencia_publica_iniciado")

    resultado = asyncio.run(
        _ingerir_jurisprudencia_async(
            tipo_acao=tipo_acao,
            tribunal=tribunal,
            escritorio_id=escritorio_id,
        )
    )

    log.info("ingest_jurisprudencia_publica_concluido", **resultado)
    return resultado


async def _ingerir_jurisprudencia_async(
    tipo_acao: str,
    tribunal: str,
    escritorio_id: int,
) -> dict[str, Any]:
    """
    Busca jurisprudência no DataJud e ingere os resultados como documentos RAG.
    """
    import redis.asyncio as redis_async

    from feature_1_ia_personalizada.services.legal_data.datajud_client import (
        DataJudClient,
    )
    from feature_1_ia_personalizada.services.rag.embeddings import EmbeddingGenerator
    from feature_1_ia_personalizada.services.rag.ingestion import DocumentoIngester

    redis_client = redis_async.from_url(settings.REDIS_URL, decode_responses=True)
    emb = EmbeddingGenerator(redis_client=redis_client)
    ingester = DocumentoIngester(
        embedding_generator=emb,
        session_factory=async_session_factory,
    )
    datajud = DataJudClient()

    ingeridos = 0
    duplicatas = 0
    erros = 0

    try:
        processos = await datajud.buscar_jurisprudencia(  # type: ignore[attr-defined]
            tipo_acao=tipo_acao, tribunal=tribunal, limite=20
        )

        for proc in processos:
            texto = proc.get("ementa") or proc.get("descricao") or ""
            if not texto or len(texto) < 100:
                continue

            titulo = f"{tribunal} — {tipo_acao} — {proc.get('numero_cnj', 'S/N')}"
            metadata = {
                "tribunal": tribunal,
                "tipo_acao": tipo_acao,
                "numero_cnj": proc.get("numero_cnj"),
                "data_doc": proc.get("data_julgamento"),
                "resultado": proc.get("resultado"),
                "fonte": "datajud_publico",
            }

            resultado = await ingester.ingerir_texto(
                texto=texto,
                escritorio_id=escritorio_id,
                titulo=titulo,
                tipo="jurisprudencia",
                metadata=metadata,
            )

            if resultado.duplicata:
                duplicatas += 1
            elif resultado.erro:
                erros += 1
            else:
                ingeridos += resultado.chunks_gerados

    finally:
        await emb.aclose()
        await redis_client.aclose()

    return {
        "tipo_acao": tipo_acao,
        "tribunal": tribunal,
        "chunks_ingeridos": ingeridos,
        "duplicatas": duplicatas,
        "erros": erros,
    }
