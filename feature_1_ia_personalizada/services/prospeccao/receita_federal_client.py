"""
feature_1_ia_personalizada/services/prospeccao/receita_federal_client.py

Client para a API pública ReceitaWS — dados de CNPJ sem chave de API.

Endpoint: https://receitaws.com.br/v1/cnpj/{cnpj}
Rate limit: ~3 req/min no plano gratuito.

Comportamento em falha: sempre retorna None (graceful degradation).
O fluxo de prospecção continua com os dados que tiver — Receita falhar
não quebra a busca no DataJud nem no LinkedIn.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from shared.utils.validators import normalizar_cnpj, validar_cnpj

logger = structlog.get_logger(__name__)

_BASE_URL = "https://receitaws.com.br/v1/cnpj"
_TIMEOUT_S = 10
_MAX_RETRIES = 2
_RETRY_BACKOFF_S = 1
_RATE_LIMIT_WAIT_S = 60
_CACHE_TTL_S = 60 * 60 * 24  # 24h — dados cadastrais raramente mudam


@dataclass
class EmpresaDados:
    """Dados normalizados retornados pela ReceitaWS."""

    cnpj: str
    razao_social: str
    nome_fantasia: str | None
    situacao: str          # ATIVA | BAIXADA | SUSPENSA | INAPTA | NULA
    porte: str             # MEI | ME | EPP | DEMAIS
    cnae_codigo: str       # código numérico (ex: "6911-7/01")
    cnae_descricao: str    # descrição textual
    uf: str
    municipio: str
    socios: list[dict[str, Any]] = field(default_factory=list)
    # [{nome, qualificacao, data_entrada}]


class ReceitaFederalClient:
    """
    Busca dados de CNPJ na API pública ReceitaWS.

    Uso:
        async with ReceitaFederalClient(redis) as client:
            dados = await client.buscar_cnpj("11.222.333/0001-81")

    Ou sem context manager (sem fechar o httpx explicitamente):
        client = ReceitaFederalClient(redis)
        dados = await client.buscar_cnpj(cnpj)
        await client.aclose()
    """

    def __init__(self, redis: Any) -> None:
        """
        Args:
            redis: instância de redis.asyncio.Redis para cache.
                   Aceita None — nesse caso opera sem cache (sem erro).
        """
        self._redis = redis
        self._http = httpx.AsyncClient(timeout=_TIMEOUT_S)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> ReceitaFederalClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Interface pública
    # ------------------------------------------------------------------

    async def buscar_cnpj(self, cnpj: str) -> EmpresaDados | None:
        """
        Retorna dados da empresa ou None se não encontrada / erro.

        Ordem de resolução:
          1. Cache Redis (TTL 24h)
          2. ReceitaWS API (com retry e tratamento de rate limit)
        """
        cnpj_limpo = normalizar_cnpj(cnpj)

        if not validar_cnpj(cnpj_limpo):
            logger.warning("receita.cnpj_invalido", cnpj=cnpj)
            return None

        # 1. Tentar cache
        cached = await self._get_cache(cnpj_limpo)
        if cached is not None:
            logger.debug("receita.cache_hit", cnpj=cnpj_limpo)
            return cached

        # 2. Chamar API
        dados = await self._fetch(cnpj_limpo)
        if dados is not None:
            await self._set_cache(cnpj_limpo, dados)

        return dados

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    async def _fetch(self, cnpj: str) -> EmpresaDados | None:
        """Chama ReceitaWS com retry e tratamento de rate limit."""
        url = f"{_BASE_URL}/{cnpj}"

        for attempt in range(1, _MAX_RETRIES + 2):  # 1, 2, 3
            try:
                resp = await self._http.get(url)
            except httpx.RequestError as exc:
                logger.warning(
                    "receita.request_error",
                    cnpj=cnpj,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt <= _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF_S * attempt)
                    continue
                return None

            if resp.status_code == 200:
                logger.info("receita.ok", cnpj=cnpj, attempt=attempt)
                return self._parse(resp.json(), cnpj)

            if resp.status_code == 429:
                logger.warning("receita.rate_limit", cnpj=cnpj, attempt=attempt)
                if attempt <= _MAX_RETRIES:
                    await asyncio.sleep(_RATE_LIMIT_WAIT_S)
                    continue
                return None

            if resp.status_code == 404:
                logger.info("receita.nao_encontrado", cnpj=cnpj)
                return None

            # 4xx/5xx inesperado — não tentar novamente
            logger.warning(
                "receita.erro_http",
                cnpj=cnpj,
                status=resp.status_code,
            )
            return None

        return None

    @staticmethod
    def _parse(data: dict[str, Any], cnpj: str) -> EmpresaDados | None:
        """Normaliza o JSON da ReceitaWS para EmpresaDados."""
        # ReceitaWS retorna {"status": "ERROR", "message": "..."} para CNPJs inválidos
        if data.get("status") == "ERROR":
            return None

        atividade = data.get("atividade_principal", [{}])
        cnae_principal = atividade[0] if atividade else {}

        socios_raw = data.get("qsa", [])
        socios = [
            {
                "nome": s.get("nome", ""),
                "qualificacao": s.get("qual", ""),
                "data_entrada": s.get("data_entrada", ""),
            }
            for s in socios_raw
        ]

        return EmpresaDados(
            cnpj=cnpj,
            razao_social=data.get("nome", ""),
            nome_fantasia=data.get("fantasia") or None,
            situacao=data.get("situacao", ""),
            porte=data.get("porte", "DEMAIS"),
            cnae_codigo=cnae_principal.get("code", ""),
            cnae_descricao=cnae_principal.get("text", ""),
            uf=data.get("uf", ""),
            municipio=data.get("municipio", ""),
            socios=socios,
        )

    async def _get_cache(self, cnpj: str) -> EmpresaDados | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(f"receita:{cnpj}")
            if raw:
                return EmpresaDados(**json.loads(raw))
        except (TypeError, KeyError) as exc:
            # Schema de EmpresaDados mudou — entrada stale no cache.
            # Retorna None para forçar nova chamada à API e sobrescrever.
            logger.debug(
                "receita.cache_parse_error",
                cnpj=cnpj,
                error=str(exc),
            )
        except Exception as exc:
            logger.debug("receita.cache_error", cnpj=cnpj, error=str(exc))
        return None

    async def _set_cache(self, cnpj: str, dados: EmpresaDados) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.setex(
                f"receita:{cnpj}",
                _CACHE_TTL_S,
                json.dumps(dados.__dict__),
            )
        except Exception:
            pass  # cache é best-effort
