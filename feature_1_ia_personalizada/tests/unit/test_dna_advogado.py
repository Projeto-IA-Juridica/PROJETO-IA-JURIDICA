"""
Testes unitários — DNAAdvogadoService
======================================
Verifica que:
- Escritório com < 5 processos retorna dados_insuficientes=True sem chamar Claude
- Especialidades trabalhistas/societárias → tipo_lead_predominante = "empresa"
- Especialidades de família/divórcio → tipo_lead_predominante = "pessoa"
- Cache Redis é utilizado quando disponível
- Fallback gracioso em caso de erro do Claude
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.prospeccao.dna_advogado import (
    DNAAdvogadoService,
    DNAEscritorio,
)


# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------

def _make_claude_mock(resposta_json: str) -> MagicMock:
    """Cria um ClaudeClient mock que retorna o JSON especificado."""
    mock = MagicMock()
    mock.chamar_direto = AsyncMock(
        return_value={
            "resposta": resposta_json,
            "tokens_input": 100,
            "tokens_output": 50,
        }
    )
    return mock


def _make_redis_mock(valor_cache: str | None = None) -> MagicMock:
    """Cria um Redis mock simples."""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=valor_cache)
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    return mock


def _make_db_mock(rows: list | None = None) -> MagicMock:
    """Cria uma AsyncSession mock retornando as linhas especificadas."""
    mock = AsyncMock()
    result_mock = MagicMock()
    result_mock.all.return_value = rows or []
    result_mock.one_or_none.return_value = None
    result_mock.scalar_one_or_none.return_value = None
    mock.execute = AsyncMock(return_value=result_mock)
    mock.commit = AsyncMock()
    return mock


# ---------------------------------------------------------------------------
# Testes: dados insuficientes (< 5 processos)
# ---------------------------------------------------------------------------

class TestDNADadosInsuficientes:
    @pytest.mark.asyncio
    async def test_menos_de_5_processos_retorna_dados_insuficientes(self):
        """Com 0 processos, o DNA deve ter dados_insuficientes=True sem chamar Claude."""
        claude = _make_claude_mock("{}")
        redis = _make_redis_mock(None)  # sem cache

        # DB retorna 0 processos e escritório sem DNA salvo
        db = _make_db_mock(rows=[])

        # Configura o escritório sem DNA salvo
        escritorio_row = MagicMock()
        escritorio_row.dna_prospeccao = None
        escritorio_row.nome = "Escritório Teste"

        result_seq = [MagicMock(), MagicMock()]
        result_seq[0].all.return_value = []           # query de stats
        result_seq[0].one_or_none.return_value = escritorio_row
        result_seq[1].all.return_value = []           # query de polo (não deve ser chamada)

        call_count = 0

        async def _execute_side_effect(*args, **kwargs):
            nonlocal call_count
            r = result_seq[min(call_count, len(result_seq) - 1)]
            call_count += 1
            return r

        db.execute = AsyncMock(side_effect=_execute_side_effect)

        svc = DNAAdvogadoService(claude=claude, redis=redis)
        dna = await svc.gerar_dna(escritorio_id=1, db=db)

        assert dna.dados_insuficientes is True
        claude.chamar_direto.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_4_processos_retorna_dados_insuficientes(self):
        """Exatamente 4 processos: abaixo do limiar mínimo de 5."""
        claude = _make_claude_mock("{}")
        redis = _make_redis_mock(None)

        # Simula 4 processos no banco
        row1 = MagicMock()
        row1.tipo_acao = "Trabalhista"
        row1.contagem = 4

        result_mock = MagicMock()
        result_mock.all.return_value = [row1]
        result_mock.one_or_none.return_value = None

        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()

        svc = DNAAdvogadoService(claude=claude, redis=redis)
        dna = await svc.gerar_dna(escritorio_id=1, db=db)

        assert dna.dados_insuficientes is True
        claude.chamar_direto.assert_not_awaited()


# ---------------------------------------------------------------------------
# Testes: especialidades B2B (empresa)
# ---------------------------------------------------------------------------

class TestDNATipoLeadEmpresa:
    @pytest.mark.asyncio
    async def test_trabalhista_retorna_tipo_empresa(self):
        """Escritório com maioria trabalhista → tipo_lead_predominante = empresa."""
        resposta = (
            '{"especialidades": ["Direito Trabalhista"], '
            '"setores_alvo": ["Indústria", "Comércio"], '
            '"tipo_lead_predominante": "empresa", '
            '"perfil_cliente_ideal": "Empresas com alto turnover", '
            '"diferenciais": ["Agilidade", "Experiência em TCO"]}'
        )
        claude = _make_claude_mock(resposta)
        redis = _make_redis_mock(None)

        # 10 processos trabalhistas
        row = MagicMock()
        row.tipo_acao = "Reclamação Trabalhista"
        row.contagem = 10

        polo_row = MagicMock()
        polo_row.polo_cliente = "réu"
        polo_row.contagem = 8

        result_stats = MagicMock()
        result_stats.all.return_value = [row]

        result_polo = MagicMock()
        result_polo.all.return_value = [polo_row]

        result_escritorio = MagicMock()
        result_escritorio.one_or_none.return_value = None  # sem DNA salvo
        result_escritorio.scalar_one_or_none.return_value = "Escritório Trabalhista"

        call_count = 0
        mocks_seq = [result_stats, result_polo, result_escritorio, result_escritorio]

        async def _execute(stmt, **kwargs):
            nonlocal call_count
            r = mocks_seq[min(call_count, len(mocks_seq) - 1)]
            call_count += 1
            return r

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=_execute)
        db.commit = AsyncMock()

        svc = DNAAdvogadoService(claude=claude, redis=redis)
        dna = await svc.gerar_dna(escritorio_id=1, db=db, nome_escritorio="Escritório Trabalhista")

        assert dna.tipo_lead_predominante == "empresa"
        assert not dna.dados_insuficientes
        assert "Direito Trabalhista" in dna.especialidades


# ---------------------------------------------------------------------------
# Testes: especialidades B2C (pessoa)
# ---------------------------------------------------------------------------

class TestDNATipoLeadPessoa:
    @pytest.mark.asyncio
    async def test_familia_retorna_tipo_pessoa(self):
        """Escritório de família → tipo_lead_predominante = pessoa."""
        resposta = (
            '{"especialidades": ["Direito de Família", "Divórcio"], '
            '"setores_alvo": ["Pessoas físicas em litígio familiar"], '
            '"tipo_lead_predominante": "pessoa", '
            '"perfil_cliente_ideal": "Casais em processo de separação", '
            '"diferenciais": ["Mediação", "Acordo extrajudicial"]}'
        )
        claude = _make_claude_mock(resposta)
        redis = _make_redis_mock(None)

        row = MagicMock()
        row.tipo_acao = "Divórcio Consensual"
        row.contagem = 12

        polo_row = MagicMock()
        polo_row.polo_cliente = "autor"
        polo_row.contagem = 10

        result_stats = MagicMock()
        result_stats.all.return_value = [row]
        result_polo = MagicMock()
        result_polo.all.return_value = [polo_row]

        call_count = 0
        mocks_seq = [result_stats, result_polo]

        async def _execute(stmt, **kwargs):
            nonlocal call_count
            r = mocks_seq[min(call_count, len(mocks_seq) - 1)]
            call_count += 1
            return r

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=_execute)
        db.commit = AsyncMock()

        svc = DNAAdvogadoService(claude=claude, redis=redis)
        dna = await svc.gerar_dna(
            escritorio_id=2, db=db, nome_escritorio="Escritório Família"
        )

        assert dna.tipo_lead_predominante == "pessoa"
        assert not dna.dados_insuficientes


# ---------------------------------------------------------------------------
# Testes: cache Redis
# ---------------------------------------------------------------------------

class TestDNACache:
    @pytest.mark.asyncio
    async def test_cache_hit_nao_consulta_banco(self):
        """Se há cache Redis válido, o banco não é consultado."""
        import json

        dna_cached = DNAEscritorio(
            escritorio_id=5,
            especialidades=["Tributário"],
            setores_alvo=["Indústria"],
            tipo_lead_predominante="empresa",
            perfil_cliente_ideal="Empresas com débitos fiscais",
            diferenciais=["Parcelamento"],
            top_tipos_acao=[{"tipo": "Execução Fiscal", "contagem": 20, "percentual": 100.0}],
            dados_insuficientes=False,
            gerado_em=datetime.now(timezone.utc),
        )
        redis = _make_redis_mock(json.dumps(dna_cached.to_dict()))
        claude = _make_claude_mock("{}")
        db = AsyncMock()

        svc = DNAAdvogadoService(claude=claude, redis=redis)
        dna = await svc.obter_dna(escritorio_id=5, db=db)

        assert dna.escritorio_id == 5
        assert dna.tipo_lead_predominante == "empresa"
        db.execute.assert_not_called()
        claude.chamar_direto.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fallback_json_invalido_retorna_dna_parcial(self):
        """Se Claude retorna JSON inválido, retorna DNA parcial sem falhar."""
        claude = _make_claude_mock("RESPOSTA INVÁLIDA NÃO É JSON {{{")
        redis = _make_redis_mock(None)

        row = MagicMock()
        row.tipo_acao = "Execução Fiscal"
        row.contagem = 8

        polo_row = MagicMock()
        polo_row.polo_cliente = "autor"
        polo_row.contagem = 7

        result_stats = MagicMock()
        result_stats.all.return_value = [row]
        result_polo = MagicMock()
        result_polo.all.return_value = [polo_row]

        call_count = 0
        mocks_seq = [result_stats, result_polo]

        async def _execute(stmt, **kwargs):
            nonlocal call_count
            r = mocks_seq[min(call_count, len(mocks_seq) - 1)]
            call_count += 1
            return r

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=_execute)
        db.commit = AsyncMock()

        svc = DNAAdvogadoService(claude=claude, redis=redis)
        dna = await svc.gerar_dna(escritorio_id=3, db=db, nome_escritorio="Teste")

        # Não deve lançar exceção; retorna DNA parcial
        assert isinstance(dna, DNAEscritorio)
        assert not dna.dados_insuficientes
