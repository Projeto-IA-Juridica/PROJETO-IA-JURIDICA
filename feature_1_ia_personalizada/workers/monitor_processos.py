# feature_1_ia_personalizada/workers/monitor_processos.py

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import structlog
from celery.exceptions import SoftTimeLimitExceeded
from prometheus_client import Gauge

from feature_1_ia_personalizada.services.legal_data.cache_manager import (
    get_andamentos_sync,
    set_andamentos_sync,
)
import pybreaker

from feature_1_ia_personalizada.services.legal_data.data_cleaner import (
    LegalDataCleaner as DataCleaner,
)
from feature_1_ia_personalizada.services.legal_data.datajud_client import DataJudClient
from feature_1_ia_personalizada.services.ai.juridical_translator import JuridicalTranslator
from shared.config.settings import settings
from shared.database.worker_queries import (
    query_processo_por_id,
    query_processos_monitorados,
    update_ultimo_andamento,
)

# from feature_1_ia_personalizada.workers.celery_app import celery_app
from .celery_app import celery_app

logger = structlog.get_logger(__name__)

_processos_monitorados_total = Gauge(
    "processos_monitorados_total",
    "Número atual de processos com monitoramento ativo",
)

# CIRCUIT BREAKER — DataJud (fonte primária no MVP)
_datajud_breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60)

# CONFIGURAÇÕES


TAMANHO_LOTE = 10
INTERVALO_ENTRE_REQUISICOES_SEGUNDOS = 0.4
# Tempo máximo por processo individual (task monitorar_processo_individual).
# A task monitorar_processos usa TEMPO_MAXIMO_TASK_SEGUNDOS (separado).
TEMPO_MAXIMO_PROCESSO_SEGUNDOS = 30
# Tempo máximo para a task que varre todos os processos.
# Com 0.4s de sleep por processo: 600s suporta ~1.500 processos por ciclo.
# Ajustar conforme o volume real do banco em produção.
TEMPO_MAXIMO_TASK_SEGUNDOS = 600
_LIMITE_BUSCA_PROCESSOS = 10_000  # máximo de processos por execução da task


# FUNÇÕES AUXILIARES


Andamento = dict[str, Any] | Any


def extrair_valor(objeto: Andamento, chave: str, valor_padrao: Any = None) -> Any:
    if isinstance(objeto, dict):
        return objeto.get(chave, valor_padrao)
    return getattr(objeto, chave, valor_padrao)


def converter_para_iso(data: Any) -> str | None:
    if data is None:
        return None
    if isinstance(data, datetime):
        return data.isoformat()
    return str(data)


def extrair_texto_e_data_do_andamento(
    andamento: Andamento,
) -> tuple[str, str | None]:
    texto = extrair_valor(andamento, "texto", "")
    data = extrair_valor(andamento, "data", None)
    return str(texto), converter_para_iso(data)


@_datajud_breaker
def buscar_andamentos_datajud(
    numero_processo: str,
    data_referencia_iso: str | None,
    cliente_datajud: DataJudClient,
) -> list[Any]:
    return cliente_datajud.buscar_novos_andamentos(numero_processo, data_referencia_iso)


# PROCESSAMENTO DE UM PROCESSO


