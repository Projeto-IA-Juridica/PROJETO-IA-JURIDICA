"""
feature_1_ia_personalizada/services/prospeccao/datajud_prospeccao.py

Busca leads por tipo de ação no DataJud — o motor de descoberta da Feature 3.

Diferente do DataJudClient (que busca pelo número CNJ), este cliente busca
*quem está litigando* em determinado tipo de ação, retornando litigantes como
potenciais leads de prospecção.

Fluxo:
  1. Resolve o(s) índice(s) ElasticSearch pelo tribunal informado (ou padrão).
  2. Busca em paralelo com query `match` em classe.nome / assuntos.nome.
  3. Extrai as partes de cada processo (polo, tipo pessoa, advogados).
  4. Deduplica por nome, acumulando contagem de processos.
  5. Ordena priorizando partes sem advogado (necessidade mais imediata).
  6. Cacheia resultado no Redis por 6h.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api-publica.datajud.cnj.jus.br"
_TIMEOUT = 20.0
_CACHE_TTL_S = 60 * 60 * 6  # 6h

# --------------------------------------------------------------------------
# Mapeamento sigla → índice ElasticSearch
# --------------------------------------------------------------------------

_SIGLA_TO_INDICE: dict[str, str] = {
    # TJs estaduais
    "TJSP": "api_publica_tjsp",
    "TJRJ": "api_publica_tjrj",
    "TJMG": "api_publica_tjmg",
    "TJRS": "api_publica_tjrs",
    "TJPR": "api_publica_tjpr",
    "TJSC": "api_publica_tjsc",
    "TJBA": "api_publica_tjba",
    "TJCE": "api_publica_tjce",
    "TJGO": "api_publica_tjgo",
    "TJPE": "api_publica_tjpe",
    "TJAM": "api_publica_tjam",
    "TJDF": "api_publica_tjdf",
    "TJMT": "api_publica_tjmt",
    "TJMS": "api_publica_tjms",
    "TJPA": "api_publica_tjpa",
    "TJPB": "api_publica_tjpb",
    "TJES": "api_publica_tjes",
    "TJAL": "api_publica_tjal",
    "TJPI": "api_publica_tjpi",
    "TJRN": "api_publica_tjrn",
    "TJRO": "api_publica_tjro",
    "TJRR": "api_publica_tjrr",
    "TJSE": "api_publica_tjse",
    "TJAC": "api_publica_tjac",
    "TJAP": "api_publica_tjap",
    "TJTO": "api_publica_tjto",
    "TJMA": "api_publica_tjma",
    # TRTs (1–24)
    **{f"TRT{i}": f"api_publica_trt{i}" for i in range(1, 25)},
    # TRFs
    "TRF1": "api_publica_trf1",
    "TRF2": "api_publica_trf2",
    "TRF3": "api_publica_trf3",
    "TRF4": "api_publica_trf4",
    "TRF5": "api_publica_trf5",
    "TRF6": "api_publica_trf6",
    # Superiores
    "TST": "api_publica_tst",
    "STJ": "api_publica_stj",
    "STF": "api_publica_stf",
}

# Padrão quando tribunal=None: 5 mais ativos por ramo
_INDICES_PADRAO_CIVEL = [
    "api_publica_tjsp",
    "api_publica_tjrj",
    "api_publica_tjmg",
    "api_publica_tjrs",
    "api_publica_tjpr",
]
_INDICES_PADRAO_TRABALHISTA = [
    "api_publica_trt2",  # SP
    "api_publica_trt4",  # RS
    "api_publica_trt3",  # MG
    "api_publica_trt1",  # RJ
    "api_publica_trt9",  # PR
]

_PALAVRAS_TRABALHISTA = frozenset(
    {
        "trabalhista",
        "reclamação trabalhista",
        "trt",
        "empregado",
        "rescisão contratual",
        "horas extras",
        "verbas rescisórias",
    }
)

# Sufixos que indicam pessoa jurídica (heurística de fallback)
_SUFIXOS_PJ = frozenset(
    {
        "LTDA",
        "S.A.",
        "S/A",
        "S.A ",
        " SA",
        " ME",
        "ME ",
        "EPP",
        "EIRELI",
        "ASSOCIAÇÃO",
        "FUNDAÇÃO",
        "INSTITUTO",
        "CONDOMÍNIO",
        "COOPERATIVA",
        "BANCO ",
        "SEGURADORA",
        "CONSTRUTORA",
        "INCORPORADORA",
        "DISTRIBUIDORA",
        "TRANSPORTADORA",
    }
)


# --------------------------------------------------------------------------
# Dataclass de resultado
# --------------------------------------------------------------------------


@dataclass
class LitiganteEncontrado:
    nome: str
    tipo: str                 # 'pessoa_juridica' | 'pessoa_fisica'
    polo: str                 # 'ativo' | 'passivo'
    processos_count: int      # quantas vezes aparece nos resultados
    numero_cnj_exemplo: str   # um CNJ representativo para contexto
    tipo_acao: str
    tribunal: str
    # True quando nenhum advogado foi listado para essa parte —
    # indica necessidade jurídica imediata; prioridade de prospecção.
    sem_advogado: bool = False


# --------------------------------------------------------------------------
# Cliente
# --------------------------------------------------------------------------


class DataJudProspeccaoClient:
    """
    Busca litigantes por tipo de ação no DataJud.

    Uso:
        client = DataJudProspeccaoClient(api_key, redis)
        leads = await client.buscar_litigantes("reclamação trabalhista", tribunal="TRT2")
    """

    def __init__(self, api_key: str | None = None, redis: Any = None) -> None:
        self._api_key = api_key
        self._redis = redis

    # ------------------------------------------------------------------
    # Interface pública
    # ------------------------------------------------------------------

    async def buscar_litigantes(
        self,
        tipo_acao: str,
        tribunal: str | None = None,
        limite: int = 20,
        tipo_lead: str | None = None,
    ) -> list[LitiganteEncontrado]:
        """
        Retorna lista de litigantes encontrados em processos do tipo_acao.

        Se tribunal=None, busca em paralelo nos 5 tribunais padrão do ramo.
        Deduplica por nome — mesmo litigante em múltiplos processos conta
        uma vez, mas acumula processos_count.
        """
        cache_key = f"datajud_prosp:{tipo_acao}:{tribunal or 'padrao'}"
        cached = await self._get_cache(cache_key)
        if cached is not None:
            logger.debug(
                "datajud_prosp.cache_hit",
                tipo_acao=tipo_acao,
                tribunal=tribunal,
            )
            return cached

        indices = self._resolver_indices(tipo_acao, tribunal)
        if not indices:
            return []

        tasks = [
            self._buscar_em_indice(tipo_acao, indice, limite)
            for indice in indices
        ]
        resultados = await asyncio.gather(*tasks, return_exceptions=True)

        brutos: list[dict] = []
        for indice, res in zip(indices, resultados, strict=False):
            if isinstance(res, Exception):
                logger.warning(
                    "datajud_prosp.indice_erro",
                    indice=indice,
                    error=str(res),
                )
                continue
            brutos.extend(res)

        logger.info(
            "datajud_prosp.busca_concluida",
            tipo_acao=tipo_acao,
            tribunal=tribunal,
            brutos=len(brutos),
        )

        deduplicados = self._deduplicar(brutos, tipo_acao)[:limite]
        await self._set_cache(cache_key, deduplicados)
        return deduplicados

    # ------------------------------------------------------------------
    # Internos — resolução de índices
    # ------------------------------------------------------------------

    def _resolver_indices(self, tipo_acao: str, tribunal: str | None) -> list[str]:
        if tribunal is not None:
            indice = _SIGLA_TO_INDICE.get(tribunal.upper())
            if not indice:
                logger.warning(
                    "datajud_prosp.tribunal_desconhecido",
                    tribunal=tribunal,
                )
                return []
            return [indice]

        tipo_lower = tipo_acao.lower()
        if any(p in tipo_lower for p in _PALAVRAS_TRABALHISTA):
            return list(_INDICES_PADRAO_TRABALHISTA)
        return list(_INDICES_PADRAO_CIVEL)

    # ------------------------------------------------------------------
    # Internos — query ElasticSearch
    # ------------------------------------------------------------------

    async def _buscar_em_indice(
        self,
        tipo_acao: str,
        indice: str,
        limite: int,
    ) -> list[dict]:
        url = f"{_BASE_URL}/{indice}/_search"
        query = {
            # Busca 3× o limite para ter margem após deduplicação
            "size": min(limite * 3, 100),
            "query": {
                "bool": {
                    "should": [
                        {"match": {"classe.nome": tipo_acao}},
                        {"match": {"assuntos.nome": tipo_acao}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "_source": [
                "numeroProcesso",
                "classe.nome",
                "tribunal.sigla",
                "partes",
            ],
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=query, headers=self._headers())

        if resp.status_code != 200:
            raise RuntimeError(
                f"DataJud HTTP {resp.status_code} ({indice}): {resp.text[:200]}"
            )

        hits = resp.json().get("hits", {}).get("hits", [])
        # Sigla de fallback quando o tribunal não consta no _source
        sigla_fallback = indice.replace("api_publica_", "").upper()

        litigantes: list[dict] = []
        for hit in hits:
            source = hit.get("_source", {})
            numero_cnj = source.get("numeroProcesso", "")
            tribunal_sigla = (
                source.get("tribunal", {}).get("sigla") or sigla_fallback
            )

            for parte in source.get("partes", []):
                nome = (parte.get("nome") or "").strip()
                if not nome:
                    continue
                polo = (parte.get("polo") or "").lower()
                tipo = self._inferir_tipo_parte(nome, parte)
                sem_adv = not bool(parte.get("advogados"))

                litigantes.append(
                    {
                        "nome": nome,
                        "tipo": tipo,
                        "polo": polo,
                        "numero_cnj": numero_cnj,
                        "tribunal": tribunal_sigla,
                        "sem_advogado": sem_adv,
                    }
                )

        return litigantes

    # ------------------------------------------------------------------
    # Internos — classificação de parte
    # ------------------------------------------------------------------

    @staticmethod
    def _inferir_tipo_parte(nome: str, parte: dict) -> str:
        """
        Infere pessoa_juridica ou pessoa_fisica.

        Ordem de preferência:
          1. Campo tipoPessoa do DataJud (quando presente)
          2. Heurística por sufixo corporativo no nome
          3. Padrão: pessoa_fisica
        """
        tipo_api = (parte.get("tipoPessoa") or "").lower()
        if "jurídica" in tipo_api or "juridica" in tipo_api or tipo_api == "pj":
            return "pessoa_juridica"
        if "física" in tipo_api or "fisica" in tipo_api or tipo_api == "pf":
            return "pessoa_fisica"

        nome_upper = nome.upper()
        if any(s in nome_upper for s in _SUFIXOS_PJ):
            return "pessoa_juridica"
        return "pessoa_fisica"

    # ------------------------------------------------------------------
    # Internos — deduplicação
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicar(
        brutos: list[dict], tipo_acao: str
    ) -> list[LitiganteEncontrado]:
        """
        Agrupa por nome, acumula processos_count.
        Ordena: sem_advogado=True primeiro, depois por processos_count desc.
        """
        acumulado: dict[str, dict] = {}
        for lit in brutos:
            nome = lit["nome"]
            if nome not in acumulado:
                acumulado[nome] = {**lit, "processos_count": 1}
            else:
                acumulado[nome]["processos_count"] += 1
                if lit["sem_advogado"]:
                    acumulado[nome]["sem_advogado"] = True

        resultado = [
            LitiganteEncontrado(
                nome=v["nome"],
                tipo=v["tipo"],
                polo=v["polo"],
                processos_count=v["processos_count"],
                numero_cnj_exemplo=v["numero_cnj"],
                tipo_acao=tipo_acao,
                tribunal=v["tribunal"],
                sem_advogado=v["sem_advogado"],
            )
            for v in acumulado.values()
        ]
        resultado.sort(key=lambda x: (-int(x.sem_advogado), -x.processos_count))
        return resultado

    # ------------------------------------------------------------------
    # Internos — cache
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"ApiKey {self._api_key}"
        return h

    async def _get_cache(self, key: str) -> list[LitiganteEncontrado] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw:
                items = json.loads(raw)
                return [LitiganteEncontrado(**item) for item in items]
        except (TypeError, KeyError) as exc:
            logger.debug(
                "datajud_prosp.cache_schema_error",
                key=key,
                error=str(exc),
            )
        except Exception as exc:
            logger.debug(
                "datajud_prosp.cache_erro",
                key=key,
                error=str(exc),
            )
        return None

    async def _set_cache(
        self, key: str, litigantes: list[LitiganteEncontrado]
    ) -> None:
        if self._redis is None:
            return
        try:
            payload = [
                {
                    "nome": lit.nome,
                    "tipo": lit.tipo,
                    "polo": lit.polo,
                    "processos_count": lit.processos_count,
                    "numero_cnj_exemplo": lit.numero_cnj_exemplo,
                    "tipo_acao": lit.tipo_acao,
                    "tribunal": lit.tribunal,
                    "sem_advogado": lit.sem_advogado,
                }
                for lit in litigantes
            ]
            await self._redis.setex(
                key,
                _CACHE_TTL_S,
                json.dumps(payload, ensure_ascii=False),
            )
        except Exception:
            pass
