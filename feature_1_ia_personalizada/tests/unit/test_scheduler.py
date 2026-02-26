# feature_1_ia_personalizada/tests/unit/test_scheduler.py
"""
Testes do MessageScheduler (services/messaging/scheduler.py).

Estratégia:
  - _ajustar_para_horario_comercial: testado nos 3 casos (antes, depois e dentro do horário).
  - Métodos agendar_*: apply_async das tasks é mockado; verifica args, eta e Agendamento retornado.
  - cancelar_agendamento: verifica chamada ao current_app.control.revoke.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.messaging.scheduler import (
    Agendamento,
    MessageScheduler,
)

_TZ_BR = timezone(timedelta(hours=-3))


def _dt(hora: int, minuto: int = 0) -> datetime:
    """Cria um datetime hoje no fuso Brasil com a hora especificada."""
    agora = datetime.now(tz=_TZ_BR)
    return agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)


def _scheduler(**kwargs) -> MessageScheduler:
    return MessageScheduler(
        fuso_horario_padrao=kwargs.get("fuso", -3),
        hora_inicio_envio=kwargs.get("inicio", 8),
        hora_fim_envio=kwargs.get("fim", 20),
    )


# ---------------------------------------------------------------------------
# _ajustar_para_horario_comercial
# ---------------------------------------------------------------------------

class TestAjustarHorarioComercial:
    def test_dentro_do_horario_mantem_hora(self):
        sched = _scheduler()
        entrada = _dt(hora=10, minuto=30)
        resultado = sched._ajustar_para_horario_comercial(entrada)
        assert resultado.hour == 10
        assert resultado.minute == 30

    def test_antes_do_inicio_ajusta_para_inicio_hoje(self):
        sched = _scheduler()
        entrada = _dt(hora=6, minuto=0)  # antes das 8h
        resultado = sched._ajustar_para_horario_comercial(entrada)
        assert resultado.hour == 8
        assert resultado.minute == 0
        assert resultado.date() == entrada.astimezone(_TZ_BR).date()

    def test_exatamente_no_inicio_mantem(self):
        sched = _scheduler()
        entrada = _dt(hora=8, minuto=0)
        resultado = sched._ajustar_para_horario_comercial(entrada)
        assert resultado.hour == 8
        assert resultado.date() == entrada.astimezone(_TZ_BR).date()

    def test_depois_do_fim_ajusta_para_amanha(self):
        sched = _scheduler()
        entrada = _dt(hora=21, minuto=0)  # depois das 20h
        resultado = sched._ajustar_para_horario_comercial(entrada)
        amanha = (entrada.astimezone(_TZ_BR) + timedelta(days=1)).date()
        assert resultado.hour == 8
        assert resultado.date() == amanha

    def test_exatamente_no_fim_ajusta_para_amanha(self):
        sched = _scheduler()
        entrada = _dt(hora=20, minuto=0)  # >= 20h deve ir para amanhã
        resultado = sched._ajustar_para_horario_comercial(entrada)
        amanha = (entrada.astimezone(_TZ_BR) + timedelta(days=1)).date()
        assert resultado.date() == amanha
        assert resultado.hour == 8

    def test_horario_personalizado_inicio_9_fim_18(self):
        sched = _scheduler(inicio=9, fim=18)
        dentro = _dt(hora=14)
        assert sched._ajustar_para_horario_comercial(dentro).hour == 14

        fora_antes = _dt(hora=7)
        assert sched._ajustar_para_horario_comercial(fora_antes).hour == 9

        fora_depois = _dt(hora=19)
        resultado = sched._ajustar_para_horario_comercial(fora_depois)
        assert resultado.hour == 9
        amanha = (fora_depois.astimezone(_TZ_BR) + timedelta(days=1)).date()
        assert resultado.date() == amanha


# ---------------------------------------------------------------------------
# agendar_notificacao_andamento
# ---------------------------------------------------------------------------

class TestAgendarNotificacaoAndamento:
    def test_chama_apply_async_com_args_corretos(self):
        sched = _scheduler()
        mock_result = MagicMock()
        mock_result.id = "task-uuid-andamento"

        with patch(
            "feature_1_ia_personalizada.services.messaging.scheduler"
            ".enviar_notificacao_andamento"
        ) as mock_task:
            mock_task.apply_async.return_value = mock_result
            horario = _dt(hora=10)
            agendamento = sched.agendar_notificacao_andamento(
                id_processo=42,
                descricao_andamento="Audiência marcada.",
                horario_envio=horario,
            )

        mock_task.apply_async.assert_called_once()
        call_kwargs = mock_task.apply_async.call_args
        assert call_kwargs.kwargs["args"] == [42, "Audiência marcada."]
        assert "eta" in call_kwargs.kwargs

    def test_retorna_agendamento_com_task_id(self):
        sched = _scheduler()
        mock_result = MagicMock()
        mock_result.id = "abc-123"

        with patch(
            "feature_1_ia_personalizada.services.messaging.scheduler"
            ".enviar_notificacao_andamento"
        ) as mock_task:
            mock_task.apply_async.return_value = mock_result
            agendamento = sched.agendar_notificacao_andamento(
                id_processo=1,
                descricao_andamento="Sentença proferida.",
                horario_envio=_dt(hora=14),
            )

        assert isinstance(agendamento, Agendamento)
        assert agendamento.task_id == "abc-123"
        assert isinstance(agendamento.eta, datetime)

    def test_eta_e_ajustada_para_horario_comercial(self):
        sched = _scheduler()
        mock_result = MagicMock()
        mock_result.id = "x"

        with patch(
            "feature_1_ia_personalizada.services.messaging.scheduler"
            ".enviar_notificacao_andamento"
        ) as mock_task:
            mock_task.apply_async.return_value = mock_result
            agendamento = sched.agendar_notificacao_andamento(
                id_processo=1,
                descricao_andamento="Teste",
                horario_envio=_dt(hora=3),  # fora do horário
            )

        assert agendamento.eta.hour == 8


# ---------------------------------------------------------------------------
# agendar_pesquisa_satisfacao
# ---------------------------------------------------------------------------

class TestAgendarPesquisaSatisfacao:
    def test_chama_apply_async_sem_args_de_processo(self):
        sched = _scheduler()
        mock_result = MagicMock()
        mock_result.id = "pesq-uuid"

        with patch(
            "feature_1_ia_personalizada.services.messaging.scheduler"
            ".enviar_pesquisa_satisfacao"
        ) as mock_task:
            mock_task.apply_async.return_value = mock_result
            agendamento = sched.agendar_pesquisa_satisfacao(horario_envio=_dt(hora=15))

        mock_task.apply_async.assert_called_once()
        assert agendamento.task_id == "pesq-uuid"

    def test_retorna_agendamento_valido(self):
        sched = _scheduler()
        mock_result = MagicMock()
        mock_result.id = "pesq-222"

        with patch(
            "feature_1_ia_personalizada.services.messaging.scheduler"
            ".enviar_pesquisa_satisfacao"
        ) as mock_task:
            mock_task.apply_async.return_value = mock_result
            ag = sched.agendar_pesquisa_satisfacao(horario_envio=_dt(hora=11))

        assert isinstance(ag, Agendamento)
        assert ag.task_id == "pesq-222"


# ---------------------------------------------------------------------------
# agendar_processar_mensagem
# ---------------------------------------------------------------------------

class TestAgendarProcessarMensagem:
    def test_chama_apply_async_com_todos_args(self):
        sched = _scheduler()
        mock_result = MagicMock()
        mock_result.id = "msg-uuid"

        with patch(
            "feature_1_ia_personalizada.services.messaging.scheduler"
            ".processar_mensagem_recebida"
        ) as mock_task:
            mock_task.apply_async.return_value = mock_result
            agendamento = sched.agendar_processar_mensagem(
                id_escritorio=5,
                id_cliente=99,
                mensagem="Qual o status do meu processo?",
                tipo="chat",
                horario_envio=_dt(hora=9),
            )

        call_kwargs = mock_task.apply_async.call_args
        assert call_kwargs.kwargs["args"] == [5, 99, "Qual o status do meu processo?", "chat"]
        assert agendamento.task_id == "msg-uuid"

    def test_eta_passada_corretamente(self):
        sched = _scheduler()
        mock_result = MagicMock()
        mock_result.id = "y"
        horario = _dt(hora=12, minuto=30)

        with patch(
            "feature_1_ia_personalizada.services.messaging.scheduler"
            ".processar_mensagem_recebida"
        ) as mock_task:
            mock_task.apply_async.return_value = mock_result
            ag = sched.agendar_processar_mensagem(
                id_escritorio=1,
                id_cliente=1,
                mensagem="Oi",
                tipo="whatsapp",
                horario_envio=horario,
            )

        eta_usado = mock_task.apply_async.call_args.kwargs["eta"]
        assert eta_usado == ag.eta


# ---------------------------------------------------------------------------
# cancelar_agendamento
# ---------------------------------------------------------------------------

class TestCancelarAgendamento:
    def test_chama_revoke_com_task_id(self):
        sched = _scheduler()

        with patch(
            "feature_1_ia_personalizada.services.messaging.scheduler.current_app"
        ) as mock_app:
            sched.cancelar_agendamento("task-para-cancelar")

        mock_app.control.revoke.assert_called_once_with(
            "task-para-cancelar", terminate=False
        )

    def test_nao_termina_processo_em_execucao(self):
        sched = _scheduler()

        with patch(
            "feature_1_ia_personalizada.services.messaging.scheduler.current_app"
        ) as mock_app:
            sched.cancelar_agendamento("qualquer-id")

        _, kwargs = mock_app.control.revoke.call_args
        assert kwargs.get("terminate") is False