def processar_processo_individual(dados_processo: dict[str, Any]) -> dict[str, Any]:

    id_processo = int(dados_processo["id"])
    numero_processo = str(dados_processo["numero"])
    data_ultimo_andamento_salvo = dados_processo.get("data_ultimo_andamento")

    # 1️⃣ Buscar andamentos: Redis (cache) → Jusbrasil → DataJud (fallback)
    # Cache-aside: hit evita chamada HTTP e reduz custo de API.
    # Miss: chama os clients externos (requer Fase 3 — imports acima).
    fonte_utilizada = "cache"
    lista_andamentos = get_andamentos_sync(numero_processo)

    if lista_andamentos is None:
        cliente_datajud = DataJudClient(api_key=settings.DATAJUD_API_KEY)
        fonte_utilizada = "datajud"
        lista_andamentos = buscar_andamentos_datajud(
            numero_processo,
            data_ultimo_andamento_salvo,
            cliente_datajud,
        )

        # Grava no Redis para próximas execuções (TTL 6h, definido em LegalDataCacheManager).
        # Usa "is not None" para cachear também listas vazias [] — evita chamada à API
        # novamente dentro do TTL para processos sem movimentações recentes.
        if lista_andamentos is not None:
            set_andamentos_sync(numero_processo, lista_andamentos)

    if not lista_andamentos:
        return {
            "id_processo": id_processo,
            "sucesso": True,
            "novos_andamentos": 0,
            "fonte": fonte_utilizada,
        }

    quantidade_novos = 0
    ultima_data_encontrada = None
    ultimo_texto_limpo = None

    for andamento in lista_andamentos:

        texto_original, data_iso = extrair_texto_e_data_do_andamento(andamento)

        texto_limpo = DataCleaner.limpar_andamento(texto_original)
        texto_traduzido = JuridicalTranslator.traduzir_andamento(texto_limpo)

        celery_app.send_task(
            "feature_1_ia_personalizada.workers.send_notifications.enviar_notificacao_andamento",
            args=[id_processo, texto_traduzido],
            queue="notificacoes",
        )

        quantidade_novos += 1
        ultima_data_encontrada = data_iso
        ultimo_texto_limpo = texto_limpo

    # Atualizar banco com último andamento
    if ultima_data_encontrada:
        update_ultimo_andamento(
            id_processo,
            ultimo_texto_limpo or "",
            ultima_data_encontrada,
        )

    return {
        "id_processo": id_processo,
        "sucesso": True,
        "novos_andamentos": quantidade_novos,
        "fonte": fonte_utilizada,
        "data_atualizada_para": ultima_data_encontrada,
    }


# TASK: MONITORAR TODOS
@celery_app.task(
    name="workers.monitorar_processos",
    soft_time_limit=TEMPO_MAXIMO_TASK_SEGUNDOS,
    time_limit=TEMPO_MAXIMO_TASK_SEGUNDOS + 30,
)
def monitorar_processos() -> dict[str, Any]:

    resultados = []
    total_processados = 0
    total_erros = 0

    try:
        processos = query_processos_monitorados(limite=_LIMITE_BUSCA_PROCESSOS)
    except Exception as erro:
        return {"sucesso": False, "erro": str(erro)}

    _processos_monitorados_total.set(len(processos))

    for indice in range(0, len(processos), TAMANHO_LOTE):
        lote = processos[indice : indice + TAMANHO_LOTE]

        for processo in lote:
            try:
                resultado = processar_processo_individual(processo)
                resultados.append(resultado)
                total_processados += 1

            except SoftTimeLimitExceeded:
                total_erros += 1
                resultados.append(
                    {
                        "id_processo": processo.get("id"),
                        "sucesso": False,
                        "erro": "tempo_maximo_excedido_30s",
                    }
                )

            except Exception as erro:
                total_erros += 1
                resultados.append(
                    {
                        "id_processo": processo.get("id"),
                        "sucesso": False,
                        "erro": str(erro),
                    }
                )

            # Rate limiting por requisição — inclui o último processo de cada lote,
            # o que gera um sleep extra antes do início do lote seguinte. Aceitável
            # para MVP; ajustar se precisar de intervalo uniforme entre lotes.
            time.sleep(INTERVALO_ENTRE_REQUISICOES_SEGUNDOS)

    return {
        "sucesso": True,
        "total_processados": total_processados,
        "total_erros": total_erros,
        "resumo_primeiros_20": resultados[:20],
    }


# TASK: MONITORAR UM PROCESSO


@celery_app.task(
    name="workers.monitorar_processo_individual",
    soft_time_limit=TEMPO_MAXIMO_PROCESSO_SEGUNDOS,
    time_limit=TEMPO_MAXIMO_PROCESSO_SEGUNDOS + 5,
)
def monitorar_processo_individual(id_processo: int) -> dict[str, Any]:

    processo = query_processo_por_id(int(id_processo))

    if not processo:
        return {
            "sucesso": False,
            "erro": "processo_nao_encontrado",
            "id_processo": id_processo,
        }

    try:
        return processar_processo_individual(processo)

    except SoftTimeLimitExceeded:
        return {
            "sucesso": False,
            "erro": "tempo_maximo_excedido_30s",
            "id_processo": id_processo,
        }

    except Exception as erro:
        return {
            "sucesso": False,
            "erro": str(erro),
            "id_processo": id_processo,
        }
