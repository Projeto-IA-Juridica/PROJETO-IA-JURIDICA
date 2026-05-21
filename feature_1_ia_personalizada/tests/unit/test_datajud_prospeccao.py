"""
Testes unitários — DataJudProspeccaoClient
==========================================
Verifica que:
- Busca por tipo_acao retorna litigantes como LitiganteEncontrado
- Deduplicação agrupa mesmo litigante em múltiplos processos
- sem_advogado=True tem prioridade na ordenação
- Tribunal trabalhista → índices TRT; cível → índices TJ
- Tribunal desconhecido → retorna lista vazia
- Cache Redis é utilizado quando disponível
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.prospeccao.datajud_prospeccao import (
    DataJudProspeccaoClient,
    LitiganteEncontrado,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hit(
    nome: str,
    polo: str = "ativo",
    tipo: str | None = None,
    numero: str = "0001234-56.2024.5.02.0100",
    tem_advogado: bool = False,
    tribunal: str = "TRT2",
) -> dict:
    """Cria um hit simulando a estrutura retornada pelo DataJud ES."""
    return {
        "_source": {
            "numeroProcesso": numero,
            "classe": {"nome": "Reclamação Trabalhista"},
            "tribunal": {"sigla": tribunal},
            "partes": [
                {
                    "nome": nome,
                    "polo": polo,
                    "tipoPessoa": tipo or ("PJ" if "LTDA" in nome else "PF"),
                    "advogados": [{"nome": "Dr. X"}] if tem_advogado else [],
                }
            ],
        }
    }


def _make_http_mock(hits: list[dict]) -> MagicMock:
    """Mock do httpx.AsyncClient retornando os hits especificados."""
    resp_mock = MagicMock()
    resp_mock.status_code = 200
    resp_mock.json.return_value = {"hits": {"hits": hits, "total": {"value": len(hits)}}}

    http_mock = AsyncMock()
    http_mock.post = AsyncMock(return_value=resp_mock)
    http_mock.__aenter__ = AsyncMock(return_value=http_mock)
    http_mock.__aexit__ = AsyncMock(return_value=None)
    return http_mock


# ---------------------------------------------------------------------------
# Resolução de índices
# ---------------------------------------------------------------------------


class TestResolucaoIndices:
    def test_trabalhista_resolve_trt(self):
        client = DataJudProspeccaoClient()
        indices = client._resolver_indices("reclamação trabalhista", None)
        assert all("trt" in i for i in indices)

    def test_civel_resolve_tj(self):
        client = DataJudProspeccaoClient()
        indices = client._resolver_indices("ação de divórcio", None)
        assert all("tj" in i for i in indices)

    def test_tribunal_especifico_retorna_unico_indice(self):
        client = DataJudProspeccaoClient()
        indices = client._resolver_indices("qualquer", "TRT2")
        assert indices == ["api_publica_trt2"]

    def test_tribunal_desconhecido_retorna_vazio(self):
        client = DataJudProspeccaoClient()
        indices = client._resolver_indices("qualquer", "TRIBUNAL_INVALIDO")
        assert indices == []


# ---------------------------------------------------------------------------
# Deduplicação
# ---------------------------------------------------------------------------


class TestDeduplicacao:
    def test_mesmo_litigante_acumula_processos_count(self):
        brutos = [
            {
                "nome": "João Silva",
                "tipo": "pessoa_fisica",
                "polo": "ativo",
                "numero_cnj": "001",
                "tribunal": "TRT2",
                "sem_advogado": True,
            },
            {
                "nome": "João Silva",
                "tipo": "pessoa_fisica",
                "polo": "ativo",
                "numero_cnj": "002",
                "tribunal": "TRT2",
                "sem_advogado": False,
            },
            {
                "nome": "Maria Costa",
                "tipo": "pessoa_fisica",
                "polo": "ativo",
                "numero_cnj": "003",
                "tribunal": "TRT2",
                "sem_advogado": False,
            },
        ]
        resultado = DataJudProspeccaoClient._deduplicar(brutos, "trabalhista")

        joao = next(r for r in resultado if r.nome == "João Silva")
        assert joao.processos_count == 2
        # Se qualquer aparição tem sem_advogado=True, o registro final deve ser True
        assert joao.sem_advogado is True

        assert len(resultado) == 2  # João e Maria, sem duplicata

    def test_sem_advogado_vem_primeiro(self):
        brutos = [
            {
                "nome": "Empresa A",
                "tipo": "pessoa_juridica",
                "polo": "passivo",
                "numero_cnj": "001",
                "tribunal": "TRT2",
                "sem_advogado": False,
            },
            {
                "nome": "Empresa B",
                "tipo": "pessoa_juridica",
                "polo": "passivo",
                "numero_cnj": "002",
                "tribunal": "TRT2",
                "sem_advogado": True,
            },
        ]
        resultado = DataJudProspeccaoClient._deduplicar(brutos, "trabalhista")

        assert resultado[0].nome == "Empresa B"  # sem_advogado=True vem primeiro


# ---------------------------------------------------------------------------
# buscar_litigantes — integração com HTTP mock
# ---------------------------------------------------------------------------


class TestBuscarLitigantes:
    @pytest.mark.asyncio
    async def test_retorna_litigantes_com_http_mock(self):
        hits = [
            _hit("EMPRESA TESTE LTDA", polo="passivo", tipo="PJ"),
            _hit("João Operário", polo="ativo", tipo="PF"),
        ]
        http_mock = _make_http_mock(hits)

        client = DataJudProspeccaoClient(api_key=None, redis=None)
        with patch(
            "feature_1_ia_personalizada.services.prospeccao.datajud_prospeccao.httpx.AsyncClient",
            return_value=http_mock,
        ):
            resultado = await client.buscar_litigantes(
                tipo_acao="reclamação trabalhista",
                tribunal="TRT2",
                limite=20,
            )

        assert len(resultado) == 2
        nomes = {r.nome for r in resultado}
        assert "EMPRESA TESTE LTDA" in nomes
        assert "João Operário" in nomes

    @pytest.mark.asyncio
    async def test_tribunal_desconhecido_retorna_lista_vazia(self):
        client = DataJudProspeccaoClient(api_key=None, redis=None)
        resultado = await client.buscar_litigantes(
            tipo_acao="divórcio",
            tribunal="TRIBUNAL_XYZ",
            limite=10,
        )
        assert resultado == []

    @pytest.mark.asyncio
    async def test_http_error_retorna_lista_vazia(self):
        """Erro HTTP em todos os índices deve retornar lista vazia sem exceção."""
        http_mock = AsyncMock()
        http_mock.post = AsyncMock(side_effect=Exception("Conexão recusada"))
        http_mock.__aenter__ = AsyncMock(return_value=http_mock)
        http_mock.__aexit__ = AsyncMock(return_value=None)

        client = DataJudProspeccaoClient(api_key=None, redis=None)
        with patch(
            "feature_1_ia_personalizada.services.prospeccao.datajud_prospeccao.httpx.AsyncClient",
            return_value=http_mock,
        ):
            resultado = await client.buscar_litigantes(
                tipo_acao="reclamação trabalhista",
                tribunal="TRT2",
                limite=10,
            )

        assert resultado == []

    @pytest.mark.asyncio
    async def test_cache_hit_nao_chama_http(self):
        """Com cache Redis válido, HTTP não é chamado."""
        litigante_cached = LitiganteEncontrado(
            nome="Empresa Cached LTDA",
            tipo="pessoa_juridica",
            polo="passivo",
            processos_count=3,
            numero_cnj_exemplo="0001234-56.2024.5.02.0100",
            tipo_acao="Reclamação Trabalhista",
            tribunal="TRT2",
            sem_advogado=True,
        )
        import dataclasses

        cached_json = json.dumps([dataclasses.asdict(litigante_cached)])

        redis_mock = MagicMock()
        redis_mock.get = AsyncMock(return_value=cached_json)

        http_mock = _make_http_mock([])

        client = DataJudProspeccaoClient(api_key=None, redis=redis_mock)
        with patch(
            "feature_1_ia_personalizada.services.prospeccao.datajud_prospeccao.httpx.AsyncClient",
            return_value=http_mock,
        ):
            resultado = await client.buscar_litigantes(
                tipo_acao="reclamação trabalhista",
                tribunal="TRT2",
            )

        assert len(resultado) == 1
        assert resultado[0].nome == "Empresa Cached LTDA"
        http_mock.post.assert_not_awaited()
