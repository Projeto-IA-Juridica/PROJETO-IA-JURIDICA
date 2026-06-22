# feature_1_ia_personalizada/workers/ingest_documentos.py
"""
Tasks Celery de ingestão de documentos jurídicos no RAG.

Tasks:
  ingest_documento              — ingere um arquivo PDF/DOCX/TXT em background
  ingest_jurisprudencia_publica — pré-popula base RAG com jurisprudência do DataJud

Fila: "ia" (definida em celery_app.py)
Base: DLQTask — em caso de falha após retries, encaminha para dead_letter.

Gerenciamento de arquivo temporário:
  O arquivo em /tmp é deletado IMEDIATAMENTE após leitura para memória, antes
  de qualquer processamento async. Isso garante que o disco é liberado cedo e
  que retries do Celery não falham por "arquivo não encontrado" (o arquivo já
  não é necessário após a leitura).

  O finally é um safety-net para o caso em que a leitura falha antes da deleção.

Retry × arquivo:
  Como o arquivo é deletado antes do asyncio.run(), um retry causado por falha
  no processamento (ex.: DB timeout) recebe arquivo_path inexistente. O handler
  detecta isso via self.request.retries > 0 e retorna sem nova tentativa, evitando
  cascata de FileNotFoundError.

Async em Celery:
  DocumentoIngester usa AsyncSession — executado via asyncio.run() dentro
  da task síncrona do Celery. Padrão recomendado para Celery 5.x sem
  necessidade de celery[asyncio].
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import redis as _redis_sync
import structlog

from feature_1_ia_personalizada.workers.celery_app import DLQTask, celery_app
from shared.config.settings import settings
from shared.database.connection import async_session_factory

logger = structlog.get_logger(__name__)

# Cliente Redis síncrono — apenas para atualizar status dos jobs
_redis_sync_client = _redis_sync.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)

_JOB_KEY_PREFIX = "f1:rag:job:"
_JOB_TTL = 60 * 60 * 24  # 24 horas


def _atualizar_job(job_id: str, updates: dict[str, Any]) -> None:
    """Atualiza campos do job no Redis (sync — dentro de task Celery)."""
    try:
        raw = _redis_sync_client.get(f"{_JOB_KEY_PREFIX}{job_id}")
        dados: dict[str, Any] = json.loads(raw) if raw else {}
        dados.update(updates)
        _redis_sync_client.setex(
            f"{_JOB_KEY_PREFIX}{job_id}",
            _JOB_TTL,
            json.dumps(dados),
        )
    except Exception as exc:
        logger.warning("ingest_job_update_falhou", job_id=job_id, erro=str(exc))


def _deletar_tmp(arquivo_path: str, log: Any) -> bool:
    """
    Deleta o arquivo temporário. Retorna True se deletado com sucesso.
    Falha silenciosa com log para não mascarar outros erros.
    """
    try:
        if os.path.exists(arquivo_path):
            os.unlink(arquivo_path)
            log.debug("ingest_tmp_deletado", path=arquivo_path)
            return True
    except Exception as exc_del:
        log.warning("ingest_tmp_delete_falhou", path=arquivo_path, erro=str(exc_del))
    return False


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
    arquivo_path: str,
    escritorio_id: int,
    titulo: str,
    tipo: str,
    job_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Ingere um documento jurídico no banco vetorial.

    Fluxo:
      1. Marca job como "em_andamento" no Redis.
      2. Lê o arquivo de /tmp para memória.
      3. Deleta o arquivo de /tmp imediatamente após leitura.
      4. Chama DocumentoIngester.ingerir_pdf() (async via asyncio.run).
      5. Marca job como "concluido" ou "erro".

    Em caso de retry após falha no passo 4, o arquivo já não existe.
    O handler detecta self.request.retries > 0 e retorna sem nova tentativa.
    """
    log = logger.bind(job_id=job_id, escritorio_id=escritorio_id, titulo=titulo)
    log.info("ingest_documento_iniciado", tentativa=self.request.retries)

    _atualizar_job(job_id, {"status": "em_andamento"})

    tmp_deletado = False

    try:
        # Arquivo ausente num retry significa que foi limpo após a tentativa anterior.
        # O erro original já foi registrado — encerra sem nova tentativa.
        if not os.path.exists(arquivo_path):
            if self.request.retries > 0:
                log.warning(
                    "ingest_retry_arquivo_ausente",
                    path=arquivo_path,
                    tentativa=self.request.retries,
                )
                _atualizar_job(
                    job_id,
                    {
                        "status": "erro",
                        "erro": "Processamento falhou e arquivo temporário já foi removido (retry impossível).",
                    },
                )
                return {"job_id": job_id, "status": "erro"}
            raise FileNotFoundError(f"Arquivo temporário não encontrado: {arquivo_path}")

        with open(arquivo_path, "rb") as f:
            arquivo_bytes = f.read()

        # Deleta o arquivo IMEDIATAMENTE após leitura — libera disco cedo
        # e garante que retries não falhem com FileNotFoundError.
        tmp_deletado = _deletar_tmp(arquivo_path, log)

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

        return {"job_id": job_id, "status": "concluido", "chunks": resultado.chunks_gerados}

    except Exception as exc:
        log.error("ingest_documento_excecao", erro=str(exc))
        _atualizar_job(job_id, {"status": "erro", "erro": str(exc)})
        raise  # DLQTask / autoretry_for captura e faz retry

    finally:
        # Safety-net: deleta o arquivo se a leitura falhou antes de tmp_deletado = True
        if not tmp_deletado:
            _deletar_tmp(arquivo_path, log)


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
