# feature_1_ia_personalizada/tests/unit/test_memory.py
"""
Testes do ConversationMemory: FIFO, TTL, truncamento, isolamento de tenant e LGPD.
"""

from __future__ import annotations

import json
import logging

import pytest

from feature_1_ia_personalizada.services.ai.memory import (
    _MAX_CONTENT_CHARS,
    _MAX_MENSAGENS,
    _TTL_SEGUNDOS,
    ConversationMemory,
    _chave,
)
from feature_1_ia_personalizada.tests.conftest import FakeRedis


@pytest.fixture
def memory(fake_redis: FakeRedis) -> ConversationMemory:
    return ConversationMemory(fake_redis)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _salvar_n(memory: ConversationMemory, n: int, escritorio=1, cliente=1) -> None:
    for i in range(n):
        await memory.salvar_mensagem(escritorio, cliente, "user", f"mensagem {i}")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    async def test_salvar_e_buscar_round_trip(
        self, memory: ConversationMemory, fake_redis: FakeRedis
    ):
        await memory.salvar_mensagem(1, 1, "user", "olá")
        historico = await memory.buscar_historico(1, 1)
        assert historico == [{"role": "user", "content": "olá"}]

    async def test_roles_preservados(self, memory: ConversationMemory):
        await memory.salvar_mensagem(1, 1, "user", "pergunta")
        await memory.salvar_mensagem(1, 1, "assistant", "resposta")
        historico = await memory.buscar_historico(1, 1)
        assert historico[0]["role"] == "user"
        assert historico[1]["role"] == "assistant"

    async def test_unicode_round_trip(self, memory: ConversationMemory):
        texto = "Petição com acentuação 📋 e emoji ⚖️"
        await memory.salvar_mensagem(1, 1, "user", texto)
        historico = await memory.buscar_historico(1, 1)
        assert historico[0]["content"] == texto

    async def test_historico_vazio_retorna_lista_vazia(self, memory: ConversationMemory):
        historico = await memory.buscar_historico(99, 99)
        assert historico == []

    async def test_tamanho_historico_correto(self, memory: ConversationMemory):
        await _salvar_n(memory, 5)
        assert await memory.tamanho_historico(1, 1) == 5

    async def test_limpar_historico_remove_tudo(self, memory: ConversationMemory):
        await _salvar_n(memory, 3)
        await memory.limpar_historico(1, 1)
        assert await memory.tamanho_historico(1, 1) == 0
        assert await memory.buscar_historico(1, 1) == []

    async def test_buscar_limite_maior_que_historico_retorna_tudo(self, memory: ConversationMemory):
        await _salvar_n(memory, 5)
        historico = await memory.buscar_historico(1, 1, limite=100)
        assert len(historico) == 5


# ---------------------------------------------------------------------------
# FIFO e limites
# ---------------------------------------------------------------------------


class TestFIFO:
    async def test_101a_mensagem_remove_a_mais_antiga(
        self, memory: ConversationMemory, fake_redis: FakeRedis
    ):
        """Ao atingir 100 msgs, a 101ª deve descartar a mais antiga."""
        for i in range(_MAX_MENSAGENS):
            await memory.salvar_mensagem(1, 1, "user", f"msg_{i}")

        await memory.salvar_mensagem(1, 1, "user", "msg_nova")

        chave = _chave(1, 1)
        itens = fake_redis._list(chave)
        assert len(itens) == _MAX_MENSAGENS

        # Primeira item agora deve ser msg_1 (msg_0 foi descartada)
        primeiro = json.loads(itens[0])
        assert primeiro["content"] == "msg_1"

        # Último item deve ser a nova mensagem
        ultimo = json.loads(itens[-1])
        assert ultimo["content"] == "msg_nova"

    async def test_limite_nao_excedido_com_muitas_mensagens(
        self, memory: ConversationMemory, fake_redis: FakeRedis
    ):
        await _salvar_n(memory, _MAX_MENSAGENS + 10)
        chave = _chave(1, 1)
        assert len(fake_redis._list(chave)) == _MAX_MENSAGENS

    async def test_buscar_com_limite_menor(self, memory: ConversationMemory):
        await _salvar_n(memory, 10)
        historico = await memory.buscar_historico(1, 1, limite=3)
        assert len(historico) == 3
        # Deve retornar as ÚLTIMAS 3 (mais recentes)
        assert historico[-1]["content"] == "mensagem 9"


# ---------------------------------------------------------------------------
# TTL
# ---------------------------------------------------------------------------


class TestTTL:
    async def test_salvar_define_ttl(self, memory: ConversationMemory, fake_redis: FakeRedis):
        await memory.salvar_mensagem(1, 1, "user", "msg")
        chave = _chave(1, 1)
        assert fake_redis._ttl(chave) == _TTL_SEGUNDOS

    async def test_buscar_renova_ttl(self, memory: ConversationMemory, fake_redis: FakeRedis):
        """buscar_historico deve renovar o TTL mesmo que salvar já tenha feito isso."""
        await memory.salvar_mensagem(1, 1, "user", "msg")
        chave = _chave(1, 1)

        # Simula TTL expirado no store (sem deletar os dados)
        fake_redis._reset_ttl(chave)
        assert fake_redis._ttl(chave) is None

        await memory.buscar_historico(1, 1)
        assert fake_redis._ttl(chave) == _TTL_SEGUNDOS

    async def test_ttl_e_7_dias(self):
        assert _TTL_SEGUNDOS == 60 * 60 * 24 * 7


