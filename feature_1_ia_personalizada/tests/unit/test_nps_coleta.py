"""
Testes unitários para coleta de NPS via WhatsApp.

Cobre _processar_resposta_nps (webhook_whatsapp.py):
  - Detecção de resposta numérica 1-5 com NPS pendente → registra e agradece
  - Texto não-numérico → retorna False (segue para a IA)
  - Número 1-5 sem interação aguardando NPS → retorna False
  - NPS ≤ 3 → alerta enviado aos advogados
  - NPS > 3 → sem alerta
  - Limitação: sem_avaliacao não interfere na detecção
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feature_1_ia_personalizada.api.routes.webhook_whatsapp import _processar_resposta_nps


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cliente_mock(nome: str = "Maria", telefone: str = "5511999999999") -> MagicMock:
    c = MagicMock()
    c.id = 1
    c.nome = nome
    c.telefone_whatsapp = telefone
    return c


def _escritorio_mock(instance: str = "test-instance") -> MagicMock:
    e = MagicMock()
    e.id = 10
    e.webhook_whatsapp_instance = instance
    return e


def _interacao_nps_pendente() -> MagicMock:
    """Interação com aguardando_nps=True no metadata."""
    i = MagicMock()
    i.metadata_json = {"aguardando_nps": True, "tipo_relacionamento": "nps_solicitado"}
    i.satisfacao = None
    return i


def _mock_db_com_nps(interacao=None) -> AsyncMock:
    """db que retorna uma interação NPS pendente (ou None se omitido)."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = interacao
    db.execute.return_value = mock_result
    db.commit = AsyncMock()
    return db


def _patch_evo():
    """
    Patcha EvolutionClient na origem do módulo onde é importado inline.
    Como _processar_resposta_nps usa 'from ...evolution_client import EvolutionClient',
    o patch deve apontar para o módulo fonte, não para o webhook.
    """
    evo_mock = AsyncMock()
    evo_mock.enviar_texto = AsyncMock()
    evo_mock.close = AsyncMock()
    return patch(
        "feature_1_ia_personalizada.services.messaging.evolution_client.EvolutionClient",
        return_value=evo_mock,
    ), evo_mock


# ---------------------------------------------------------------------------
# Texto não-numérico → False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_texto_nao_numerico_retorna_false():
    """Mensagem de texto comum não aciona o fluxo NPS."""
    db = _mock_db_com_nps()
    result = await _processar_resposta_nps(
        "Qual o status do meu processo?", _cliente_mock(), _escritorio_mock(), db
    )
    assert result is False
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_numero_fora_do_range_retorna_false():
    """Números fora de 1-5 não acionam o fluxo NPS."""
    db = _mock_db_com_nps()
    for texto in ("0", "6", "10", "55"):
        result = await _processar_resposta_nps(texto, _cliente_mock(), _escritorio_mock(), db)
        assert result is False, f"Esperava False para '{texto}'"


@pytest.mark.asyncio
async def test_numero_com_espacos_detectado():
    """Número com espaços em branco ao redor é detectado corretamente."""
    interacao = _interacao_nps_pendente()
    db = _mock_db_com_nps(interacao)
    patch_ctx, evo = _patch_evo()

    with patch_ctx:
        result = await _processar_resposta_nps(" 4 ", _cliente_mock(), _escritorio_mock(), db)

    assert result is True


