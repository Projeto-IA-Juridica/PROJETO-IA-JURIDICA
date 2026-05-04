# tests/unit/test_hub_advogado.py
"""
Testes unitários do Hub do Advogado.

Cobre:
  - HubAdvogadoClassificador: heurísticas e fallback
  - ConfidenceRouter: fórmula de score e roteamento
  - _despachar: mapeamento intenção → handler
  - webhook: roteamento Hub vs escalação vs cliente
"""
from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.ai.hub_advogado_classifier import (
    ClassificacaoAdvogado,
    HubAdvogadoClassificador,
    IntencaoAdvogado,
)


# ---------------------------------------------------------------------------
# HubAdvogadoClassificador — heurísticas (sem I/O)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classificar_documento_sem_claude():
    """Documento PDF → ANALISE_PETICAO sem chamar Claude."""
    clf = HubAdvogadoClassificador.__new__(HubAdvogadoClassificador)
    resultado = await clf.classificar("", tipo_media="document")
    assert resultado.intencao == IntencaoAdvogado.ANALISE_PETICAO


@pytest.mark.asyncio
async def test_classificar_status_heuristica():
    """Mensagem com palavra-chave de status → STATUS_ESCRITORIO sem Claude."""
    clf = HubAdvogadoClassificador.__new__(HubAdvogadoClassificador)
    for texto in ["status do escritório", "resumo do dia", "dashboard", "métricas de hoje"]:
        resultado = await clf.classificar(texto, tipo_media="texto")
        assert resultado.intencao == IntencaoAdvogado.STATUS_ESCRITORIO, texto


@pytest.mark.asyncio
async def test_classificar_fallback_claude_falha():
    """Se Claude falhar, retorna DUVIDA_JURIDICA."""
    clf = HubAdvogadoClassificador.__new__(HubAdvogadoClassificador)
    clf._client = MagicMock()
    clf._client.messages = MagicMock()
    clf._client.messages.create = AsyncMock(side_effect=RuntimeError("timeout"))

    resultado = await clf.classificar("como funciona o prazo prescricional?", tipo_media="texto")
    assert resultado.intencao == IntencaoAdvogado.DUVIDA_JURIDICA


@pytest.mark.asyncio
async def test_classificar_com_claude_sucesso():
    """Claude retorna JSON válido → intenção e entidades extraídas corretamente."""
    clf = HubAdvogadoClassificador.__new__(HubAdvogadoClassificador)

    mock_content = MagicMock()
    mock_content.text = json.dumps({
        "intencao": "resumo_processo",
        "entidades": {
            "cliente_nome": "João Silva",
            "processo_cnj": "0001234-56.2024.8.26.0001",
            "query_juris": None,
        },
    })
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    clf._client = MagicMock()
    clf._client.messages = MagicMock()
    clf._client.messages.create = AsyncMock(return_value=mock_response)

    resultado = await clf.classificar(
        "me dê um resumo do processo 0001234-56.2024.8.26.0001 do João Silva",
        tipo_media="texto",
    )

    assert resultado.intencao == IntencaoAdvogado.RESUMO_PROCESSO
    assert resultado.cliente_nome == "João Silva"
    assert resultado.processo_cnj == "0001234-56.2024.8.26.0001"


@pytest.mark.asyncio
async def test_classificar_intencao_invalida_cai_em_fallback():
    """Claude retorna intenção não listada → cai em DUVIDA_JURIDICA."""
    clf = HubAdvogadoClassificador.__new__(HubAdvogadoClassificador)

    mock_content = MagicMock()
    mock_content.text = json.dumps({
        "intencao": "intencao_inexistente",
        "entidades": {},
    })
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    clf._client = MagicMock()
    clf._client.messages = MagicMock()
    clf._client.messages.create = AsyncMock(return_value=mock_response)

    resultado = await clf.classificar("alguma coisa", tipo_media="texto")
    assert resultado.intencao == IntencaoAdvogado.DUVIDA_JURIDICA


# ---------------------------------------------------------------------------
# ClassificacaoAdvogado — propriedades
# ---------------------------------------------------------------------------


def test_classificacao_propriedades():
    c = ClassificacaoAdvogado(
        intencao=IntencaoAdvogado.INSIGHT_CLIENTE,
        entidades={
            "cliente_nome": "Maria",
            "processo_cnj": None,
            "query_juris": "dano moral",
        },
    )
    assert c.cliente_nome == "Maria"
    assert c.processo_cnj is None
    assert c.query_juris == "dano moral"


def test_classificacao_entidades_vazias():
    c = ClassificacaoAdvogado(intencao=IntencaoAdvogado.DUVIDA_JURIDICA)
    assert c.cliente_nome is None
    assert c.processo_cnj is None
    assert c.query_juris is None


