# feature_1_ia_personalizada/tests/integration/test_e2e_celery_orchestrator.py
from __future__ import annotations

import sys
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

# Impede que o módulo tente conectar no banco de dados real em sys imports
fake_db = MagicMock()
fake_db.async_session_factory = MagicMock()
sys.modules["shared.database.connection"] = fake_db
sys.modules["shared.database"] = fake_db

from feature_1_ia_personalizada.workers.send_notifications import processar_mensagem_recebida
from feature_1_ia_personalizada.services.ai.orchestrator import executar_fluxo_orquestrador


class TestWorkerE2E:
    """
    Testes de integração end-to-end do fluxo Celery -> Orchestrator.
    Garante que a task processar_mensagem_recebida (executada em background)
    consegue instanciar as dependências e percorrer o fluxo.
    """

    @patch("feature_1_ia_personalizada.services.ai.orchestrator.executar_fluxo_orquestrador")
    @patch("feature_1_ia_personalizada.workers.send_notifications.registrar_interacao")
    def test_worker_sucesso_invoca_orquestrador_e_salva_historico(
        self, mock_registrar, mock_orquestrador
    ):
        """
        Garante que, se o orquestrador retornar sucesso, o worker devolve 'ok'
        e chama a função de registrar a interação.
        """
        resultado_simulado = {
            "resposta": "Olá! Em que posso ajudar?",
            "intencao": "saudacao",
            "usando_fallback": False,
            "tokens_usados": {"input": 100, "output": 50},
            "processo_id": None,
        }
        mock_orquestrador.return_value = resultado_simulado

        resultado = processar_mensagem_recebida(
            id_escritorio=1,
            id_cliente=1,
            mensagem="Olá, bom dia",
            tipo="texto"
        )

        assert resultado == {"status": "ok"}
        mock_orquestrador.assert_called_once_with(
            id_escritorio=1, id_cliente=1, mensagem="Olá, bom dia", tipo="texto"
        )
        
        # Verifica se o worker registrou a interação de sucesso
        mock_registrar.assert_called_once()
        args_registro = mock_registrar.call_args.kwargs
        assert args_registro["id_cliente"] == 1
        assert args_registro["tipo"] == "mensagem_processada"
        assert args_registro["dados"] == resultado_simulado

    @patch("feature_1_ia_personalizada.services.ai.orchestrator.executar_fluxo_orquestrador")
    @patch("feature_1_ia_personalizada.workers.send_notifications.registrar_interacao")
    def test_worker_falha_propaga_erro_e_registra_falha(
        self, mock_registrar, mock_orquestrador
    ):
        """
        Garante que, se o orquestrador falhar catastroficamente (raise Exception),
        o worker registra o erro e repassa a exceção (para o Celery dar retry).
        """
        mock_orquestrador.side_effect = RuntimeError("Falha de rede severa")

        with pytest.raises(RuntimeError, match="Falha de rede severa"):
            processar_mensagem_recebida(
                id_escritorio=2,
                id_cliente=2,
                mensagem="Me ajude",
                tipo="texto"
            )

        # O worker deve ter registrado a falha
        mock_registrar.assert_called_once()
        args_registro = mock_registrar.call_args.kwargs
        assert args_registro["id_cliente"] == 2
        assert args_registro["tipo"] == "erro_processamento"
        assert "Falha de rede severa" in args_registro["dados"]["erro"]

    @patch("feature_1_ia_personalizada.services.ai.orchestrator.asyncio.run")
    @patch("feature_1_ia_personalizada.workers.send_notifications.registrar_interacao")
    def test_fluxo_completo_orquestrador_mockando_aio_run(self, mock_registrar, mock_run):
        """
        Testa a cadeia processar_mensagem_recebida -> executar_fluxo_orquestrador
        sem invocar de fato as classes do LangGraph (pois o event loop não roda).
        """
        mock_run.return_value = {
            "resposta": "Andamento do processo",
            "intencao": "status",
            "usando_fallback": False,
        }

        # Exerce o entrypoint
        result = processar_mensagem_recebida(3, 3, "status", "texto")
        assert result == {"status": "ok"}
        
        # Verifica se o asyncio.run foi invocado para criar o loop do LangGraph
        mock_run.assert_called_once()
        
        # Verifica se a interação foi salva
        mock_registrar.assert_called_once()
        args_req = mock_registrar.call_args.kwargs
        assert args_req["tipo"] == "mensagem_processada"
        assert args_req["dados"]["intencao"] == "status"
