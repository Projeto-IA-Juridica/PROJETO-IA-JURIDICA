# feature_1_ia_personalizada/services/legal_data/vitoria_preditor.py
"""
VitoriaPreditor — Contexto histórico de casos similares via DataJud (CNJ).

ATENÇÃO — Compliance OAB:
  Este módulo NÃO calcula "probabilidade de vitória" nem faz predições.
  Ele coleta e apresenta estatísticas de desfecho de CASOS PÚBLICOS SIMILARES
  para fornecer contexto informativo ao cliente, sem constituir opinião jurídica.

Fluxo:
  1. Deriva o índice ElasticSearch a partir do número CNJ
  2. Se tipo_acao não disponível localmente, busca do próprio processo no DataJud
  3. Busca casos com mesma classe/tipo de ação no mesmo tribunal (DataJud)
  4. Classifica movimentos em: favorável_autor | desfavorável_autor | neutro
  5. Ajusta perspectiva para polo do cliente (autor ou réu)
  6. Retorna EstatisticaProcessual (com todos os percentuais) ou None

ScoreRiscoCalculator (novo — Feature 2):
  Calcula score de complexidade/risco (0–100) para uso interno do advogado.
  NÃO prevê vitória/derrota. Alimenta o painel e a Feature 4 (ML de prazos).
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import structlog
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field

from feature_1_ia_personalizada.services.legal_data.datajud_client import (
    DataJudClientError,
    _indice_para_cnj,
)
from shared.config.constants import (
    SCORE_RISCO_COMPLEXIDADE_POR_TIPO,
    SCORE_RISCO_PESOS,
    SCORE_RISCO_POR_FASE,
    SCORE_RISCO_PRAZO_MAX_REFERENCIA,
    SCORE_RISCO_SALARIO_MINIMO_REF,
)

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api-publica.datajud.cnj.jus.br"

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

MIN_CASOS_COM_DESFECHO: int = 10
MAX_CASOS_BUSCA: int = 100

# Listas de índices para fallback nacional (sem wildcard — API pública não suporta)
_INDICES_TJ_NACIONAIS = [
    "api_publica_tjsp",
    "api_publica_tjmg",
    "api_publica_tjrj",
    "api_publica_tjrs",
    "api_publica_tjpr",
    "api_publica_tjba",
    "api_publica_tjsc",
    "api_publica_tjgo",
    "api_publica_tjce",
    "api_publica_tjpe",
]
_INDICES_TRF_NACIONAIS = [
    "api_publica_trf1",
    "api_publica_trf2",
    "api_publica_trf3",
    "api_publica_trf4",
    "api_publica_trf5",
    "api_publica_trf6",
]
_INDICES_TRT_NACIONAIS = [
    "api_publica_trt1",
    "api_publica_trt2",
    "api_publica_trt3",
    "api_publica_trt4",
    "api_publica_trt5",
    "api_publica_trt15",
]

DISCLAIMER_ESTATISTICA = (
    "Estes são dados históricos de processos públicos similares, "
    "obtidos do DataJud (CNJ). Não representam previsão de resultado "
    "para o seu caso. Cada processo é único. Converse com seu advogado(a) "
    "para uma análise personalizada."
)

DISCLAIMER_ESTATISTICA_NACIONAL = (
    "Estes são dados históricos de processos similares em tribunais brasileiros, "
    "obtidos do DataJud (CNJ). Por não haver amostra suficiente no mesmo tribunal, "
    "utilizamos referências nacionais como contexto informativo. "
    "Não representam previsão de resultado para o seu caso. "
    "Cada processo é único. Converse com seu advogado(a) para uma análise personalizada."
)

# ---------------------------------------------------------------------------
# Métricas Prometheus
# ---------------------------------------------------------------------------

_estatistica_total = Counter(
    "vitoria_estatistica_total",
    "Total de consultas de estatísticas processuais",
    labelnames=["resultado"],
)
_estatistica_duration = Histogram(
    "vitoria_estatistica_duration_seconds",
    "Tempo de consulta de estatísticas de casos similares (segundos)",
)

# ---------------------------------------------------------------------------
# Dataclass de resultado
# ---------------------------------------------------------------------------


@dataclass
class EstatisticaProcessual:
    casos_analisados: int
    casos_com_desfecho: int
    pct_favoravel: float
    pct_desfavoravel: float
    pct_neutro: float
    confianca: str
    tipo_acao: str
    polo_cliente: str
    escopo: str = "tribunal"  # "tribunal" | "nacional"
    disclaimer: str = field(default=DISCLAIMER_ESTATISTICA)
    fatores: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Preditor (legado — mantido intacto)
# ---------------------------------------------------------------------------


class VitoriaPreditor:

    _FAVORAVEL_AUTOR = re.compile(
        r"\b("
        r"procedente"
        r"|procedência"
        r"|procedência do pedido"
        r"|parcialmente procedente"
        r"|procedência parcial"
        r"|deferido"
        r"|deferimento"
        r"|conced[ieu]"
        r"|concessão"
        r"|provido"
        r")\b",
        re.IGNORECASE,
    )

    _DESFAVORAVEL_AUTOR = re.compile(
        r"\b("
        r"improcedente"
        r"|improcedência"
        r"|improcedência do pedido"
        r"|indeferido"
        r"|indeferimento"
        r"|não provido"
        r"|desprovido"
        r"|negado"
        r")\b",
        re.IGNORECASE,
    )

    _NEUTRO = re.compile(
        r"\b("
        r"acordo"
        r"|homologação de acordo"
        r"|extinção sem resolução"
        r"|extinção sem julgamento de mérito"
        r"|arquivamento"
        r"|desistência"
        r")\b",
        re.IGNORECASE,
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    # -----------------------------------------------------------------------
    # API pública
    # -----------------------------------------------------------------------

    async def buscar_estatistica(
        self,
        numero_cnj: str,
        tipo_acao: str | None,
        polo_cliente: str = "autor",
    ) -> EstatisticaProcessual | None:
        log = logger.bind(cnj=numero_cnj, polo=polo_cliente)

        try:
            indice = _indice_para_cnj(numero_cnj)
        except DataJudClientError as exc:
            log.warning("vitoria_preditor_cnj_invalido", erro=str(exc))
            _estatistica_total.labels(resultado="sem_dados").inc()
            return None

        # Se tipo_acao não cadastrado localmente, busca do DataJud pelo CNJ
        if not tipo_acao or not tipo_acao.strip():
            log.info("vitoria_preditor_buscando_tipo_acao_no_datajud")
            tipo_acao = await self._buscar_tipo_acao_do_cnj(indice, numero_cnj)
            if not tipo_acao:
                log.info("vitoria_preditor_sem_tipo_acao")
                _estatistica_total.labels(resultado="sem_dados").inc()
                return None

        _t0 = time.perf_counter()
        casos = await self._buscar_casos_similares(indice, tipo_acao)
        _estatistica_duration.observe(time.perf_counter() - _t0)

        favoraveis, desfavoraveis, neutros = (
            self._contar_desfechos(casos, polo_cliente) if casos else (0, 0, 0)
        )
        total_desfechos = favoraveis + desfavoraveis + neutros
        escopo = "tribunal"

        # Fallback: se amostra local insuficiente, consulta top tribunais do mesmo tipo em paralelo
        if total_desfechos < MIN_CASOS_COM_DESFECHO:
            indices_nacionais = self._indices_nacionais(indice)
            if indices_nacionais:
                log.info(
                    "vitoria_preditor_tentando_escopo_nacional",
                    indice_local=indice,
                    qtd_indices=len(indices_nacionais),
                    total_local=total_desfechos,
                )
                _t1 = time.perf_counter()
                resultados_paralelos = await asyncio.gather(
                    *[self._buscar_casos_similares(idx, tipo_acao) for idx in indices_nacionais],
                    return_exceptions=True,
                )
                _estatistica_duration.observe(time.perf_counter() - _t1)

                casos_nacionais: list[dict[str, Any]] = []
                for resultado in resultados_paralelos:
                    if isinstance(resultado, list):
                        casos_nacionais.extend(resultado)

                if casos_nacionais:
                    fav_n, desf_n, neut_n = self._contar_desfechos(casos_nacionais, polo_cliente)
                    total_n = fav_n + desf_n + neut_n
                    if total_n >= MIN_CASOS_COM_DESFECHO:
                        casos = casos_nacionais
                        favoraveis, desfavoraveis, neutros = fav_n, desf_n, neut_n
                        total_desfechos = total_n
                        escopo = "nacional"
                        log.info(
                            "vitoria_preditor_usando_escopo_nacional",
                            total_nacional=total_n,
                            indices_consultados=len(indices_nacionais),
                        )

        if total_desfechos < MIN_CASOS_COM_DESFECHO:
            log.info(
                "vitoria_preditor_amostra_insuficiente",
                total_desfechos=total_desfechos,
                minimo_exigido=MIN_CASOS_COM_DESFECHO,
                escopo_tentado=escopo,
            )
            _estatistica_total.labels(resultado="sem_dados").inc()
            return None

        pct_favoravel = round((favoraveis / total_desfechos) * 100, 1)
        pct_desfavoravel = round((desfavoraveis / total_desfechos) * 100, 1)
        pct_neutro = round(100.0 - pct_favoravel - pct_desfavoravel, 1)

        log.info(
            "vitoria_estatistica_calculada",
            pct_favoravel=pct_favoravel,
            pct_desfavoravel=pct_desfavoravel,
            pct_neutro=pct_neutro,
            total_desfechos=total_desfechos,
            casos_analisados=len(casos),
            escopo=escopo,
        )

        disclaimer = (
            DISCLAIMER_ESTATISTICA if escopo == "tribunal" else DISCLAIMER_ESTATISTICA_NACIONAL
        )

        _estatistica_total.labels(resultado="exibida").inc()
        return EstatisticaProcessual(
            casos_analisados=len(casos),
            casos_com_desfecho=total_desfechos,
            pct_favoravel=pct_favoravel,
            pct_desfavoravel=pct_desfavoravel,
            pct_neutro=pct_neutro,
            confianca=self._calcular_confianca(total_desfechos, escopo),
            tipo_acao=tipo_acao,
            polo_cliente=polo_cliente,
            escopo=escopo,
            disclaimer=disclaimer,
            fatores=self._montar_fatores(
                pct_favoravel,
                pct_desfavoravel,
                pct_neutro,
                total_desfechos,
                polo_cliente,
                tipo_acao,
                escopo,
            ),
        )

    # -----------------------------------------------------------------------
    # Busca tipo_acao diretamente do processo no DataJud
    # -----------------------------------------------------------------------

    async def _buscar_tipo_acao_do_cnj(
        self,
        indice: str,
        numero_cnj: str,
    ) -> str | None:
        numero_limpo = re.sub(r"[.\-]", "", numero_cnj).strip()
        numero_formatado = numero_cnj.strip()

        url = f"{_BASE_URL}/{indice}/_search"
        query: dict[str, Any] = {
            "query": {
                "bool": {
                    "should": [
                        {"match": {"numeroProcesso": numero_formatado}},
                        {"match": {"numeroProcesso": numero_limpo}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "size": 1,
            "_source": ["classe", "assuntos"],
        }

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"ApiKey {self._api_key}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(url, json=query, headers=headers)
                resp.raise_for_status()
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as exc:
                logger.warning("vitoria_preditor_busca_tipo_acao_erro", erro=str(exc))
                return None

        hits = resp.json().get("hits", {}).get("hits", [])
        if not hits:
            return None

        source = hits[0].get("_source", {})

        classe = source.get("classe", {})
        if isinstance(classe, dict) and classe.get("nome"):
            return classe["nome"]

        assuntos = source.get("assuntos", [])
        if assuntos and isinstance(assuntos, list):
            primeiro = assuntos[0]
            if isinstance(primeiro, dict) and primeiro.get("nome"):
                return primeiro["nome"]

        return None

    # -----------------------------------------------------------------------
    # Métodos internos
    # -----------------------------------------------------------------------

    async def _buscar_casos_similares(
        self,
        indice: str,
        tipo_acao: str,
    ) -> list[dict[str, Any]]:
        url = f"{_BASE_URL}/{indice}/_search"
        query: dict[str, Any] = {
            "query": {
                "bool": {
                    "should": [
                        {
                            "match": {
                                "classe.nome": {
                                    "query": tipo_acao,
                                    "fuzziness": "AUTO",
                                }
                            }
                        },
                        {
                            "match": {
                                "assuntos.nome": {
                                    "query": tipo_acao,
                                    "fuzziness": "AUTO",
                                }
                            }
                        },
                    ],
                    "minimum_should_match": 1,
                }
            },
            "size": MAX_CASOS_BUSCA,
            "_source": ["movimentos", "classe", "assuntos"],
        }

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"ApiKey {self._api_key}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(url, json=query, headers=headers)
                resp.raise_for_status()
            except httpx.TimeoutException:
                logger.warning("vitoria_preditor_timeout", indice=indice)
                return []
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "vitoria_preditor_http_erro",
                    indice=indice,
                    status=exc.response.status_code,
                )
                return []
            except httpx.RequestError as exc:
                logger.warning("vitoria_preditor_rede_erro", indice=indice, erro=str(exc))
                return []

        hits = resp.json().get("hits", {}).get("hits", [])
        return [h["_source"] for h in hits if "_source" in h]

    def _contar_desfechos(
        self,
        casos: list[dict[str, Any]],
        polo_cliente: str,
    ) -> tuple[int, int, int]:
        favoraveis = 0
        desfavoraveis = 0
        neutros = 0
        polo_reu = polo_cliente.lower() == "reu"

        for caso in casos:
            movimentos = caso.get("movimentos") or []
            movimentos = sorted(
                movimentos,
                key=lambda m: m.get("dataHora") or "",
                reverse=True,
            )
            for mov in movimentos:
                nome = mov.get("nome", "")
                if not nome:
                    continue

                if self._FAVORAVEL_AUTOR.search(nome):
                    if polo_reu:
                        desfavoraveis += 1
                    else:
                        favoraveis += 1
                    break

                if self._DESFAVORAVEL_AUTOR.search(nome):
                    if polo_reu:
                        favoraveis += 1
                    else:
                        desfavoraveis += 1
                    break

                if self._NEUTRO.search(nome):
                    neutros += 1
                    break

        return favoraveis, desfavoraveis, neutros

    @staticmethod
    def _indices_nacionais(indice: str) -> list[str]:
        if re.match(r"api_publica_tj[a-z]{2}$", indice):
            return [idx for idx in _INDICES_TJ_NACIONAIS if idx != indice]
        if re.match(r"api_publica_trf\d+$", indice):
            return [idx for idx in _INDICES_TRF_NACIONAIS if idx != indice]
        if re.match(r"api_publica_trt\d+$", indice):
            return [idx for idx in _INDICES_TRT_NACIONAIS if idx != indice]
        return []

    @staticmethod
    def _calcular_confianca(total_desfechos: int, escopo: str = "tribunal") -> str:
        if escopo == "nacional":
            if total_desfechos >= 50:
                return "media"
            return "baixa"
        if total_desfechos >= 50:
            return "alta"
        if total_desfechos >= 20:
            return "media"
        return "baixa"

    @staticmethod
    def _montar_fatores(
        pct_favoravel: float,
        pct_desfavoravel: float,
        pct_neutro: float,
        total_desfechos: int,
        polo_cliente: str,
        tipo_acao: str,
        escopo: str = "tribunal",
    ) -> list[str]:
        fatores: list[str] = []

        tipo_curto = tipo_acao[:70] if len(tipo_acao) > 70 else tipo_acao

        if escopo == "nacional":
            fatores.append(
                f"Em {total_desfechos} casos públicos de '{tipo_curto}' com desfecho "
                f"registrado em tribunais brasileiros (escopo nacional — amostra local insuficiente): "
                f"{pct_favoravel}% favoráveis, "
                f"{pct_desfavoravel}% desfavoráveis, "
                f"{pct_neutro}% acordos ou extinções"
            )
        else:
            fatores.append(
                f"Em {total_desfechos} casos públicos de '{tipo_curto}' com desfecho "
                f"registrado no mesmo tribunal: "
                f"{pct_favoravel}% favoráveis, "
                f"{pct_desfavoravel}% desfavoráveis, "
                f"{pct_neutro}% acordos ou extinções"
            )

        if polo_cliente.lower() == "reu":
            fatores.append(
                "Perspectiva ajustada para polo réu "
                "(cliente está sendo processado nesta ação)"
            )

        return fatores


# ---------------------------------------------------------------------------
# Score de Risco Processual (Feature 2)
# ---------------------------------------------------------------------------
# NÃO prevê vitória/derrota (vedado pelo Provimento OAB 205/2021).
# Calcula complexidade/risco operacional para uso interno do advogado.
# O cliente nunca vê este número diretamente.
#
# Fórmula (pesos em shared/config/constants.py → SCORE_RISCO_PESOS):
#   1. Complexidade jurídica  25%  (tipo_acao → SCORE_RISCO_COMPLEXIDADE_POR_TIPO)
#   2. Duração estimada       25%  (DataJud: tempo_medio_tramitacao_dias, normalizado)
#   3. Histórico da vara      20%  (taxa_procedencia_autor do DataJud + polo do cliente)
#   4. Valor da causa         15%  (faixas em salários-mínimos)
#   5. Fase processual atual  15%  (SCORE_RISCO_POR_FASE — risco decresce com avanço)
#
# Performance: cálculo em memória <50ms. DataJud já cacheado pelo cache_manager (TTL 6h).
# ---------------------------------------------------------------------------


class ComponentesScore(BaseModel):
    complexidade_juridica: int = Field(..., ge=0, le=100)
    duracao_estimada: int = Field(..., ge=0, le=100)
    historico_vara: int = Field(..., ge=0, le=100)
    valor_causa: int = Field(..., ge=0, le=100)
    fase_processual: int = Field(..., ge=0, le=100)


class ScoreRisco(BaseModel):
    score: int = Field(..., ge=0, le=100, description="Score global 0–100")
    nivel: str = Field(..., description="baixo | moderado | alto | critico")
    componentes: ComponentesScore
    interpretacao: str = Field(..., description="Texto para o advogado — sem previsão de resultado")
    atualizado_em: datetime


def _normalizar_score(valor: float, minimo: float, maximo: float) -> int:
    if maximo <= minimo:
        return 50
    norm = (valor - minimo) / (maximo - minimo)
    return int(round(max(0.0, min(1.0, norm)) * 100))


def _componente_complexidade(tipo_acao: Optional[str]) -> int:
    if not tipo_acao:
        return 50
    chave = tipo_acao.lower().strip()
    # Busca exata primeiro, depois substring para nomes completos do DataJud
    if chave in SCORE_RISCO_COMPLEXIDADE_POR_TIPO:
        return SCORE_RISCO_COMPLEXIDADE_POR_TIPO[chave]
    for k, v in SCORE_RISCO_COMPLEXIDADE_POR_TIPO.items():
        if k in chave or chave in k:
            return v
    return 50


def _componente_duracao(datajud_data: Optional[dict]) -> int:
    if not datajud_data:
        return 50
    media_dias = datajud_data.get("tempo_medio_tramitacao_dias")
    if media_dias is None:
        return 50
    return _normalizar_score(float(media_dias), 0, SCORE_RISCO_PRAZO_MAX_REFERENCIA)


def _componente_historico_vara(datajud_data: Optional[dict], polo_cliente: Optional[str]) -> int:
    if not datajud_data:
        return 50
    taxa = datajud_data.get("taxa_procedencia_autor")
    if taxa is None:
        return 50
    # Para o réu: risco = taxa de procedência do autor
    # Para o autor: risco = taxa de improcedência
    if polo_cliente and polo_cliente.lower() == "reu":
        return int(round(float(taxa) * 100))
    return int(round((1.0 - float(taxa)) * 100))


def _componente_valor_causa(valor_causa: Optional[float]) -> int:
    if not valor_causa or valor_causa <= 0:
        return 50
    sm = valor_causa / SCORE_RISCO_SALARIO_MINIMO_REF
    if sm < 10:
        return 10
    if sm < 40:
        return 30
    if sm < 100:
        return 55
    if sm < 200:
        return 75
    return 95


def _componente_fase(fase_processual: Optional[str]) -> int:
    if not fase_processual:
        return SCORE_RISCO_POR_FASE.get("conhecimento", 80)
    return SCORE_RISCO_POR_FASE.get(fase_processual.lower(), 50)


def _gerar_interpretacao_score(
    score: int,
    nivel: str,
    componentes: ComponentesScore,
    tipo_acao: Optional[str],
) -> str:
    """
    Texto explicativo para o advogado baseado nos componentes mais altos.
    Não menciona probabilidade de vitória/derrota (compliance OAB).
    """
    tipo_label = (tipo_acao or "processo").replace("_", " ").capitalize()

    cabecalhos = {
        "baixo":    f"{tipo_label} com baixa complexidade operacional.",
        "moderado": f"{tipo_label} com complexidade moderada — acompanhamento padrão recomendado.",
        "alto":     f"{tipo_label} com alta complexidade — atenção redobrada aos prazos.",
        "critico":  f"{tipo_label} com complexidade crítica — revisão estratégica recomendada.",
    }
    partes = [cabecalhos.get(nivel, f"Score de risco: {score}/100.")]

    comp_dict = {
        "complexidade jurídica": componentes.complexidade_juridica,
        "duração estimada":      componentes.duracao_estimada,
        "histórico da vara":     componentes.historico_vara,
        "valor da causa":        componentes.valor_causa,
        "fase processual":       componentes.fase_processual,
    }
    top2 = sorted(comp_dict.items(), key=lambda x: x[1], reverse=True)[:2]
    drivers = " e ".join(f"{nome} ({val}/100)" for nome, val in top2 if val > 50)
    if drivers:
        partes.append(f"Principais fatores: {drivers}.")

    if componentes.duracao_estimada >= 75:
        partes.append(
            "A vara apresenta tempo médio de tramitação elevado — "
            "comunique prazo realista ao cliente."
        )
    elif componentes.duracao_estimada <= 25:
        partes.append("Vara com tramitação ágil — expectativa de prazo abaixo da média.")

    if componentes.valor_causa >= 75:
        partes.append(
            "Valor da causa elevado: documente todas as movimentações com rigor redobrado."
        )

    return " ".join(partes)


class ScoreRiscoCalculator:
    """
    Calcula o ScoreRisco de um processo judicial.

    Uso no worker:
        calc = ScoreRiscoCalculator()
        score = calc.calcular(processo, datajud_data)

    `processo` precisa ter: tipo_acao, valor_causa, fase_processual, polo_cliente
    `datajud_data` é o dict já cacheado pelo cache_manager:
        tempo_medio_tramitacao_dias, taxa_procedencia_autor
    """

    def calcular(self, processo: Any, datajud_data: Optional[dict] = None) -> ScoreRisco:
        tipo_acao       = getattr(processo, "tipo_acao", None)
        valor_causa     = getattr(processo, "valor_causa", None)
        fase_processual = getattr(processo, "fase_processual", None)
        polo_cliente    = getattr(processo, "polo_cliente", None)

        c_complexidade = _componente_complexidade(tipo_acao)
        c_duracao      = _componente_duracao(datajud_data)
        c_historico    = _componente_historico_vara(datajud_data, polo_cliente)
        c_valor        = _componente_valor_causa(float(valor_causa) if valor_causa else None)
        c_fase         = _componente_fase(fase_processual)

        componentes = ComponentesScore(
            complexidade_juridica=c_complexidade,
            duracao_estimada=c_duracao,
            historico_vara=c_historico,
            valor_causa=c_valor,
            fase_processual=c_fase,
        )

        score = int(round(
            c_complexidade * SCORE_RISCO_PESOS["complexidade_juridica"]
            + c_duracao    * SCORE_RISCO_PESOS["duracao_estimada"]
            + c_historico  * SCORE_RISCO_PESOS["historico_vara"]
            + c_valor      * SCORE_RISCO_PESOS["valor_causa"]
            + c_fase       * SCORE_RISCO_PESOS["fase_processual"]
        ))

        if score <= 25:
            nivel = "baixo"
        elif score <= 50:
            nivel = "moderado"
        elif score <= 75:
            nivel = "alto"
        else:
            nivel = "critico"

        return ScoreRisco(
            score=score,
            nivel=nivel,
            componentes=componentes,
            interpretacao=_gerar_interpretacao_score(score, nivel, componentes, tipo_acao),
            atualizado_em=datetime.now(timezone.utc),
        )