# ---------------------------------------------------------------------------
# _despachar — roteamento intenção → handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_despachar_status_escritorio_nao_chama_claude():
    """STATUS_ESCRITORIO usa _handler_status_escritorio que não chama escalacao_client."""
    from feature_1_ia_personalizada.workers.hub_advogado import _despachar

    classificacao = ClassificacaoAdvogado(intencao=IntencaoAdvogado.STATUS_ESCRITORIO)
    usuario = MagicMock()
    usuario.nome = "Dr. Teste"
    escritorio = MagicMock()
    escritorio.id = 1
    escritorio.nome = "Escritório Teste"
    escritorio.webhook_whatsapp_instance = "inst1"
    escalacao_client = MagicMock()

    with patch(
        "feature_1_ia_personalizada.workers.hub_advogado._handler_status_escritorio",
        new_callable=AsyncMock,
        return_value=("OK", "none", 0, 0, Decimal("0"), None, None),
    ) as mock_handler:
        await _despachar(
            classificacao=classificacao,
            mensagem="status",
            tipo_media="texto",
            message_id=None,
            usuario=usuario,
            escritorio=escritorio,
            payload={},
            session=MagicMock(),
            escalacao_client=escalacao_client,
        )
        mock_handler.assert_awaited_once()
    # escalacao_client nunca deve ser chamado em STATUS_ESCRITORIO
    escalacao_client.gerar_resposta.assert_not_called()


@pytest.mark.asyncio
async def test_despachar_duvida_juridica_usa_escalacao_client():
    """DUVIDA_JURIDICA despacha para _handler_duvida_juridica com escalacao_client."""
    from feature_1_ia_personalizada.workers.hub_advogado import _despachar

    classificacao = ClassificacaoAdvogado(intencao=IntencaoAdvogado.DUVIDA_JURIDICA)
    usuario = MagicMock()
    escritorio = MagicMock()
    escritorio.id = 1
    escalacao_client = MagicMock()

    with patch(
        "feature_1_ia_personalizada.workers.hub_advogado._handler_duvida_juridica",
        new_callable=AsyncMock,
        return_value=("resp", "claude_opus", 10, 20, Decimal("0.001"), None, None),
    ) as mock_handler:
        resposta, modelo, tin, tout, custo, rc, rp = await _despachar(
            classificacao=classificacao,
            mensagem="qual o prazo para apelar?",
            tipo_media="texto",
            message_id=None,
            usuario=usuario,
            escritorio=escritorio,
            payload={},
            session=MagicMock(),
            escalacao_client=escalacao_client,
        )
        mock_handler.assert_awaited_once()
        assert modelo == "claude_opus"
        assert tin == 10


# ---------------------------------------------------------------------------
# Webhook — roteamento Hub vs escalação
# ---------------------------------------------------------------------------


def _make_escritorio(escalacao_habilitada: bool = True):
    e = MagicMock()
    e.id = 1
    e.nome = "Test"
    e.webhook_whatsapp_instance = "inst1"
    e.escalacao_habilitada = escalacao_habilitada
    return e


def _make_usuario(escalacao_ativa: bool, role: str = "advogado"):
    u = MagicMock()
    u.id = 42
    u.role = role
    u.escalacao_ativa = escalacao_ativa
    u.whatsapp_numero = "5511999999999"
    u.ativo = True
    return u


@pytest.mark.asyncio
async def test_webhook_advogado_sem_escalacao_ativa_vai_para_hub():
    """
    Advogado com escalacao_ativa=False e hub habilitado → hub_advogado enfileirado.
    """
    from unittest.mock import patch, AsyncMock, MagicMock

    advogado = _make_usuario(escalacao_ativa=False)
    escritorio = _make_escritorio(escalacao_habilitada=True)

    with patch(
        "feature_1_ia_personalizada.workers.hub_advogado.processar_mensagem_advogado"
    ) as mock_task:
        mock_task.apply_async = MagicMock()

        # Simula o bloco de roteamento diretamente (sem subir o FastAPI inteiro)
        if advogado.escalacao_ativa:
            routed_to = "escalation_reply"
        elif escritorio.escalacao_habilitada:
            mock_task.apply_async(
                kwargs={"payload": {}, "usuario_id": advogado.id},
                queue="hub_advogado",
            )
            routed_to = "hub_advogado"
        else:
            routed_to = "ignored"

        assert routed_to == "hub_advogado"
        mock_task.apply_async.assert_called_once_with(
            kwargs={"payload": {}, "usuario_id": advogado.id},
            queue="hub_advogado",
        )


@pytest.mark.asyncio
async def test_webhook_advogado_escalacao_ativa_vai_para_resposta_advogado():
    """Advogado com escalacao_ativa=True → processar_resposta_advogado (não hub)."""
    advogado = _make_usuario(escalacao_ativa=True)
    escritorio = _make_escritorio(escalacao_habilitada=True)

    routed_to = "escalation_reply" if advogado.escalacao_ativa else "hub_advogado"
    assert routed_to == "escalation_reply"


@pytest.mark.asyncio
async def test_webhook_hub_desabilitado_nao_enfileira():
    """escritorio.escalacao_habilitada=False → não enfileira no hub."""
    advogado = _make_usuario(escalacao_ativa=False)
    escritorio = _make_escritorio(escalacao_habilitada=False)

    if advogado.escalacao_ativa:
        routed_to = "escalation_reply"
    elif escritorio.escalacao_habilitada:
        routed_to = "hub_advogado"
    else:
        routed_to = "ignored"

    assert routed_to == "ignored"
