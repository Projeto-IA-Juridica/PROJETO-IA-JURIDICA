"""
feature_1_ia_personalizada/services/prospeccao/trackjud_client.py

Cliente para a API Vigilant (TrackJud) — enriquecimento de leads por CPF.

A API busca TODOS os processos de um CPF em tribunais selecionados.
Diferente do DataJud, retorna o campo `partes` completo com nome, tipo e representante.

Base URL: https://vigilant.trackjud.com.br
Docs:     https://vigilant.trackjud.com.br (seção Getting Started)
Créditos: R$ 0,10/tribunal. 5 créditos grátis. Resultados em cache não debitam.

Fluxo por CPF:
  1. POST /api/v1/consults {document: CPF, courts: [...]}
  2a. 200 OK → dados retornados imediatamente (cache hit)
  2b. 202 Accepted → polling GET /api/v1/consults/{id} até status="done"
  3. Extrai partes de cada processo e monta LitiganteEncontrado
  4. Cacheia no Redis por 6h (evita cobranças repetidas para o mesmo CPF)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

import httpx
import structlog

from feature_1_ia_personalizada.services.prospeccao.datajud_prospeccao import (
    LitiganteEncontrado,
)

logger = structlog.get_logger(__name__)

_BASE_URL = "https://vigilant.trackjud.com.br"
_TIMEOUT = 30.0
_POLL_INTERVAL_S = 5.0
_POLL_TIMEOUT_S = 90.0
_CACHE_TTL_S = 60 * 60 * 6  # 6h

# Tribunais padrão quando nenhum é informado (maior volume processual no Brasil)
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

# Sufixos de razão social para inferir pessoa jurídica por heurística
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

# Mapeamento tipo de parte (API) → polo (modelo interno)
_TIPO_PARA_POLO: dict[str, str] = {
    "autor": "ativo",
    "requerente": "ativo",
    "reclamante": "ativo",
    "impetrante": "ativo",
    "apelante": "ativo",
    "reu": "passivo",
    "réu": "passivo",
    "requerido": "passivo",
    "reclamado": "passivo",
    "impetrado": "passivo",
    "apelado": "passivo",
}


class VigilantClient:
    """
    Enriquece leads B2C por CPF via API Vigilant (TrackJud).

    Uso:
        client = VigilantClient(api_key, redis)
        leads = await client.buscar_por_cpf("529.982.247-25", tribunais=["TJSP", "TJMG"])
    """

    def __init__(self, api_key: str | None = None, redis: Any = None) -> None:
        self._api_key = api_key
        self._redis = redis

    # ------------------------------------------------------------------
    # Interface pública
    # ------------------------------------------------------------------

    async def buscar_por_cpf(
        self,
        cpf: str,
        tribunais: list[str] | None = None,
        tipo_acao_filtro: str | None = None,
    ) -> list[LitiganteEncontrado]:
        """
        Retorna litigantes encontrados para o CPF informado.

        Um CPF geralmente tem múltiplos processos; cada processo gera um
        LitiganteEncontrado separado (tipo_acao diferente = lead diferente para o scoring).

        Args:
            cpf: CPF no formato NNN.NNN.NNN-NN ou NNNNNNNNNNN.
            tribunais: Códigos dos tribunais a consultar (ex: ["TJSP", "TRT2"]).
                       None = tribunais padrão cível.
            tipo_acao_filtro: Se informado, filtra processos pelo tipo de ação.
                              None = retorna todos os processos encontrados.

        Sem VIGILANT_API_KEY configurada, retorna lista vazia com aviso de log.
        """
        if not self._api_key:
            logger.warning(
                "vigilant.sem_api_key",
                mensagem="TRACKJUD_API_KEY não configurada — prospecção por CPF indisponível.",
            )
            return []

        courts = tribunais or _TRIBUNAIS_PADRAO_CIVEL
        cache_key = f"vigilant_cpf:{cpf}:{','.join(sorted(courts))}"

        cached = await self._get_cache(cache_key)
        if cached is not None:
            logger.debug("vigilant.cache_hit", cpf=cpf[:3] + "***")
            return cached

        try:
            data = await self._consultar(cpf, courts)
        except Exception as exc:
            logger.error("vigilant.consulta_falhou", cpf=cpf[:3] + "***", error=str(exc))
            return []

        litigantes = self._extrair_litigantes(data, tipo_acao_filtro)

        logger.info(
            "vigilant.busca_concluida",
            cpf=cpf[:3] + "***",
            tribunais=courts,
            processos_encontrados=sum(
                len(court.get("processes", [])) for court in data.get("courts", [])
            ),
            litigantes=len(litigantes),
        )

        await self._set_cache(cache_key, litigantes)
        return litigantes

    async def buscar_multiplos_cpfs(
        self,
        cpfs: list[str],
        tribunais: list[str] | None = None,
        tipo_acao_filtro: str | None = None,
    ) -> list[LitiganteEncontrado]:
        """
        Consulta vários CPFs em paralelo (máx 5 simultâneos para não estourar créditos).
        """
        semaforo = asyncio.Semaphore(5)

        async def _com_semaforo(cpf: str) -> list[LitiganteEncontrado]:
            async with semaforo:
                return await self.buscar_por_cpf(cpf, tribunais, tipo_acao_filtro)

        resultados = await asyncio.gather(
            *[_com_semaforo(cpf) for cpf in cpfs],
            return_exceptions=True,
        )

        litigantes: list[LitiganteEncontrado] = []
        for cpf, res in zip(cpfs, resultados, strict=False):
            if isinstance(res, Exception):
                logger.warning("vigilant.cpf_falhou", cpf=cpf[:3] + "***", error=str(res))
                continue
            if isinstance(res, list):
                litigantes.extend(res)

        return litigantes

    # ------------------------------------------------------------------
    # Internos — ciclo de vida da consulta
    # ------------------------------------------------------------------

    async def _consultar(self, cpf: str, courts: list[str]) -> dict[str, Any]:
        """
        Cria a consulta e aguarda o resultado.
        Retorna o dict `data` da resposta (mesma estrutura para 200 e resultado de polling).
        """
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE_URL}/api/v1/consults",
                headers=self._headers(),
                json={"document": cpf, "courts": courts},
            )

        if resp.status_code == 200:
            # Cache hit — dados imediatos
            return cast(dict[str, Any], resp.json()["data"])

        if resp.status_code == 202:
            # Cache miss — coleta em background, fazer polling
            consult_id = resp.json()["data"]["consult_id"]
            return await self._aguardar_consulta(consult_id)

        if resp.status_code == 402:
            raise RuntimeError(
                "Vigilant: créditos insuficientes. " "Recarregue em https://app.trackjud.com.br."
            )
        if resp.status_code == 422:
            detalhe = resp.json().get("detail", resp.text[:200])
            raise ValueError(f"CPF ou tribunal inválido: {detalhe}")

        resp.raise_for_status()
        return cast(dict[str, Any], resp.json()["data"])  # never reached, raise_for_status acima

    async def _aguardar_consulta(self, consult_id: str) -> dict[str, Any]:
        """
        Polling de GET /api/v1/consults/{id} até status='done' ou timeout.
        API diz: execução típica < 60s.
        """
        deadline = asyncio.get_event_loop().time() + _POLL_TIMEOUT_S

        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(_POLL_INTERVAL_S)

            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"{_BASE_URL}/api/v1/consults/{consult_id}",
                    headers=self._headers(),
                )
            resp.raise_for_status()
            data = cast(dict[str, Any], resp.json()["data"])

            if data.get("status") == "done":
                return data

            if data.get("status") in ("canceled", "failed"):
                raise RuntimeError(
                    f"Consulta Vigilant {consult_id} encerrou com status={data['status']}"
                )

        raise TimeoutError(f"Consulta Vigilant {consult_id} não concluiu em {_POLL_TIMEOUT_S}s")

    # ------------------------------------------------------------------
    # Internos — extração e conversão
    # ------------------------------------------------------------------

    def _extrair_litigantes(
        self,
        data: dict,
        tipo_acao_filtro: str | None,
    ) -> list[LitiganteEncontrado]:
        """
        Converte a resposta da Vigilant em LitiganteEncontrado.

        Estrutura da resposta (campo `data`):
          data.courts[].processes[].partes[] → {nome, tipo, representante}
          data.courts[].processes[].classe   → tipo de ação
          data.courts[].processes[].numero_processo_unico → CNJ
          data.courts[].court                → sigla do tribunal
        """
        # {(nome, tribunal, tipo_acao): {dados acumulados}}
        acumulado: dict[tuple[str, str, str], dict] = {}

        for court_entry in data.get("courts", []):
            tribunal = court_entry.get("court", "")

            for proc in court_entry.get("processes", []):
                tipo_acao = (proc.get("classe") or "").strip()
                numero_cnj = proc.get("numero_processo_unico") or proc.get("numero_processo", "")

                if tipo_acao_filtro and tipo_acao_filtro.lower() not in tipo_acao.lower():
                    continue

                for parte in proc.get("partes", []):
                    nome = (parte.get("nome") or "").strip()
                    if not nome:
                        continue

                    tipo_parte = (parte.get("tipo") or "").lower().strip()
                    polo = _TIPO_PARA_POLO.get(tipo_parte, "ativo")
                    tipo_pessoa = self._inferir_tipo(nome)
                    # `representante` presente e não vazio = tem advogado
                    sem_adv = not bool((parte.get("representante") or "").strip())

                    chave = (nome, tribunal, tipo_acao)
                    if chave not in acumulado:
                        acumulado[chave] = {
                            "nome": nome,
                            "tipo": tipo_pessoa,
                            "polo": polo,
                            "numero_cnj": numero_cnj,
                            "tribunal": tribunal,
                            "tipo_acao": tipo_acao,
                            "sem_advogado": sem_adv,
                            "processos_count": 1,
                        }
                    else:
                        acumulado[chave]["processos_count"] += 1
                        if sem_adv:
                            acumulado[chave]["sem_advogado"] = True

        resultado = [
            LitiganteEncontrado(
                nome=v["nome"],
                tipo=v["tipo"],
                polo=v["polo"],
                processos_count=v["processos_count"],
                numero_cnj_exemplo=v["numero_cnj"],
                tipo_acao=v["tipo_acao"],
                tribunal=v["tribunal"],
                sem_advogado=v["sem_advogado"],
            )
            for v in acumulado.values()
        ]
        # Prioritiza sem advogado, depois por quantidade de processos
        resultado.sort(key=lambda x: (-int(x.sem_advogado), -x.processos_count))
        return resultado

    @staticmethod
    def _inferir_tipo(nome: str) -> str:
        nome_upper = nome.upper()
        if any(s in nome_upper for s in _SUFIXOS_PJ):
            return "pessoa_juridica"
        return "pessoa_fisica"

    # ------------------------------------------------------------------
    # Internos — autenticação e cache
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
            logger.debug("vigilant.cache_schema_error", key=key, error=str(exc))
        except Exception as exc:
            logger.debug("vigilant.cache_erro", key=key, error=str(exc))
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
