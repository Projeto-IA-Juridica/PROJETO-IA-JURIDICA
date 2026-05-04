"""
feature_1_ia_personalizada/services/prospeccao/vibe_prospecting_client.py

Client para o Vibe Prospecting (Explorium AgentSource) — inteligência B2B
para encontrar decisores e contatos de empresas via protocolo MCP.

Preenche o gap da F3.4: contatos LinkedIn + decisores, sem depender do
LinkedIn Partner Program.

Retorna ContatoLinkedIn para manter total compatibilidade com o pipeline
existente (EmpresaIntelligenceService, MatchingService, score +15).

Fallback gracioso: sem EXPLORIUM_API_KEY → disponivel=False → retorna [].
Cache Redis 7 dias (mesmo TTL que LinkedInClient).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from feature_1_ia_personalizada.services.prospeccao.linkedin_client import ContatoLinkedIn

logger = structlog.get_logger(__name__)

_MCP_URL = "https://mcp.explorium.ai/mcp"
_TIMEOUT = 30.0
_CACHE_TTL_S = 60 * 60 * 24 * 7  # 7 dias
_MAX_CONTATOS = 10

_CARGOS_RELEVANTES = frozenset({
    "ceo", "presidente", "vice-presidente", "diretor", "diretora",
    "cfo", "coo", "general counsel", "head of legal",
    "advogado", "advogada", "jurídico", "juridico",
    "compliance", "legal", "counsel", "sócio", "socio", "partner",
})


class VibeProspectingClient:
    """
    Client para o Explorium AgentSource via protocolo MCP (JSON-RPC 2.0).

    Uso:
        client = VibeProspectingClient(redis=redis)
        if client.disponivel:
            contatos = await client.buscar_contatos_empresa("Empresa XYZ")
        # retorna [] automaticamente se indisponível ou em qualquer falha
    """

    def __init__(self, api_key: str | None = None, redis: Any = None) -> None:
        from shared.config.settings import settings

        self._api_key = api_key or getattr(settings, "EXPLORIUM_API_KEY", None)
        self._redis = redis
        self._disponivel = bool(self._api_key)

        if not self._disponivel:
            logger.debug(
                "vibe_prospecting.modo_degradado",
                motivo="EXPLORIUM_API_KEY ausente",
            )

    @property
    def disponivel(self) -> bool:
        return self._disponivel

    async def buscar_contatos_empresa(
        self,
        nome_empresa: str,
        pais: str = "BR",
        limite: int = _MAX_CONTATOS,
    ) -> list[ContatoLinkedIn]:
        """
        Retorna até `limite` decisores e contatos relevantes da empresa.
        Retorna [] sem erro se indisponível ou em qualquer falha.
        """
        if not self._disponivel:
            return []

        cache_key = f"vibe:{nome_empresa.lower()}:{pais}"
        cached = await self._get_cache(cache_key)
        if cached is not None:
            logger.debug("vibe_prospecting.cache_hit", empresa=nome_empresa)
            return cached

        try:
            contatos = await self._buscar(nome_empresa, pais, limite)
            await self._set_cache(cache_key, contatos)
            logger.info(
                "vibe_prospecting.ok",
                empresa=nome_empresa,
                pais=pais,
                total=len(contatos),
            )
            return contatos
        except Exception as exc:
            logger.warning(
                "vibe_prospecting.erro",
                empresa=nome_empresa,
                error=str(exc),
            )
            return []

    # ------------------------------------------------------------------
    # Internos — chamada MCP
    # ------------------------------------------------------------------

    async def _buscar(
        self, nome_empresa: str, pais: str, limite: int
    ) -> list[ContatoLinkedIn]:
        headers = {
            "Content-Type": "application/json",
            "api_key": self._api_key,
        }

        # Busca 2× o limite para ter margem após filtro por cargo
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "find_prospects",
                "arguments": {
                    "company_name": nome_empresa,
                    "country_code": pais,
                    "limit": min(limite * 2, 50),
                },
            },
            "id": 1,
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(_MCP_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise RuntimeError(
                f"MCP error {data['error'].get('code', '')}: "
                f"{data['error'].get('message', data['error'])}"
            )

        return self._extrair_contatos(data.get("result", {}), nome_empresa, limite)

    def _extrair_contatos(
        self, resultado: dict, empresa: str, limite: int
    ) -> list[ContatoLinkedIn]:
        """
        Extrai contatos do resultado MCP.

        O servidor pode retornar em dois formatos:
          - content[].type == "text"  → texto JSON com lista de prospects
          - content[].type == "json"  → objeto estruturado diretamente
        """
        contatos: list[ContatoLinkedIn] = []
        content = resultado.get("content", [])

        for item in content:
            tipo = item.get("type", "")

            if tipo == "text":
                try:
                    parsed = json.loads(item.get("text", "[]"))
                    prospects = (
                        parsed
                        if isinstance(parsed, list)
                        else parsed.get("prospects", [])
                    )
                    for p in prospects:
                        c = self._mapear_contato(p, empresa)
                        if c:
                            contatos.append(c)
                except (json.JSONDecodeError, TypeError):
                    continue

            elif tipo in ("json", "resource"):
                prospects = item.get("data") or item.get("prospects", [])
                if isinstance(prospects, list):
                    for p in prospects:
                        c = self._mapear_contato(p, empresa)
                        if c:
                            contatos.append(c)

        relevantes = [c for c in contatos if self._cargo_relevante(c.cargo)]
        return relevantes[:limite]

    @staticmethod
    def _mapear_contato(data: dict, empresa: str) -> ContatoLinkedIn | None:
        """Mapeia um prospect Explorium para ContatoLinkedIn."""
        nome = (
            data.get("full_name")
            or data.get("name")
            or (
                f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
            )
        )
        if not nome:
            return None

        cargo = (
            data.get("job_title")
            or data.get("title")
            or data.get("current_role")
            or ""
        )
        linkedin_url = (
            data.get("linkedin_url")
            or data.get("profile_url")
            or data.get("linkedin_profile")
        )

        return ContatoLinkedIn(
            nome=nome,
            cargo=cargo,
            url_perfil=linkedin_url,
            empresa=empresa,
        )

    @staticmethod
    def _cargo_relevante(cargo: str) -> bool:
        cargo_lower = cargo.lower()
        return any(termo in cargo_lower for termo in _CARGOS_RELEVANTES)

    # ------------------------------------------------------------------
    # Internos — cache
    # ------------------------------------------------------------------

    async def _get_cache(self, key: str) -> list[ContatoLinkedIn] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw:
                return [ContatoLinkedIn(**c) for c in json.loads(raw)]
        except (TypeError, KeyError) as exc:
            logger.debug("vibe_prospecting.cache_parse_error", key=key, error=str(exc))
        except Exception as exc:
            logger.debug("vibe_prospecting.cache_erro", key=key, error=str(exc))
        return None

    async def _set_cache(self, key: str, contatos: list[ContatoLinkedIn]) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.setex(
                key,
                _CACHE_TTL_S,
                json.dumps([c.__dict__ for c in contatos]),
            )
        except Exception:
            pass
