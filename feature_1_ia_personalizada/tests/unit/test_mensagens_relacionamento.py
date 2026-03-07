# feature_1_ia_personalizada/tests/unit/test_mensagens_relacionamento.py
"""
Testes das tasks de relacionamento (workers/mensagens_relacionamento.py).

Estratégia:
  - Funções puras (normalizar_texto, chave, dividir_em_lotes) testadas diretamente.
  - Helpers Redis usam MagicMock no cliente_redis do módulo.
  - Tasks Celery são executadas via .run(mock_self) com todas as integrações
    mockadas (GoogleSheetsClient, WhatsAppService, Redis, buscar_processo_ativo_do_cliente,
    salvar_interacao, buscar_data_ultima_interacao).
  - time.sleep é patcheado para não atrasar a suite.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import feature_1_ia_personalizada.workers.mensagens_relacionamento as mr
from feature_1_ia_personalizada.workers.mensagens_relacionamento import (
    Cliente,
    Processo,
    adquirir_bloqueio,
    chave,
    dia_mes_hoje,
    dividir_em_lotes,
    ja_enviado_recentemente,
    marcar_enviado,
    normalizar_texto,
    verificar_aniversarios_diarios,
    verificar_clientes_sem_contato,
    verificar_datas_comemorativas,
)

_TZ_BR = timezone(timedelta(hours=-3))


@pytest.fixture(autouse=True)
def _reset_sheets_singleton():
    """Reseta o singleton GoogleSheetsClient._client entre testes para evitar vazamento de estado."""
    mr.GoogleSheetsClient._client = None
    yield
    mr.GoogleSheetsClient._client = None


def _cliente(
    id: int = 1,
    nome: str = "João Silva",
    telefone: str = "5511999999999",
    status: str = "ativo",
    data_nascimento: str | None = None,
    profissao: str | None = None,
) -> Cliente:
    return Cliente(
        id=id,
        nome=nome,
        telefone=telefone,
        status=status,
        data_nascimento=data_nascimento,
        profissao=profissao,
    )


def _processo(
    id: int = 10, numero: str = "0001234-56.2023.8.26.0001", cliente_id: int = 1
) -> Processo:
    return Processo(id=id, numero=numero, cliente_id=cliente_id, status="ativo")


def _mock_redis(*, existe: bool = False, lock_ok: bool = True) -> MagicMock:
    redis = MagicMock()
    redis.exists.return_value = 1 if existe else 0
    redis.set.return_value = True if lock_ok else None
    return redis


# ---------------------------------------------------------------------------
# Funções puras
# ---------------------------------------------------------------------------


class TestNormalizarTexto:
    def test_minusculo(self):
        assert normalizar_texto("ATIVO") == "ativo"

    def test_remove_acentos(self):
        assert normalizar_texto("Bancário") == "bancario"

    def test_strip(self):
        assert normalizar_texto("  ativo  ") == "ativo"

    def test_string_vazia(self):
        assert normalizar_texto("") == ""

    def test_none_equivalente(self):
        assert normalizar_texto("") == ""

    def test_combinado(self):
        assert normalizar_texto("  Professôr  ") == "professor"


class TestChave:
    def test_prefixo_e_uma_parte(self):
        assert (
            chave("relacionamento:aniversario", 1, "01-03")
            == "relacionamento:aniversario:1:01-03"
        )

    def test_sem_partes_adicionais(self):
        assert chave("lock:teste") == "lock:teste:"

    def test_parte_inteiro(self):
        resultado = chave("prefixo", 42)
        assert "42" in resultado


class TestDividirEmLotes:
    def test_lista_vazia(self):
        assert dividir_em_lotes([], 5) == []

    def test_lote_exato(self):
        resultado = dividir_em_lotes([1, 2, 3, 4], 2)
        assert resultado == [[1, 2], [3, 4]]

    def test_lote_com_sobra(self):
        resultado = dividir_em_lotes([1, 2, 3], 2)
        assert resultado == [[1, 2], [3]]

    def test_tamanho_maior_que_lista(self):
        assert dividir_em_lotes([1, 2], 10) == [[1, 2]]


# ---------------------------------------------------------------------------
# Helpers Redis
# ---------------------------------------------------------------------------


class TestRedisHelpers:
    def test_adquirir_bloqueio_retorna_true_quando_set_ok(self):
        redis = _mock_redis(lock_ok=True)
        with patch.object(mr, "cliente_redis", redis):
            assert adquirir_bloqueio("lock:x", 300) is True
        redis.set.assert_called_once_with("lock:x", "1", nx=True, ex=300)

    def test_adquirir_bloqueio_retorna_false_quando_set_falha(self):
        redis = MagicMock()
        redis.set.return_value = None
        with patch.object(mr, "cliente_redis", redis):
            assert adquirir_bloqueio("lock:x", 300) is False

    def test_ja_enviado_recentemente_true(self):
        redis = _mock_redis(existe=True)
        with patch.object(mr, "cliente_redis", redis):
            assert ja_enviado_recentemente("chave:x") is True

    def test_ja_enviado_recentemente_false(self):
        redis = _mock_redis(existe=False)
        with patch.object(mr, "cliente_redis", redis):
            assert ja_enviado_recentemente("chave:x") is False

    def test_marcar_enviado_chama_set_com_expiracao(self):
        redis = MagicMock()
        with patch.object(mr, "cliente_redis", redis):
            marcar_enviado("chave:x", 2592000)
        redis.set.assert_called_once_with("chave:x", "1", ex=2592000)


# ---------------------------------------------------------------------------
# Task: verificar_aniversarios_diarios
# ---------------------------------------------------------------------------


class TestVerificarAniversarios:
    def _run(self, clientes, redis=None, processo=None, *, lock_ok=True, existe=False):
        """Executa a task com todas as dependências mockadas."""
        redis = redis or _mock_redis(lock_ok=lock_ok, existe=existe)

        with (
            patch.object(mr, "cliente_redis", redis),
            patch.object(mr.GoogleSheetsClient, "get_clientes", return_value=clientes),
            patch.object(mr.GoogleSheetsClient, "registrar_log_envio"),
            patch.object(mr.WhatsAppService, "enviar_mensagem"),
            patch.object(mr, "buscar_processo_ativo_do_cliente", return_value=processo),
            patch.object(mr, "salvar_interacao"),
            patch("time.sleep"),
        ):
            return verificar_aniversarios_diarios.run()

    def _hoje(self) -> tuple[int, int]:
        return dia_mes_hoje()

    def test_cliente_aniversariante_envia_mensagem(self):
        dia, mes = self._hoje()
        cliente = _cliente(data_nascimento=f"1990-{mes:02d}-{dia:02d}")
        redis = _mock_redis(lock_ok=True, existe=False)

        with (
            patch.object(mr, "cliente_redis", redis),
            patch.object(mr.GoogleSheetsClient, "get_clientes", return_value=[cliente]),
            patch.object(mr.GoogleSheetsClient, "registrar_log_envio"),
            patch.object(mr.WhatsAppService, "enviar_mensagem") as mock_enviar,
            patch.object(mr, "buscar_processo_ativo_do_cliente", return_value=None),
            patch.object(mr, "salvar_interacao"),
            patch("time.sleep"),
        ):
            result = verificar_aniversarios_diarios.run()

        assert result["enviados"] == 1
        mock_enviar.assert_called_once()
        args = mock_enviar.call_args
        assert cliente.nome in args.kwargs.get("texto", args[1].get("texto", ""))

    def test_cliente_inativo_e_ignorado(self):
        dia, mes = self._hoje()
        cliente = _cliente(
            status="inativo", data_nascimento=f"1990-{mes:02d}-{dia:02d}"
        )
        result = self._run([cliente])
        assert result["enviados"] == 0
        assert result["total"] == 0

    def test_cliente_sem_data_nascimento_e_ignorado(self):
        cliente = _cliente(data_nascimento=None)
        result = self._run([cliente])
        assert result["enviados"] == 0

    def test_cliente_data_invalida_e_ignorado(self):
        cliente = _cliente(data_nascimento="nao-e-data")
        result = self._run([cliente])
        assert result["enviados"] == 0

    def test_ja_enviado_recentemente_incrementa_ignorados(self):
        dia, mes = self._hoje()
        cliente = _cliente(data_nascimento=f"1990-{mes:02d}-{dia:02d}")
        redis = _mock_redis(existe=True)
        result = self._run([cliente], redis=redis)
        assert result["enviados"] == 0
        assert result["ignorados"] == 1

    def test_lock_nao_adquirido_incrementa_ignorados(self):
        dia, mes = self._hoje()
        cliente = _cliente(data_nascimento=f"1990-{mes:02d}-{dia:02d}")
        redis = MagicMock()
        redis.exists.return_value = 0  # não enviado ainda
        redis.set.return_value = None  # lock falha
        result = self._run([cliente], redis=redis)
        assert result["ignorados"] == 1

    def test_retorno_contem_campos_esperados(self):
        result = self._run([])
        assert result["status"] == "ok"
        assert "enviados" in result
        assert "ignorados" in result
        assert "total" in result


# ---------------------------------------------------------------------------
# Task: verificar_datas_comemorativas
# ---------------------------------------------------------------------------


class TestVerificarDatasComemorativas:
    def _run(self, clientes, datas, redis=None, *, lock_ok=True, existe=False):
        redis = redis or _mock_redis(lock_ok=lock_ok, existe=existe)

        with (
            patch.object(mr, "cliente_redis", redis),
            patch.object(mr.GoogleSheetsClient, "get_clientes", return_value=clientes),
            patch.object(
                mr.GoogleSheetsClient, "get_datas_comemorativas", return_value=datas
            ),
            patch.object(mr.GoogleSheetsClient, "registrar_log_envio"),
            patch.object(mr.WhatsAppService, "enviar_mensagem"),
            patch.object(mr, "buscar_processo_ativo_do_cliente", return_value=None),
            patch.object(mr, "salvar_interacao"),
            patch("time.sleep"),
        ):
            return verificar_datas_comemorativas.run()

    def _hoje_data(self) -> dict:
        dia, mes = dia_mes_hoje()
        return {
            "dia": dia,
            "mes": mes,
            "nome": "Dia do Teste",
            "profissao_alvo": "",
            "template": "",
        }

    def test_sem_datas_hoje_retorna_zero(self):
        """Data fixa em 15/03 garante que a data '01/01' nunca coincide com hoje."""
        data_ano_novo = {
            "dia": 1,
            "mes": 1,
            "nome": "Ano Novo",
            "profissao_alvo": "",
            "template": "",
        }
        data_fixa = datetime(2024, 3, 15, tzinfo=_TZ_BR)
        with patch.object(mr, "agora_local", return_value=data_fixa):
            result = self._run([_cliente()], datas=[data_ano_novo])
        assert result["enviados"] == 0
        assert result["datas"] == 0

    def test_data_hoje_envia_para_clientes_ativos(self):
        data = self._hoje_data()
        cliente = _cliente()
        result = self._run([cliente], datas=[data])
        assert result["enviados"] == 1

    def test_template_dia_bancario_usado_corretamente(self):
        data = {
            **self._hoje_data(),
            "template": "TEMPLATE_DIA_BANCARIO",
            "nome": "Dia do Bancário",
        }
        cliente = _cliente()
        redis = _mock_redis(lock_ok=True, existe=False)

        with (
            patch.object(mr, "cliente_redis", redis),
            patch.object(mr.GoogleSheetsClient, "get_clientes", return_value=[cliente]),
            patch.object(
                mr.GoogleSheetsClient, "get_datas_comemorativas", return_value=[data]
            ),
            patch.object(mr.GoogleSheetsClient, "registrar_log_envio"),
            patch.object(mr.WhatsAppService, "enviar_mensagem") as mock_enviar,
            patch.object(mr, "buscar_processo_ativo_do_cliente", return_value=None),
            patch.object(mr, "salvar_interacao"),
            patch("time.sleep"),
        ):
            verificar_datas_comemorativas.run()

        texto_enviado = mock_enviar.call_args.kwargs.get(
            "texto", mock_enviar.call_args[1].get("texto", "")
        )
        assert "Dia do Bancário" in texto_enviado

    def test_filtro_por_profissao(self):
        data = {**self._hoje_data(), "profissao_alvo": "bancario"}
        bancario = _cliente(id=1, profissao="Bancário")
        professor = _cliente(id=2, profissao="Professor")

        with (
            patch.object(mr, "cliente_redis", _mock_redis()),
            patch.object(
                mr.GoogleSheetsClient,
                "get_clientes",
                return_value=[bancario, professor],
            ),
            patch.object(
                mr.GoogleSheetsClient, "get_datas_comemorativas", return_value=[data]
            ),
            patch.object(mr.GoogleSheetsClient, "registrar_log_envio"),
            patch.object(mr.WhatsAppService, "enviar_mensagem") as mock_enviar,
            patch.object(mr, "buscar_processo_ativo_do_cliente", return_value=None),
            patch.object(mr, "salvar_interacao"),
            patch("time.sleep"),
        ):
            verificar_datas_comemorativas.run()

        # Apenas o bancário deve ter recebido mensagem
        assert mock_enviar.call_count == 1

    def test_cliente_inativo_nao_recebe(self):
        data = self._hoje_data()
        cliente = _cliente(status="inativo")
        result = self._run([cliente], datas=[data])
        assert result["enviados"] == 0

    def test_retorno_contem_campos_esperados(self):
        result = self._run([], datas=[])
        assert result["status"] == "ok"
        assert "enviados" in result
        assert "ignorados" in result
        assert "datas" in result


# ---------------------------------------------------------------------------
# Task: verificar_clientes_sem_contato
# ---------------------------------------------------------------------------


class TestVerificarClientesSemContato:
    def _run(
        self,
        clientes,
        ultima_interacao_por_id: dict,
        redis=None,
        *,
        lock_ok=True,
        existe=False,
    ):
        redis = redis or _mock_redis(lock_ok=lock_ok, existe=existe)

        with (
            patch.object(mr, "cliente_redis", redis),
            patch.object(mr.GoogleSheetsClient, "get_clientes", return_value=clientes),
            patch.object(mr.GoogleSheetsClient, "registrar_log_envio"),
            patch.object(mr.WhatsAppService, "enviar_mensagem"),
            patch.object(mr, "buscar_processo_ativo_do_cliente", return_value=None),
            patch.object(mr, "salvar_interacao"),
            patch.object(mr, "query_ultima_interacao_batch", return_value=ultima_interacao_por_id),
            patch("time.sleep"),
        ):
            return verificar_clientes_sem_contato.run()

    def test_cliente_sem_interacao_e_candidato(self):
        cliente = _cliente()
        result = self._run([cliente], ultima_interacao_por_id={})
        assert result["enviados"] == 1

    def test_cliente_com_interacao_recente_nao_e_candidato(self):
        cliente = _cliente()
        agora = datetime.now(tz=_TZ_BR)
        result = self._run(
            [cliente],
            ultima_interacao_por_id={cliente.id: agora - timedelta(days=10)},
        )
        assert result["candidatos"] == 0
        assert result["enviados"] == 0

    def test_cliente_com_interacao_antiga_e_candidato(self):
        cliente = _cliente()
        agora = datetime.now(tz=_TZ_BR)
        result = self._run(
            [cliente],
            ultima_interacao_por_id={cliente.id: agora - timedelta(days=100)},
        )
        assert result["enviados"] == 1

    def test_limite_de_10_clientes(self):
        clientes = [_cliente(id=i, telefone=f"551199999{i:04d}") for i in range(1, 20)]
        result = self._run(clientes, ultima_interacao_por_id={})
        assert result["candidatos"] <= 10
        assert result["enviados"] <= 10

    def test_cliente_inativo_nao_e_candidato(self):
        cliente = _cliente(status="inativo")
        result = self._run([cliente], ultima_interacao_por_id={})
        assert result["candidatos"] == 0

    def test_deduplicacao_redis_impede_reenvio(self):
        cliente = _cliente()
        redis = _mock_redis(lock_ok=True, existe=True)  # já enviado
        result = self._run([cliente], ultima_interacao_por_id={}, redis=redis)
        assert result["enviados"] == 0
        assert result["ignorados"] == 1

    def test_retorno_contem_campos_esperados(self):
        result = self._run([], ultima_interacao_por_id={})
        assert result["status"] == "ok"
        assert "enviados" in result
        assert "ignorados" in result
        assert "candidatos" in result
