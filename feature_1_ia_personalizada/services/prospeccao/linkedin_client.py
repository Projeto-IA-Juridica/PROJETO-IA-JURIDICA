"""
feature_1_ia_personalizada/services/prospeccao/linkedin_client.py

Client para a LinkedIn API — People Search / Company Employees.

IMPORTANTE: requer aprovação no LinkedIn Partner Program para uso em produção.
Enquanto as credenciais não estiverem configuradas (LINKEDIN_CLIENT_ID +
LINKEDIN_CLIENT_SECRET no .env), o client opera em modo degradado:
  - disponivel = False
  - buscar_funcionarios() retorna [] sem erro nem warning repetitivo

Quando aprovado, o fluxo OAuth 2.0 é:
  1. POST /oauth/v2/accessToken → token de aplicativo (client_credentials)
  2. GET /v2/search (People Search) filtrando por empresa
  3. Cache do token até expiração; cache de resultados por empresa (TTL 7 dias)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from shared.config.settings import settings

logger = structlog.get_logger(__name__)

_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_SEARCH_URL = "https://api.linkedin.com/v2/search"
_TIMEOUT_S = 15
_CACHE_TTL_FUNCIONARIOS_S = 60 * 60 * 24 * 7  # 7 dias
_CACHE_TTL_TOKEN_S = 60 * 60 * 23  # 23h (token válido por 24h)
_MAX_CONTATOS_POR_EMPRESA = 10

# Cargos com maior probabilidade de decisão jurídica ou interesse em contratar advocacia
_CARGOS_RELEVANTES = frozenset(
    {
        "ceo",
        "cfo",
        "coo",
        "presidente",
        "vice-presidente",
        "diretor",
        "diretora",
        "gerente jurídico",
        "gerente juridico",
        "compliance",
        "general counsel",
        "advogado",
        "advogada",
        "jurídico",
        "juridico",
        "sócio",
        "socio",
        "partner",
        "head of legal",
        "legal",
        "counsel",
    }
)


@dataclass
class ContatoLinkedIn:
    nome: str
    cargo: str
    url_perfil: str | None
    empresa: str


class LinkedInClient:
    """
    Wrapper para a LinkedIn API com fallback gracioso quando sem credenciais.

    Uso:
        client = LinkedInClient(redis)
        if client.disponivel:
            contatos = await client.buscar_funcionarios("Empresa ABC")
        # ou simplesmente:
        contatos = await client.buscar_funcionarios("Empresa ABC")
        # retorna [] automaticamente se indisponível
    """

    def __init__(self, redis: Any) -> None:
        self._redis = redis
        self._disponivel = bool(settings.LINKEDIN_CLIENT_ID and settings.LINKEDIN_CLIENT_SECRET)
        self._http = httpx.AsyncClient(timeout=_TIMEOUT_S)

        if not self._disponivel:
            logger.debug(
                "linkedin.modo_degradado",
                motivo="LINKEDIN_CLIENT_ID ou LINKEDIN_CLIENT_SECRET ausentes",
            )

    @property
    def disponivel(self) -> bool:
        return self._disponivel

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> LinkedInClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Interface pública
    # ------------------------------------------------------------------

    async def buscar_funcionarios(
        self,
        empresa_nome: str,
        empresa_linkedin_id: str | None = None,
    ) -> list[ContatoLinkedIn]:
        """
        Retorna até 10 contatos relevantes da empresa.
        Retorna [] sem erro se LinkedIn indisponível ou em qualquer falha.
        """
        if not self._disponivel:
            return []

        cache_key = f"linkedin:{empresa_linkedin_id or empresa_nome.lower()}"
        cached = await self._get_cache(cache_key)
        if cached is not None:
            logger.debug("linkedin.cache_hit", empresa=empresa_nome)
            return cached

        try:
            token = await self._obter_token()
            if token is None:
                return []

            contatos = await self._buscar(token, empresa_nome, empresa_linkedin_id)
            await self._set_cache(cache_key, contatos)
            logger.info(
                "linkedin.ok",
                empresa=empresa_nome,
                total=len(contatos),
            )
            return contatos

        except Exception as exc:
            # Nunca vazar exceção para o chamador — LinkedIn é opcional
            logger.warning(
                "linkedin.erro",
                empresa=empresa_nome,
                error=str(exc),
            )
            return []

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    async def _obter_token(self) -> str | None:
        """Obtém token OAuth2 client_credentials, com cache Redis."""
        cache_key = "linkedin:access_token"

        if self._redis is not None:
            try:
                token = await self._redis.get(cache_key)
                if token:
                    return token
            except Exception:
                pass

        try:
            resp = await self._http.post(
                _TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.LINKEDIN_CLIENT_ID,
                    "client_secret": settings.LINKEDIN_CLIENT_SECRET,
                },
            )
            if resp.status_code != 200:
                logger.warning("linkedin.token_erro", status=resp.status_code)
                return None

            token = resp.json().get("access_token")
            if token and self._redis is not None:
                try:
                    await self._redis.setex(cache_key, _CACHE_TTL_TOKEN_S, token)
                except Exception:
                    pass
            return token

        except Exception as exc:
            logger.warning("linkedin.token_request_error", error=str(exc))
            return None

    async def _buscar(
        self,
        token: str,
        empresa_nome: str,
        empresa_id: str | None,
    ) -> list[ContatoLinkedIn]:
        """Chama LinkedIn People Search e filtra cargos relevantes."""
        params: dict[str, Any] = {
            "q": "peopleSearch",
            "keywords": empresa_nome,
            "count": 25,  # busca mais para filtrar por cargo depois
        }
        if empresa_id:
            params["facetCurrentCompany"] = empresa_id

        resp = await self._http.get(
            _SEARCH_URL,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )

        if resp.status_code == 401:
            # Token expirou — limpa cache e sinaliza para reobtter
            if self._redis is not None:
                try:
                    await self._redis.delete("linkedin:access_token")
                except Exception:
                    pass
            logger.warning("linkedin.token_expirado")
            return []

        if resp.status_code != 200:
            logger.warning("linkedin.search_erro", status=resp.status_code)
            return []

        elementos = resp.json().get("elements", [])
        contatos: list[ContatoLinkedIn] = []

        for elem in elementos:
            cargo = elem.get("headline", "").lower()
            if not self._cargo_relevante(cargo):
                continue

            contatos.append(
                ContatoLinkedIn(
                    nome=elem.get("title", {}).get("text", ""),
                    cargo=elem.get("headline", ""),
                    url_perfil=elem.get("navigationUrl"),
                    empresa=empresa_nome,
                )
            )
            if len(contatos) >= _MAX_CONTATOS_POR_EMPRESA:
                break

        return contatos

    @staticmethod
    def _cargo_relevante(cargo_lower: str) -> bool:
        # Intencionalmente permissivo (substring match):
        # preferimos falso positivo a falso negativo neste contexto —
        # é melhor incluir um contato a mais do que perder um decisor.
        # Ex: "legal" casa com "paralegal" (ok para prospecção).
        return any(termo in cargo_lower for termo in _CARGOS_RELEVANTES)

    async def _get_cache(self, key: str) -> list[ContatoLinkedIn] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw:
                return [ContatoLinkedIn(**c) for c in json.loads(raw)]
        except (TypeError, KeyError) as exc:
            logger.debug("linkedin.cache_parse_error", key=key, error=str(exc))
        except Exception as exc:
            logger.debug("linkedin.cache_error", key=key, error=str(exc))
        return None

    async def _set_cache(self, key: str, contatos: list[ContatoLinkedIn]) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.setex(
                key,
                _CACHE_TTL_FUNCIONARIOS_S,
                json.dumps([c.__dict__ for c in contatos]),
            )
        except Exception:
            pass
