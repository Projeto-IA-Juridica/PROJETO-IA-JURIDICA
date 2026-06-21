# feature_1_ia_personalizada/workers/monitor_processos.py

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import pybreaker
import structlog
from celery.exceptions import SoftTimeLimitExceeded
from prometheus_client import Gauge

from feature_1_ia_personalizada.services.ai.juridical_translator import (
    JuridicalTranslator,
)
from feature_1_ia_personalizada.services.ai.processo_state import ProcessoStateManager
from feature_1_ia_personalizada.services.legal_data.cache_manager import (
    get_andamentos_sync,
    set_andamentos_sync,
)
from feature_1_ia_personalizada.services.legal_data.data_cleaner import (
    LegalDataCleaner as DataCleaner,
)
from feature_1_ia_personalizada.services.legal_data.datajud_client import (
    DataJudClient,
    _parse_iso_dt,
)
from feature_1_ia_personalizada.services.legal_data.score_risco import (
    ScoreRiscoCalculator,
)
from shared.config.settings import settings
from shared.database.worker_queries import (
    query_processo_por_id,
    query_processos_monitorados,
    update_metadados_processo,
    update_ultimo_andamento,
)

from .celery_app import celery_app

logger = structlog.get_logger(__name__)

_processos_monitorados_total = Gauge(
    "processos_monitorados_total",
    "Número atual de processos com monitoramento ativo",
)

# CIRCUIT BREAKER — DataJud (fonte primária no MVP)
_datajud_breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60)

# Instância única do calculador de score (stateless — seguro para reuso)
_score_calculator = ScoreRiscoCalculator()

# CONFIGURAÇÕES

TAMANHO_LOTE = 10
INTERVALO_ENTRE_REQUISICOES_SEGUNDOS = 0.4
TEMPO_MAXIMO_PROCESSO_SEGUNDOS = 30
TEMPO_MAXIMO_TASK_SEGUNDOS = 600
_LIMITE_BUSCA_PROCESSOS = 10_000


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