# ---------------------------------------------------------------------------
# Truncamento de conteúdo
# ---------------------------------------------------------------------------


class TestTruncamento:
    async def test_conteudo_4097_chars_truncado_para_4096(
        self, memory: ConversationMemory, fake_redis: FakeRedis
    ):
        conteudo_longo = "x" * (_MAX_CONTENT_CHARS + 1)
        await memory.salvar_mensagem(1, 1, "user", conteudo_longo)

        chave = _chave(1, 1)
        item = json.loads(fake_redis._list(chave)[0])
        assert len(item["content"]) == _MAX_CONTENT_CHARS

    async def test_conteudo_exatamente_4096_nao_truncado(
        self, memory: ConversationMemory, fake_redis: FakeRedis
    ):
        conteudo_exato = "y" * _MAX_CONTENT_CHARS
        await memory.salvar_mensagem(1, 1, "user", conteudo_exato)

        chave = _chave(1, 1)
        item = json.loads(fake_redis._list(chave)[0])
        assert len(item["content"]) == _MAX_CONTENT_CHARS

    async def test_conteudo_curto_nao_alterado(
        self, memory: ConversationMemory, fake_redis: FakeRedis
    ):
        await memory.salvar_mensagem(1, 1, "user", "curto")
        chave = _chave(1, 1)
        item = json.loads(fake_redis._list(chave)[0])
        assert item["content"] == "curto"


# ---------------------------------------------------------------------------
# Isolamento multi-tenant
# ---------------------------------------------------------------------------


class TestIsolamento:
    async def test_escritorios_diferentes_nao_se_misturam(self, memory: ConversationMemory):
        await memory.salvar_mensagem(1, 1, "user", "escritorio 1")
        await memory.salvar_mensagem(2, 1, "user", "escritorio 2")

        hist_1 = await memory.buscar_historico(1, 1)
        hist_2 = await memory.buscar_historico(2, 1)

        assert hist_1[0]["content"] == "escritorio 1"
        assert hist_2[0]["content"] == "escritorio 2"
        assert len(hist_1) == 1
        assert len(hist_2) == 1

    async def test_clientes_diferentes_nao_se_misturam(self, memory: ConversationMemory):
        await memory.salvar_mensagem(1, 10, "user", "cliente 10")
        await memory.salvar_mensagem(1, 20, "user", "cliente 20")

        hist_10 = await memory.buscar_historico(1, 10)
        hist_20 = await memory.buscar_historico(1, 20)

        assert hist_10[0]["content"] == "cliente 10"
        assert hist_20[0]["content"] == "cliente 20"

    async def test_limpar_historico_nao_afeta_outro_cliente(self, memory: ConversationMemory):
        await memory.salvar_mensagem(1, 1, "user", "cliente 1")
        await memory.salvar_mensagem(1, 2, "user", "cliente 2")

        await memory.limpar_historico(1, 1)

        assert await memory.buscar_historico(1, 1) == []
        assert len(await memory.buscar_historico(1, 2)) == 1


# ---------------------------------------------------------------------------
# Resiliência e LGPD
# ---------------------------------------------------------------------------


class TestResiliencia:
    async def test_item_corrompido_ignorado_sem_crash(
        self, memory: ConversationMemory, fake_redis: FakeRedis
    ):
        """Um item com JSON inválido no Redis não deve derrubar o buscar_historico."""
        chave = _chave(1, 1)
        # Acesso direto ao _store.lists é intencional: precisamos injetar um estado
        # corrompido que não pode ser criado pela API pública do FakeRedis.
        # Se a estrutura interna do FakeRedis mudar, este teste precisará ser atualizado.
        fake_redis._store.lists[chave] = [
            json.dumps({"role": "user", "content": "ok"}),
            "ISSO NAO E JSON {{{",  # corrompido
            json.dumps({"role": "assistant", "content": "também ok"}),
        ]

        historico = await memory.buscar_historico(1, 1)
        # Deve retornar apenas os 2 itens válidos
        assert len(historico) == 2
        assert historico[0]["content"] == "ok"
        assert historico[1]["content"] == "também ok"

    async def test_log_item_corrompido_nao_expoe_conteudo(
        self, memory: ConversationMemory, fake_redis: FakeRedis, caplog
    ):
        """LGPD: o log de item inválido não deve logar o conteúdo bruto."""
        chave = _chave(1, 1)
        dados_sensiveis = "CPF: 123.456.789-00 — NÃO DEVE APARECER NO LOG"
        # Acesso direto ao _store.lists é intencional: simula dado sensível corrompido
        # já persistido no Redis, impossível de injetar via API pública.
        fake_redis._store.lists[chave] = [dados_sensiveis]

        with caplog.at_level(logging.WARNING):
            await memory.buscar_historico(1, 1)

        for record in caplog.records:
            assert dados_sensiveis not in record.getMessage()
            assert dados_sensiveis not in str(record.__dict__)
