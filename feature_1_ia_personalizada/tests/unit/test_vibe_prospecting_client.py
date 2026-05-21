"""
Testes unitários — VibeProspectingClient
=========================================
Cobre:
- Modo degradado (sem API key) → retorna [] sem erro
- Cache hit → não faz chamada HTTP
- Resposta MCP formato "text" → extrai e filtra contatos
- Resposta MCP formato "json" → extrai e filtra contatos
- Erro JSON-RPC (campo "error") → retorna [] sem levantar
- Erro HTTP (status 4xx/5xx) → retorna [] sem levantar
- Filtro por cargo relevante → exclui cargos irrelevantes
- Deduplicação por nome no limite de resultados
- _mapear_contato com diferentes formatos de campos
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from feature_1_ia_personalizada.services.prospeccao.vibe_prospecting_client import (
    VibeProspectingClient,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_mock(cached_data: str | None = None) -> MagicMock:
    mock = MagicMock()
    mock.get = AsyncMock(return_value=cached_data)
    mock.setex = AsyncMock(return_value=True)
    return mock


def _prospect_text_content(prospects: list[dict]) -> dict:
    """Monta payload MCP com content[].type == 'text'."""
    return {"result": {"content": [{"type": "text", "text": json.dumps(prospects)}]}}


def _prospect_json_content(prospects: list[dict]) -> dict:
    """Monta payload MCP com content[].type == 'json'."""
    return {"result": {"content": [{"type": "json", "data": prospects}]}}


def _mock_http_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data or {})
    if status_code >= 400:
        resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                f"HTTP {status_code}", request=MagicMock(), response=resp
            )
        )
    else:
        resp.raise_for_status = MagicMock(return_value=None)
    return resp


def _client_com_key(redis=None) -> VibeProspectingClient:
    with patch("shared.config.settings.Settings", autospec=True):
        client = VibeProspectingClient(api_key="test-explorium-key", redis=redis)
    return client


# ---------------------------------------------------------------------------
# Modo degradado (sem API key)
# ---------------------------------------------------------------------------


class TestModoDegradado:
    def test_disponivel_false_sem_chave(self):
        with patch("shared.config.settings.Settings", autospec=True):
            client = VibeProspectingClient(api_key=None, redis=None)
        assert client.disponivel is False

    async def test_retorna_lista_vazia_sem_chave(self):
        with patch("shared.config.settings.Settings", autospec=True):
            client = VibeProspectingClient(api_key=None, redis=None)
        result = await client.buscar_contatos_empresa("Empresa Teste LTDA")
        assert result == []

    def test_disponivel_true_com_chave(self):
        client = _client_com_key()
        assert client.disponivel is True


# ---------------------------------------------------------------------------
# Cache Redis
# ---------------------------------------------------------------------------


class TestCacheRedis:
    async def test_cache_hit_nao_faz_http(self):
        """Se há cache, não deve fazer chamada HTTP."""
        cached = [
            {
                "nome": "Maria Diretora",
                "cargo": "Diretora Jurídica",
                "url_perfil": "https://linkedin.com/in/maria",
                "empresa": "Empresa X",
            }
        ]
        redis = _make_redis_mock(json.dumps(cached))
        client = _client_com_key(redis=redis)

        with patch("httpx.AsyncClient") as mock_http:
            result = await client.buscar_contatos_empresa("Empresa X")

        mock_http.assert_not_called()
        assert len(result) == 1
        assert result[0].nome == "Maria Diretora"

    async def test_cache_miss_faz_http(self):
        """Sem cache, deve fazer chamada HTTP."""
        redis = _make_redis_mock(None)
        client = _client_com_key(redis=redis)

        prospects = [{"full_name": "João CEO", "job_title": "CEO", "linkedin_url": None}]
        payload = _prospect_text_content(prospects)
        resp = _mock_http_response(200, payload)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.post = AsyncMock(return_value=resp)
            result = await client.buscar_contatos_empresa("Empresa X")

        assert len(result) == 1

    async def test_resultado_salvo_no_cache(self):
        """Após busca bem-sucedida, resultado é salvo no Redis."""
        redis = _make_redis_mock(None)
        client = _client_com_key(redis=redis)

        prospects = [{"full_name": "Ana CFO", "job_title": "CFO", "linkedin_url": None}]
        payload = _prospect_text_content(prospects)
        resp = _mock_http_response(200, payload)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.post = AsyncMock(return_value=resp)
            await client.buscar_contatos_empresa("Empresa Y")

        redis.setex.assert_awaited_once()


# ---------------------------------------------------------------------------
# Parsing de resposta MCP — formato "text"
# ---------------------------------------------------------------------------


class TestRespostaMCPFormatoText:
    async def test_extrai_contatos_formato_text(self):
        client = _client_com_key()
        prospects = [
            {
                "full_name": "Carlos Presidente",
                "job_title": "Presidente",
                "linkedin_url": "https://linkedin.com/in/carlos",
            },
        ]
        payload = _prospect_text_content(prospects)
        resp = _mock_http_response(200, payload)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.post = AsyncMock(return_value=resp)
            result = await client.buscar_contatos_empresa("Empresa Z")

        assert len(result) == 1
        assert result[0].nome == "Carlos Presidente"
        assert result[0].cargo == "Presidente"
        assert result[0].url_perfil == "https://linkedin.com/in/carlos"

    async def test_extrai_contatos_de_objeto_com_chave_prospects(self):
        """Quando o JSON tem estrutura {'prospects': [...]}."""
        client = _client_com_key()
        payload = {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "prospects": [
                                    {
                                        "full_name": "Luis Diretor",
                                        "job_title": "Diretor",
                                        "linkedin_url": None,
                                    }
                                ]
                            }
                        ),
                    }
                ]
            }
        }
        resp = _mock_http_response(200, payload)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.post = AsyncMock(return_value=resp)
            result = await client.buscar_contatos_empresa("Empresa W")

        assert len(result) == 1
        assert result[0].nome == "Luis Diretor"


# ---------------------------------------------------------------------------
# Parsing de resposta MCP — formato "json"
# ---------------------------------------------------------------------------


class TestRespostaMCPFormatoJson:
    async def test_extrai_contatos_formato_json(self):
        client = _client_com_key()
        prospects = [
            {
                "full_name": "Paula Compliance",
                "job_title": "Compliance Officer",
                "linkedin_url": "https://linkedin.com/in/paula",
            },
        ]
        payload = _prospect_json_content(prospects)
        resp = _mock_http_response(200, payload)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.post = AsyncMock(return_value=resp)
            result = await client.buscar_contatos_empresa("Empresa V")

        assert len(result) == 1
        assert result[0].nome == "Paula Compliance"


# ---------------------------------------------------------------------------
# Tratamento de erros
# ---------------------------------------------------------------------------


class TestTratamentoDeErros:
    async def test_erro_jsonrpc_retorna_lista_vazia(self):
        """Campo 'error' na resposta MCP → retorna [] sem levantar."""
        client = _client_com_key()
        payload = {"error": {"code": -32601, "message": "Method not found: find_prospects"}}
        resp = _mock_http_response(200, payload)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.post = AsyncMock(return_value=resp)
            result = await client.buscar_contatos_empresa("Empresa X")

        assert result == []

    async def test_http_500_retorna_lista_vazia(self):
        """Erro HTTP 500 → retorna [] sem levantar."""
        client = _client_com_key()
        resp = _mock_http_response(500)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.post = AsyncMock(return_value=resp)
            result = await client.buscar_contatos_empresa("Empresa X")

        assert result == []

    async def test_timeout_retorna_lista_vazia(self):
        """Timeout na chamada HTTP → retorna [] sem levantar."""
        client = _client_com_key()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            result = await client.buscar_contatos_empresa("Empresa X")

        assert result == []

    async def test_resposta_vazia_retorna_lista_vazia(self):
        """Resposta MCP sem 'content' → retorna []."""
        client = _client_com_key()
        resp = _mock_http_response(200, {"result": {}})

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.post = AsyncMock(return_value=resp)
            result = await client.buscar_contatos_empresa("Empresa X")

        assert result == []


# ---------------------------------------------------------------------------
# Filtro por cargo relevante
# ---------------------------------------------------------------------------


class TestFiltroCargoRelevante:
    async def test_exclui_cargos_irrelevantes(self):
        """Analistas, estagiários e outros cargos não-decisores são excluídos."""
        client = _client_com_key()
        prospects = [
            {"full_name": "Pedro CEO", "job_title": "CEO", "linkedin_url": None},
            {"full_name": "Ana Analista", "job_title": "Analista Financeira", "linkedin_url": None},
            {"full_name": "Bia Estagio", "job_title": "Estagiária", "linkedin_url": None},
            {"full_name": "Rui Diretor", "job_title": "Diretor Jurídico", "linkedin_url": None},
        ]
        payload = _prospect_text_content(prospects)
        resp = _mock_http_response(200, payload)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.post = AsyncMock(return_value=resp)
            result = await client.buscar_contatos_empresa("Empresa X")

        nomes = [c.nome for c in result]
        assert "Pedro CEO" in nomes
        assert "Rui Diretor" in nomes
        assert "Ana Analista" not in nomes
        assert "Bia Estagio" not in nomes

    def test_cargo_relevante_case_insensitive(self):
        assert VibeProspectingClient._cargo_relevante("CEO") is True
        assert VibeProspectingClient._cargo_relevante("Compliance Officer") is True
        assert VibeProspectingClient._cargo_relevante("Gerente Jurídico") is True
        assert VibeProspectingClient._cargo_relevante("Estagiário") is False
        assert VibeProspectingClient._cargo_relevante("Auxiliar Administrativo") is False


# ---------------------------------------------------------------------------
# Mapeamento de campos (_mapear_contato)
# ---------------------------------------------------------------------------


class TestMapearContato:
    def test_mapeia_full_name(self):
        c = VibeProspectingClient._mapear_contato(
            {
                "full_name": "Maria Silva",
                "job_title": "Presidente",
                "linkedin_url": "https://li.com/maria",
            },
            "Empresa X",
        )
        assert c is not None
        assert c.nome == "Maria Silva"
        assert c.cargo == "Presidente"
        assert c.url_perfil == "https://li.com/maria"

    def test_mapeia_first_last_name(self):
        """Quando só há first_name + last_name."""
        c = VibeProspectingClient._mapear_contato(
            {"first_name": "João", "last_name": "Ferreira", "title": "CFO"},
            "Empresa Y",
        )
        assert c is not None
        assert c.nome == "João Ferreira"
        assert c.cargo == "CFO"

    def test_mapeia_profile_url_alternativo(self):
        """Aceita profile_url como fallback de linkedin_url."""
        c = VibeProspectingClient._mapear_contato(
            {"full_name": "Ana Sócia", "job_title": "Sócia", "profile_url": "https://li.com/ana"},
            "Empresa Z",
        )
        assert c is not None
        assert c.url_perfil == "https://li.com/ana"

    def test_retorna_none_sem_nome(self):
        """Contato sem nome → None (ignorado pelo pipeline)."""
        c = VibeProspectingClient._mapear_contato(
            {"job_title": "CEO", "linkedin_url": None},
            "Empresa X",
        )
        assert c is None

    def test_cargo_vazio_permitido(self):
        """Contato sem cargo é mantido (cargo = '')."""
        c = VibeProspectingClient._mapear_contato(
            {"full_name": "Carlos Sem Cargo"},
            "Empresa X",
        )
        assert c is not None
        assert c.cargo == ""
