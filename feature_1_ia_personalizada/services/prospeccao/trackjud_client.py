"""
feature_1_ia_personalizada/services/prospeccao/trackjud_client.py

Busca leads por tipo de ação no TrackJud — substitui o DataJudProspeccaoClient
como motor de descoberta da Feature 3.

Diferença fundamental em relação ao DataJud público:
  - DataJud: campo `partes` nunca presente nos documentos (LGPD/CNJ)
  - TrackJud: retorna partes completas (nome, polo, tipo de pessoa, advogados)

Documentação: https://docs.trackjud.com.br
Plano pay-per-use: R$ 0,10 por tribunal consultado; 5 créditos grátis.

Fluxo:
  1. Resolve tribunal(is) a consultar (aceita sigla única ou padrão por ramo).
  2. Busca em paralelo nos tribunais resolvidos.
  3. Extrai partes de cada processo retornado.
  4. Deduplica por nome, acumulando contagem de processos.
  5. Ordena priorizando partes sem advogado (necessidade mais imediata).
  6. Cacheia resultado no Redis por 6h (evita cobranças repetidas).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from feature_1_ia_personalizada.services.prospeccao.datajud_prospeccao import (
    LitiganteEncontrado,
)

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.trackjud.com.br"
_TIMEOUT = 25.0
_CACHE_TTL_S = 60 * 60 * 6  # 6h

# --------------------------------------------------------------------------
# Tribunais suportados pelo TrackJud (12 fontes, 10 estados no plano básico)
# Atualizar conforme cobertura do plano contratado.
# Ref: https://docs.trackjud.com.br/tribunais
# --------------------------------------------------------------------------

_TRIBUNAIS_SUPORTADOS: frozenset[str] = frozenset(
    {
        # TJs com maior volume processual
        "TJSP", "TJRJ", "TJMG", "TJRS", "TJPR", "TJSC", "TJBA", "TJCE", "TJGO",
        # TRTs principais
        "TRT1", "TRT2", "TRT3", "TRT4", "TRT9", "TRT15",
        # TRFs
        "TRF1", "TRF2", "TRF3", "TRF4",
    }
)

_TRIBUNAIS_PADRAO_CIVEL = ["TJSP", "TJRJ", "TJMG", "TJRS", "TJPR"]
_TRIBUNAIS_PADRAO_TRABALHISTA = ["TRT2", "TRT4", "TRT3", "TRT1", "TRT9"]

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
        "LTDA", "S.A.", "S/A", "S.A ", " SA", " ME", "ME ", "EPP", "EIRELI",
        "ASSOCIAÇÃO", "FUNDAÇÃO", "INSTITUTO", "CONDOMÍNIO", "COOPERATIVA",
        "BANCO ", "SEGURADORA", "CONSTRUTORA", "INCORPORADORA",
        "DISTRIBUIDORA", "TRANSPORTADORA",
    }
)


# --------------------------------------------------------------------------
# Cliente
# --------------------------------------------------------------------------


class TrackJudProspeccaoClient:
    """
    Busca litigantes por tipo de ação via API TrackJud.

    Interface idêntica ao DataJudProspeccaoClient — drop-in replacement.

    Uso:
        client = TrackJudProspeccaoClient(api_key, redis)
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

        Se tribunal=None, busca em paralelo nos tribunais padrão do ramo.
        Deduplica por nome — mesmo litigante em múltiplos processos conta
        uma vez, mas acumula processos_count.

        Sem TRACKJUD_API_KEY configurada, retorna lista vazia com log de aviso.
        """
        if not self._api_key:
            logger.warning(
                "trackjud.sem_api_key",
                mensagem="TRACKJUD_API_KEY não configurada — prospecção indisponível. "
                "Adicione a variável de ambiente e reinicie.",
            )
            return []

        cache_key = f"trackjud_prosp:{tipo_acao}:{tribunal or 'padrao'}"
        cached = await self._get_cache(cache_key)
        if cached is not None:
            logger.debug("trackjud.cache_hit", tipo_acao=tipo_acao, tribunal=tribunal)
            return cached

        tribunais = self._resolver_tribunais(tipo_acao, tribunal)
        if not tribunais:
            return []

        tasks = [self._buscar_em_tribunal(tipo_acao, t, limite) for t in tribunais]
        resultados = await asyncio.gather(*tasks, return_exceptions=True)

        brutos: list[dict] = []
        for trib, res in zip(tribunais, resultados, strict=False):
            if isinstance(res, Exception):
                logger.warning("trackjud.tribunal_erro", tribunal=trib, error=str(res))
                continue
            if isinstance(res, list):
                brutos.extend(res)

        logger.info(
            "trackjud.busca_concluida",
            tipo_acao=tipo_acao,
            tribunal=tribunal,
            brutos=len(brutos),
        )

        deduplicados = self._deduplicar(brutos, tipo_acao)[:limite]
        await self._set_cache(cache_key, deduplicados)
        return deduplicados

    # ------------------------------------------------------------------
    # Internos — resolução de tribunais
    # ------------------------------------------------------------------

    def _resolver_tribunais(self, tipo_acao: str, tribunal: str | None) -> list[str]:
        if tribunal is not None:
            sigla = tribunal.upper()
            if sigla not in _TRIBUNAIS_SUPORTADOS:
                logger.warning("trackjud.tribunal_nao_suportado", tribunal=sigla)
                return []
            return [sigla]

        tipo_lower = tipo_acao.lower()
        if any(p in tipo_lower for p in _PALAVRAS_TRABALHISTA):
            return list(_TRIBUNAIS_PADRAO_TRABALHISTA)
        return list(_TRIBUNAIS_PADRAO_CIVEL)

    # ------------------------------------------------------------------
    # Internos — chamada à API TrackJud
    # ------------------------------------------------------------------

    async def _buscar_em_tribunal(
        self,
        tipo_acao: str,
        tribunal: str,
        limite: int,
    ) -> list[dict]:
        """
        POST /v1/processos/buscar

        Body esperado:
          {
            "classe": "<tipo de ação>",
            "tribunal": "<sigla>",
            "pagina": 1,
            "por_pagina": <limite * 3>
          }

        Resposta esperada:
          {
            "total": <int>,
            "processos": [
              {
                "numero": "<CNJ>",
                "tribunal": "<sigla>",
                "classe": "<nome>",
                "partes": [
                  {
                    "nome": "<string>",
                    "polo": "ATIVO"|"PASSIVO",
                    "tipo": "PESSOA_JURIDICA"|"PESSOA_FISICA",
                    "advogados": ["OAB ..."]
                  }
                ]
              }
            ]
          }

        Ajuste os campos acima conforme a documentação oficial recebida ao cadastrar.
        """
        url = f"{_BASE_URL}/v1/processos/buscar"
        payload = {
            "classe": tipo_acao,
            "tribunal": tribunal,
            "pagina": 1,
            "por_pagina": min(limite * 3, 100),
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=self._headers())

        if resp.status_code == 402:
            raise RuntimeError(
                f"TrackJud: créditos insuficientes para consultar {tribunal}. "
                "Recarregue créditos em https://app.trackjud.com.br."
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"TrackJud HTTP {resp.status_code} ({tribunal}): {resp.text[:200]}"
            )

        data = resp.json()
        processos = data.get("processos", [])

        litigantes: list[dict] = []
        for proc in processos:
            numero_cnj = proc.get("numero", "")
            tribunal_sigla = proc.get("tribunal", tribunal)

            for parte in proc.get("partes", []):
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
        tipo_api = (parte.get("tipo") or "").upper()
        if "JURIDICA" in tipo_api or "PJ" == tipo_api:
            return "pessoa_juridica"
        if "FISICA" in tipo_api or "PF" == tipo_api:
            return "pessoa_fisica"

        nome_upper = nome.upper()
        if any(s in nome_upper for s in _SUFIXOS_PJ):
            return "pessoa_juridica"
        return "pessoa_fisica"

    # ------------------------------------------------------------------
    # Internos — deduplicação (idêntica ao DataJudProspeccaoClient)
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicar(brutos: list[dict], tipo_acao: str) -> list[LitiganteEncontrado]:
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
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

    async def _get_cache(self, key: str) -> list[LitiganteEncontrado] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw:
                items = json.loads(raw)
                return [LitiganteEncontrado(**item) for item in items]
        except (TypeError, KeyError) as exc:
            logger.debug("trackjud.cache_schema_error", key=key, error=str(exc))
        except Exception as exc:
            logger.debug("trackjud.cache_erro", key=key, error=str(exc))
        return None

    async def _set_cache(self, key: str, litigantes: list[LitiganteEncontrado]) -> None:
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