# ---------------------------------------------------------------------------
# Sem interação NPS pendente → False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_numero_valido_sem_nps_pendente_retorna_false():
    """Mensagem '3' mas sem interação aguardando_nps → não é NPS, vai para a IA."""
    db = _mock_db_com_nps(interacao=None)  # sem NPS pendente
    result = await _processar_resposta_nps("3", _cliente_mock(), _escritorio_mock(), db)
    assert result is False
    db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Registro correto da nota
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("nota", [1, 2, 3, 4, 5])
async def test_nota_registrada_no_banco(nota: int):
    """satisfacao é salvo e a flag aguardando_nps é removida."""
    interacao = _interacao_nps_pendente()
    db = _mock_db_com_nps(interacao)
    patch_ctx, _ = _patch_evo()

    with patch_ctx:
        result = await _processar_resposta_nps(str(nota), _cliente_mock(), _escritorio_mock(), db)

    assert result is True
    assert interacao.satisfacao == nota
    assert "aguardando_nps" not in interacao.metadata_json
    db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# Agradecimento enviado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agradecimento_enviado_apos_nps():
    """Após registrar NPS, mensagem de agradecimento é enviada ao cliente."""
    interacao = _interacao_nps_pendente()
    db = _mock_db_com_nps(interacao)
    patch_ctx, evo_mock = _patch_evo()

    with patch_ctx:
        await _processar_resposta_nps("5", _cliente_mock(nome="Lucas"), _escritorio_mock(), db)

    evo_mock.enviar_texto.assert_awaited_once()
    args = evo_mock.enviar_texto.call_args[0]
    assert "Lucas" in args[2]  # mensagem contém nome do cliente


# ---------------------------------------------------------------------------
# Alerta para NPS baixo (≤ 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("nota", [1, 2, 3])
async def test_alerta_enviado_para_nps_baixo(nota: int):
    """NPS ≤ 3 → alerta enviado a todos os advogados com escalacao_ativa."""
    interacao = _interacao_nps_pendente()
    db = _mock_db_com_nps(interacao)

    # Mock do resultado da query de advogados
    adv1 = MagicMock()
    adv1.whatsapp_numero = "5511988880001"
    adv2 = MagicMock()
    adv2.whatsapp_numero = "5511988880002"

    mock_adv_result = MagicMock()
    mock_adv_result.scalars.return_value.all.return_value = [adv1, adv2]

    # execute: primeiro call → interação NPS; segundo call → advogados
    mock_nps_result = MagicMock()
    mock_nps_result.scalar_one_or_none.return_value = interacao
    db.execute.side_effect = [mock_nps_result, mock_adv_result]

    patch_ctx, evo_mock = _patch_evo()

    with patch_ctx:
        result = await _processar_resposta_nps(str(nota), _cliente_mock(), _escritorio_mock(), db)

    assert result is True
    # enviar_texto: 1 agradecimento + 2 alertas = 3 calls
    assert evo_mock.enviar_texto.await_count == 3

    # Verifica que o texto do alerta contém "ALERTA"
    alerta_calls = [
        call for call in evo_mock.enviar_texto.call_args_list
        if "ALERTA" in str(call)
    ]
    assert len(alerta_calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("nota", [4, 5])
async def test_sem_alerta_para_nps_alto(nota: int):
    """NPS > 3 → sem alerta, apenas agradecimento."""
    interacao = _interacao_nps_pendente()
    db = _mock_db_com_nps(interacao)
    patch_ctx, evo_mock = _patch_evo()

    with patch_ctx:
        result = await _processar_resposta_nps(str(nota), _cliente_mock(), _escritorio_mock(), db)

    assert result is True
    # Apenas o agradecimento — sem query de advogados, sem alerta
    evo_mock.enviar_texto.assert_awaited_once()
    db.execute.assert_awaited_once()  # só a query de NPS, não a de advogados


# ---------------------------------------------------------------------------
# Resiliência: erro no envio não quebra o fluxo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_erro_no_envio_nao_propaga_excecao():
    """Falha no EvolutionClient não levanta exceção — nota já foi salva."""
    interacao = _interacao_nps_pendente()
    db = _mock_db_com_nps(interacao)

    evo_mock = AsyncMock()
    evo_mock.enviar_texto.side_effect = Exception("timeout")
    evo_mock.close = AsyncMock()

    with patch(
        "feature_1_ia_personalizada.services.messaging.evolution_client.EvolutionClient",
        return_value=evo_mock,
    ):
        result = await _processar_resposta_nps("4", _cliente_mock(), _escritorio_mock(), db)

    # Retorna True pois a nota foi registrada antes do erro no envio
    assert result is True
    assert interacao.satisfacao == 4
    db.commit.assert_awaited_once()
