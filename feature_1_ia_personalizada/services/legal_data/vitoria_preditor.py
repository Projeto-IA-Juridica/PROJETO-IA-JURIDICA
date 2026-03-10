# feature_1_ia_personalizada/services/legal_data/vitoria_preditor.py
"""
VitoriaPreditor — Contexto histórico de casos similares via DataJud (CNJ).

ATENÇÃO — Compliance OAB:
  Este módulo NÃO calcula "probabilidade de vitória" nem faz predições.
  Ele coleta e apresenta estatísticas de desfecho de CASOS PÚBLICOS SIMILARES
  para fornecer contexto informativo ao cliente, sem constituir opinião jurídica.

  A IA nunca deve converter esses dados em promessa de resultado.
  O FactChecker possui padrões específicos para bloquear esse tipo de framing.

Regra de exibição:
  Retorna EstatisticaProcessual apenas quando há dados suficientes
  (>= MIN_CASOS_COM_DESFECHO). O critério é QUALIDADE DA AMOSTRA, não o resultado.
  Nenhum gate por percentual é aplicado — exibir 40% é tão válido quanto 80%.
  A decisão de interpretar os dados é do cliente com seu advogado(a).

Fluxo:
  1. Deriva o índice ElasticSearch a partir do número CNJ
  2. Busca casos com mesma classe/tipo de ação no mesmo tribunal (DataJud)
  3. Classifica movimentos em: favorável_autor | desfavorável_autor | neutro
  4. Ajusta perspectiva para polo do cliente (autor ou réu)
  5. Retorna EstatisticaProcessual (com todos os percentuais) ou None
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
from prometheus_client import Counter, Histogram

from feature_1_ia_personalizada.services.legal_data.datajud_client import (
    DataJudClientError,
    _indice_para_cnj,  # função interna reutilizada — mesma lógica CNJ
)

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api-publica.datajud.cnj.jus.br"

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

# Mínimo de casos com desfecho claro para exibir (gate de qualidade da amostra)
# Abaixo disso, retorna None — dados insuficientes para ser informativo
MIN_CASOS_COM_DESFECHO: int = 10

# Máximo de casos similares buscados por consulta
MAX_CASOS_BUSCA: int = 100

# Disclaimer obrigatório — sempre incluído na resposta ao cliente
DISCLAIMER_ESTATISTICA = (
    "Estes são dados históricos de processos públicos similares, "
    "obtidos do DataJud (CNJ). Não representam previsão de resultado "
    "para o seu caso. Cada processo é único. Converse com seu advogado(a) "
    "para uma análise personalizada."
)

# ---------------------------------------------------------------------------
# Métricas Prometheus
# ---------------------------------------------------------------------------

_estatistica_total = Counter(
    "vitoria_estatistica_total",
    "Total de consultas de estatísticas processuais",
    labelnames=["resultado"],  # "exibida" | "sem_dados"
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
    """
    Contexto histórico de casos similares públicos.

    NÃO é uma predição de resultado. É um recorte estatístico de
    desfechos registrados no DataJud para casos com perfil similar.

    Atributos:
        casos_analisados:   Total de casos encontrados no DataJud
        casos_com_desfecho: Casos com movimentação de desfecho claro
        pct_favoravel:      % com desfecho favorável ao polo do cliente (0–100)
        pct_desfavoravel:   % com desfecho desfavorável ao polo do cliente (0–100)
        pct_neutro:         % com desfecho neutro (acordo, extinção sem mérito etc.)
        confianca:          "alta" (≥50) | "media" (≥20) | "baixa" (≥10)
        tipo_acao:          Tipo de ação usado na busca
        polo_cliente:       Polo do cliente (autor | reu | terceiro)
        disclaimer:         Texto de aviso obrigatório (compliance OAB)
        fatores:            Frases explicativas para incluir na mensagem
    """

    casos_analisados: int
    casos_com_desfecho: int
    pct_favoravel: float
    pct_desfavoravel: float
    pct_neutro: float
    confianca: str
    tipo_acao: str
    polo_cliente: str
    disclaimer: str = field(default=DISCLAIMER_ESTATISTICA)
    fatores: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Preditor
# ---------------------------------------------------------------------------


class VitoriaPreditor:
    """
    Consulta DataJud para coletar contexto histórico de casos similares.

    Uso:
        preditor = VitoriaPreditor(api_key=settings.DATAJUD_API_KEY)
        resultado = await preditor.buscar_estatistica(
            numero_cnj="0000001-23.2021.8.26.0001",
            tipo_acao="Ação de Indenização por Dano Moral",
            polo_cliente="autor",
        )
        if resultado:
            # Amostra suficiente — seguro apresentar como contexto ao cliente
    """

    # Desfecho FAVORÁVEL ao autor (procedência / concessão)
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

    # Desfecho DESFAVORÁVEL ao autor (improcedência / indeferimento)
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

    # Desfecho NEUTRO (acordo, extinção sem mérito, arquivamento)
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
        """
        Busca contexto histórico de casos similares no DataJud.

        Retorna EstatisticaProcessual quando a amostra é suficiente
        (>= MIN_CASOS_COM_DESFECHO), ou None quando:
          - tipo_acao não disponível
          - CNJ inválido ou tribunal não mapeado
          - Amostra insuficiente de casos com desfecho claro

        Nenhum gate por percentual é aplicado — resultado é exibido
        independente do valor calculado.

        Args:
            numero_cnj:   Número CNJ formatado (ex: 0000001-23.2021.8.26.0001)
            tipo_acao:    Tipo/classe da ação (ex: "Ação de Indenização por Dano Moral")
            polo_cliente: "autor" | "reu" | "terceiro"
        """
        log = logger.bind(cnj=numero_cnj, polo=polo_cliente)

        if not tipo_acao or not tipo_acao.strip():
            log.info("vitoria_preditor_sem_tipo_acao")
            _estatistica_total.labels(resultado="sem_dados").inc()
            return None

        try:
            indice = _indice_para_cnj(numero_cnj)
        except DataJudClientError as exc:
            log.warning("vitoria_preditor_cnj_invalido", erro=str(exc))
            _estatistica_total.labels(resultado="sem_dados").inc()
            return None

        # perf_counter manual: prometheus_client.Histogram.time() é síncrono e infla
        # a métrica com latência ociosa do event loop em carga alta.
        _t0 = time.perf_counter()
        casos = await self._buscar_casos_similares(indice, tipo_acao)
        _estatistica_duration.observe(time.perf_counter() - _t0)

        if not casos:
            log.info("vitoria_preditor_sem_casos", tipo_acao=tipo_acao)
            _estatistica_total.labels(resultado="sem_dados").inc()
            return None

        favoraveis, desfavoraveis, neutros = self._contar_desfechos(casos, polo_cliente)
        total_desfechos = favoraveis + desfavoraveis + neutros

        if total_desfechos < MIN_CASOS_COM_DESFECHO:
            log.info(
                "vitoria_preditor_amostra_insuficiente",
                total_desfechos=total_desfechos,
                minimo_exigido=MIN_CASOS_COM_DESFECHO,
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
        )

        _estatistica_total.labels(resultado="exibida").inc()
        return EstatisticaProcessual(
            casos_analisados=len(casos),
            casos_com_desfecho=total_desfechos,
            pct_favoravel=pct_favoravel,
            pct_desfavoravel=pct_desfavoravel,
            pct_neutro=pct_neutro,
            confianca=self._calcular_confianca(total_desfechos),
            tipo_acao=tipo_acao,
            polo_cliente=polo_cliente,
            fatores=self._montar_fatores(
                pct_favoravel,
                pct_desfavoravel,
                pct_neutro,
                total_desfechos,
                polo_cliente,
                tipo_acao,
            ),
        )

    # -----------------------------------------------------------------------
    # Métodos internos
    # -----------------------------------------------------------------------

    async def _buscar_casos_similares(
        self,
        indice: str,
        tipo_acao: str,
    ) -> list[dict[str, Any]]:
        """
        Consulta DataJud por casos com mesma classe ou assunto no mesmo tribunal.

        Usa fuzzy matching para tolerar variações de escrita
        (ex: "Dano Moral" vs "Indenização por Dano Moral").
        """
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
        """
        Percorre movimentos de cada caso classificando desfechos.

        Retorna: (favoraveis, desfavoraveis, neutros) do ponto de vista do cliente.

        Regra de polo:
          - "autor" → procedência = favorável, improcedência = desfavorável
          - "reu"   → improcedência = favorável, procedência = desfavorável
          - outros  → tratados como autor

        Considera apenas o primeiro movimento com desfecho claro por caso.
        """
        favoraveis = 0
        desfavoraveis = 0
        neutros = 0
        polo_reu = polo_cliente.lower() == "reu"

        for caso in casos:
            movimentos = caso.get("movimentos") or []
            # DataJud não garante ordem cronológica — ordenamos decrescente por dataHora
            # para que o break capture o desfecho mais recente (após eventuais recursos),
            # não a sentença original de 1ª instância.
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
    def _calcular_confianca(total_desfechos: int) -> str:
        """Alta: ≥50 casos | Media: ≥20 | Baixa: ≥10."""
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
    ) -> list[str]:
        """Gera frases humanizadas para compor a mensagem ao cliente."""
        fatores: list[str] = []

        tipo_curto = tipo_acao[:70] if len(tipo_acao) > 70 else tipo_acao
        fatores.append(
            f"Em {total_desfechos} casos públicos de '{tipo_curto}' com desfecho registrado: "
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
