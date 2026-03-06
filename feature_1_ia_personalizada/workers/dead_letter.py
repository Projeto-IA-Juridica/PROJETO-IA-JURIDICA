# feature_1_ia_personalizada/workers/dead_letter.py
"""
Dead Letter Queue — Handler de tasks que esgotaram todos os retries.

Fluxo:
  task falha → autoretry_for tenta N vezes → DLQTask.on_failure detecta
  esgotamento → envia para fila "dead_letter" → processar_dlq executa aqui.

O objetivo é: nunca perder uma falha silenciosamente.
  1. Log estruturado com contexto completo (visível via structlog + Loki/Sentry)
  2. Persistência no banco (interacao tipo "dlq_falha") para post-mortem
  3. Resultado preservado no Flower para triagem manual

Visualizar no Flower: http://localhost:5555 → Tasks → fila: dead_letter

Para re-executar uma task da DLQ manualmente:
  # Inspecionar o payload persistido no banco (tipo="dlq_falha")
  # Chamar a task original diretamente com os mesmos argumentos
  from feature_1_ia_personalizada.workers.send_notifications import (
      enviar_notificacao_andamento,
  )
  enviar_notificacao_andamento.apply_async(args=[id_processo, descricao])
"""

from __future__ import annotations

import structlog

from .celery_app import celery_app

logger = structlog.get_logger(__name__)

# Mapa: nome parcial da task → índice do id_cliente nos args posicionais.
# None como valor significa que id_cliente não está diretamente nos args
# e precisa ser resolvido via lookup no banco.
_ID_CLIENTE_DIRETO: dict[str, int] = {
    # processar_mensagem_recebida(id_escritorio, id_cliente, mensagem, tipo)
    "processar_mensagem_recebida": 1,
}

_ID_CLIENTE_VIA_PROCESSO: dict[str, int] = {
    # enviar_notificacao_andamento(id_processo, descricao_andamento)
    # id_cliente resolvido via JOIN processo→cliente no banco.
    "enviar_notificacao_andamento": 0,
}


def _resolver_id_cliente(nome_task: str, args: list) -> int | None:
    """
    Resolve id_cliente a partir dos args da task original.

    Estratégia em duas etapas:
    1. Extração direta — id_cliente está nos args (ex: processar_mensagem_recebida)
    2. Lookup via banco — id_processo nos args, resolve cliente_id via JOIN
       (ex: enviar_notificacao_andamento)

    Retorna None se a resolução falhar ou a task não for mapeada.
    """
    for sufixo, idx in _ID_CLIENTE_DIRETO.items():
        if sufixo in nome_task:
            return int(args[idx]) if len(args) > idx else None

    for sufixo, idx in _ID_CLIENTE_VIA_PROCESSO.items():
        if sufixo in nome_task:
            if len(args) <= idx:
                return None
            id_processo = int(args[idx])
            try:
                from shared.database.worker_queries import query_processo_e_cliente

                resultado = query_processo_e_cliente(id_processo)
                if resultado is not None:
                    processo, _ = resultado
                    return processo.cliente_id
            except Exception as lookup_exc:
                logger.warning(
                    "dlq.lookup_cliente_falhou",
                    nome_task=nome_task,
                    id_processo=id_processo,
                    erro=str(lookup_exc),
                )
            return None

    return None


@celery_app.task(
    # ATENÇÃO: name= é um contrato entre três pontos do código — NÃO remover.
    # Alterar este valor exige atualizar em sincronia:
    #   1. celery_app.py → task_routes (chave do dict)
    #   2. celery_app.py → DLQTask.on_failure → celery_app.send_task(nome, ...)
    # Se name= for removido, o Celery registra a task com o caminho completo do módulo
    # ("feature_1_ia_personalizada.workers.dead_letter.processar_dlq") e o send_task
    # enfileira para "workers.dead_letter.processar_dlq" — nenhum worker consome,
    # falha silenciosa exatamente no caminho de recuperação de falhas.
    name="workers.dead_letter.processar_dlq",
    queue="dead_letter",
    max_retries=0,        # DLQ não retenta — exige intervenção manual
    ignore_result=False,  # mantém resultado visível no Flower para triagem
    acks_late=False,      # DLQ deve ack imediatamente — não há recovery aqui
)
def processar_dlq(
    *,
    nome_task: str,
    task_id: str,
    args: list,
    kwargs: dict,
    erro: str,
    traceback: str,
    tentativas: int,
) -> dict:
    """
    Handler do Dead Letter Queue.

    Recebe o payload de qualquer task que esgotou seus retries e:
      - Loga com nível ERROR (capturado pelo Sentry e Loki)
      - Persiste no banco como interacao tipo "dlq_falha" para post-mortem
      - Retorna metadados estruturados visíveis no Flower
    """
    logger.error(
        "dlq.task_falhou_definitivamente",
        nome_task=nome_task,
        task_id=task_id,
        args=args,
        kwargs=kwargs,
        erro=erro,
        tentativas=tentativas,
        # traceback omitido do log principal para não poluir métricas
        # — está preservado no campo "traceback" do Flower e no banco
    )

    id_cliente = _resolver_id_cliente(nome_task, args)

    # Persiste no banco para análise post-mortem.
    # Falha silenciosa: se o banco também estiver down, não queremos
    # que o handler da DLQ entre em loop.
    # insert_interacao requer id_cliente não-nulo (FK obrigatória).
    # Se a resolução falhou (processo não encontrado, DB down durante lookup,
    # task não mapeada), loga aviso — o evento já está no Sentry/Loki via ERROR acima.
    try:
        if id_cliente is not None:
            from shared.database.worker_queries import insert_interacao

            insert_interacao(
                id_cliente=id_cliente,
                id_processo=None,
                tipo="dlq_falha",
                metadata_json={
                    "nome_task": nome_task,
                    "task_id": task_id,
                    "args": args,
                    "kwargs": kwargs,
                    "tentativas": tentativas,
                    "erro": erro[:2000],  # limita para caber no JSON do banco
                },
            )
        else:
            logger.warning(
                "dlq.sem_id_cliente_persistencia_ignorada",
                nome_task=nome_task,
                task_id=task_id,
                motivo="id_cliente nao resolvido — falha capturada apenas em Sentry/Loki",
            )
    except Exception as db_exc:
        logger.warning(
            "dlq.persistencia_falhou",
            nome_task=nome_task,
            task_id=task_id,
            erro_db=str(db_exc),
        )

    return {
        "status": "dlq_registrado",
        "nome_task": nome_task,
        "task_id": task_id,
        "tentativas": tentativas,
        "erro": erro[:500],
    }
