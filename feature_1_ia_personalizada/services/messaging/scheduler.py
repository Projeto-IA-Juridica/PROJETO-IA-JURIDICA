from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from celery import current_app

# importa as SUAS tasks
from feature_1_ia_personalizada.workers.send_notifications import (
    enviar_notificacao_andamento,
    enviar_pesquisa_satisfacao,
    processar_mensagem_recebida,
)


@dataclass(frozen=True)
class Agendamento:
    task_id: str
    eta: datetime


class MessageScheduler:
    """
    Agenda tasks do send_notifications.py usando ETA.

    - agendar_notificacao_andamento
    - agendar_pesquisa_satisfacao
    - agendar_processar_mensagem
    - cancelar_agendamento
    """

    def __init__(
        self,
        fuso_horario_padrao: int = -3,
        hora_inicio_envio: int = 8,
        hora_fim_envio: int = 20,
    ) -> None:
        self.tz = timezone(timedelta(hours=fuso_horario_padrao))
        self.hora_inicio = hora_inicio_envio
        self.hora_fim = hora_fim_envio

    def _ajustar_para_horario_comercial(self, dt: datetime) -> datetime:
        """
        Ajusta para o próximo horário permitido:
          - antes do início -> hoje às HORA_INICIO_ENVIO
          - depois do fim -> amanhã às HORA_INICIO_ENVIO
          - dentro -> mantém
        """
        dt = dt.astimezone(self.tz)

        inicio = dt.replace(hour=self.hora_inicio, minute=0, second=0, microsecond=0)
        fim = dt.replace(hour=self.hora_fim, minute=0, second=0, microsecond=0)

        if dt < inicio:
            return inicio

        if dt >= fim:
            amanha = dt + timedelta(days=1)
            return amanha.replace(hour=self.hora_inicio, minute=0, second=0, microsecond=0)

        return dt

    # Agendamentos das SUAS tasks

    def agendar_notificacao_andamento(
        self,
        id_processo: int,
        descricao_andamento: str,
        horario_envio: datetime,
    ) -> Agendamento:
        eta = self._ajustar_para_horario_comercial(horario_envio)

        result = enviar_notificacao_andamento.apply_async(
            args=[id_processo, descricao_andamento],
            eta=eta,
        )
        return Agendamento(task_id=result.id, eta=eta)

    def agendar_pesquisa_satisfacao(self, horario_envio: datetime) -> Agendamento:
        eta = self._ajustar_para_horario_comercial(horario_envio)

        result = enviar_pesquisa_satisfacao.apply_async(
            args=[],
            eta=eta,
        )
        return Agendamento(task_id=result.id, eta=eta)

    def agendar_processar_mensagem(
        self,
        id_escritorio: int,
        id_cliente: int,
        mensagem: str,
        tipo: str,
        horario_envio: datetime,
    ) -> Agendamento:
        eta = self._ajustar_para_horario_comercial(horario_envio)

        result = processar_mensagem_recebida.apply_async(
            args=[id_escritorio, id_cliente, mensagem, tipo],
            eta=eta,
        )
        return Agendamento(task_id=result.id, eta=eta)

    def cancelar_agendamento(self, task_id: str) -> None:
        current_app.control.revoke(task_id, terminate=False)