def _filtrar_andamentos_por_data(
    andamentos: list[Any],
    data_referencia_iso: Any,
) -> list[Any]:
    """Aplica o mesmo filtro de data de buscar_novos_andamentos ao cache.

    O cache compartilhado (orchestrator + worker) contém TODOS os movimentos
    sem filtro. Sem esta função, o worker re-notificaria andamentos já vistos
    toda vez que houvesse um cache hit do orchestrator.
    """
    if not data_referencia_iso:
        return andamentos
    ref_dt = _parse_iso_dt(str(data_referencia_iso))
    if ref_dt is None:
        return andamentos

    filtrados = []
    for a in andamentos:
        data_hora = extrair_valor(a, "data", None)
        if data_hora:
            mov_dt = _parse_iso_dt(str(data_hora))
            if mov_dt and mov_dt <= ref_dt:
                continue
        filtrados.append(a)
    return filtrados


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
    tipo_acao = dados_processo.get("tipo_acao") or "não informado"
    polo_cliente = dados_processo.get("polo_cliente") or "autor"

    # 1️⃣ Buscar andamentos: Redis (cache) → DataJud (fallback)
    # O cache é compartilhado com o orchestrator, que salva TODOS os movimentos
    # sem filtro de data. O worker DEVE aplicar o filtro ao ler do cache para
    # evitar re-notificar movimentos já vistos (falso positivo).
    fonte_utilizada = "cache"
    raw_cache = get_andamentos_sync(numero_processo)
    tribunal_preenchido = bool(dados_processo.get("tribunal"))

    if raw_cache is not None and tribunal_preenchido:
        lista_andamentos = _filtrar_andamentos_por_data(raw_cache, data_ultimo_andamento_salvo)
    else:
        cliente_datajud = DataJudClient(api_key=settings.DATAJUD_API_KEY)
        fonte_utilizada = "datajud"

        # Quando tribunal ainda não foi preenchido, usa buscar_dados_completos
        # para extrair metadados e andamentos numa única chamada à API.
        if not tribunal_preenchido:
            lista_andamentos, metadados = cliente_datajud.buscar_dados_completos(
                numero_processo,
                data_ultimo_andamento_salvo,
            )
            if metadados:
                try:
                    update_metadados_processo(id_processo, metadados)
                except Exception as exc:
                    logger.warning("update_metadados_falhou", processo_id=id_processo, erro=str(exc))
        else:
            lista_andamentos = buscar_andamentos_datajud(
                numero_processo,
                data_ultimo_andamento_salvo,
                cliente_datajud,
            )

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
    ultima_data_encontrada: str | None = None
    _ultima_data_dt: datetime | None = None  # para comparação correta com timezone
    ultimo_texto_limpo: str | None = None

    state_manager = ProcessoStateManager()

    for andamento in lista_andamentos:
        texto_original, data_iso = extrair_texto_e_data_do_andamento(andamento)

        texto_limpo = DataCleaner.limpar_andamento(texto_original)

        estado = state_manager.update_state(id_processo, texto_limpo)
        historico = state_manager.gerar_contexto_historico(id_processo)

        texto_resumido = JuridicalTranslator.traduzir_com_contexto(
            andamento=texto_limpo,
            fase_atual=estado.get("fase", "conhecimento"),
            historico=historico,
            tipo_acao=tipo_acao,
            polo_cliente=polo_cliente,
        )

        celery_app.send_task(
            "feature_1_ia_personalizada.workers.send_notifications.enviar_notificacao_andamento",
            args=[id_processo, texto_resumido],
            queue="notificacoes",
        )

        quantidade_novos += 1
        ultimo_texto_limpo = texto_limpo

        # Mantém a data MAIS RECENTE entre todos os andamentos do ciclo.
        # DataJud não garante ordem; sobrescrever a cada iteração salvaria a
        # data mais ANTIGA, fazendo o próximo ciclo re-processar os mesmos andamentos.
        if data_iso:
            mov_dt = _parse_iso_dt(data_iso)
            if mov_dt and (_ultima_data_dt is None or mov_dt > _ultima_data_dt):
                _ultima_data_dt = mov_dt
                ultima_data_encontrada = data_iso

    # 2️⃣ Atualizar banco e recalcular score em paralelo — operações independentes entre si.
    # ThreadPoolExecutor: seguro porque cada função usa sua própria sessão síncrona de DB.
    futures = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        if ultima_data_encontrada:
            futures["andamento"] = executor.submit(
                update_ultimo_andamento,
                id_processo,
                ultimo_texto_limpo or "",
                ultima_data_encontrada,
            )
        futures["score"] = executor.submit(_atualizar_score, dados_processo)

    # Propaga exceções de update_ultimo_andamento (crítico); score já tem graceful degradation interna
    if "andamento" in futures:
        futures["andamento"].result()

    return {
        "id_processo": id_processo,
        "sucesso": True,
        "novos_andamentos": quantidade_novos,
        "fonte": fonte_utilizada,
        "data_atualizada_para": ultima_data_encontrada,
    }


def _atualizar_score(
    dados_processo: dict[str, Any],
) -> None:
    """
    Calcula e persiste o score de risco no banco.
    Operação em memória (<50ms) — única I/O é o update_score abaixo.
    Falha silenciosa: score não pode travar o worker principal.
    """
    try:
        # Cria objeto leve com atributos esperados pelo ScoreRiscoCalculator
        class _ProcessoProxy:
            tipo_acao = dados_processo.get("tipo_acao")
            valor_causa = dados_processo.get("valor_causa")
            fase_processual = dados_processo.get("fase_processual")
            polo_cliente = dados_processo.get("polo_cliente") or "autor"

        score_obj = _score_calculator.calcular(_ProcessoProxy(), None)

        from shared.database.worker_queries import update_score_risco

        update_score_risco(
            int(dados_processo["id"]),
            score_obj.score,
            score_obj.nivel,
            score_obj.componentes.model_dump(),
            score_obj.interpretacao,
            score_obj.atualizado_em,
        )

    except Exception as exc:
        logger.warning(
            "score_risco_falhou",
            processo_id=dados_processo.get("id"),
            erro=str(exc),
        )


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

    # Gauge por nível de risco e escritório — conta antes do ciclo de atualização
    # para refletir o estado persistido no banco (scores calculados no ciclo anterior).
    try:
        from collections import defaultdict

        from feature_1_ia_personalizada.api.routes.metrics import processos_por_risco_gauge

        _dist: dict[tuple[str, str], int] = defaultdict(int)
        for _p in processos:
            _esc = str(_p.get("escritorio_id", "desconhecido"))
            _nivel = str(_p.get("score_nivel") or "sem_score")
            _dist[(_esc, _nivel)] += 1
        for (_esc, _nivel), _total in _dist.items():
            processos_por_risco_gauge.labels(escritorio_id=_esc, nivel=_nivel).set(_total)
    except Exception:
        pass  # métricas nunca bloqueiam o worker

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
