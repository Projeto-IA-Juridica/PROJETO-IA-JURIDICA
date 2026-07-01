from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.agendamento import Agendamento
from shared.models.disponibilidade_advogado import DisponibilidadeAdvogado

_DIAS_PT = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
]

_UTC = ZoneInfo("UTC")


@dataclass
class SlotDisponivel:
    inicio: datetime  # UTC, timezone-aware
    fim: datetime  # UTC, timezone-aware
    label: str  # ex: "Segunda-feira, 07/07 às 10h"


class AgendamentoDetector:
    """
    Busca os próximos slots livres para um escritório.

    Lógica:
      1. Carrega disponibilidades ativas do escritório.
      2. Itera dias à frente (até _MAX_DIAS_FRENTE) gerando candidatos de
         duracao_min minutos dentro de cada janela [hora_inicio, hora_fim].
      3. Para cada candidato, consulta conflitos com agendamentos em
         status 'confirmado' ou 'aguardando_advogado' no mesmo intervalo.
      4. Retorna os primeiros num_slots livres.
    """

    _MAX_DIAS_FRENTE = 30

    def __init__(
        self,
        db: AsyncSession,
        escritorio_id: int,
        timezone_str: str = "America/Sao_Paulo",
    ) -> None:
        self._db = db
        self._escritorio_id = escritorio_id
        self._tz = ZoneInfo(timezone_str)

    async def buscar_slots(
        self,
        num_slots: int = 3,
        duracao_min: int = 60,
    ) -> list[SlotDisponivel]:
        disponibilidades = await self._carregar_disponibilidades()
        if not disponibilidades:
            return []

        disp_por_dia: dict[int, DisponibilidadeAdvogado] = {
            d.dia_semana: d for d in disponibilidades
        }

        slots: list[SlotDisponivel] = []
        hoje = datetime.now(self._tz).date()

        for delta in range(1, self._MAX_DIAS_FRENTE + 1):
            if len(slots) >= num_slots:
                break

            dia = hoje + timedelta(days=delta)
            weekday = dia.weekday()  # 0=segunda … 5=sábado; 6=domingo (ignorado)

            if weekday not in disp_por_dia:
                continue

            disp = disp_por_dia[weekday]
            candidatos = self._gerar_candidatos(dia, disp, duracao_min)

            for inicio_utc, fim_utc in candidatos:
                if len(slots) >= num_slots:
                    break
                if not await self._tem_conflito(inicio_utc, fim_utc):
                    label = self._formatar_label(inicio_utc)
                    slots.append(SlotDisponivel(inicio=inicio_utc, fim=fim_utc, label=label))

        return slots

    async def _carregar_disponibilidades(self) -> list[DisponibilidadeAdvogado]:
        stmt = select(DisponibilidadeAdvogado).where(
            DisponibilidadeAdvogado.escritorio_id == self._escritorio_id,
            DisponibilidadeAdvogado.ativo.is_(True),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    def _gerar_candidatos(
        self,
        dia: date,
        disp: DisponibilidadeAdvogado,
        duracao_min: int,
    ) -> list[tuple[datetime, datetime]]:
        """Gera pares (inicio_utc, fim_utc) para o dia dentro da janela de disponibilidade."""
        delta = timedelta(minutes=duracao_min)
        # Combina data local + hora local e localiza no tz do escritório
        atual = datetime.combine(dia, disp.hora_inicio).replace(tzinfo=self._tz)
        fim_janela = datetime.combine(dia, disp.hora_fim).replace(tzinfo=self._tz)

        candidatos: list[tuple[datetime, datetime]] = []
        while atual + delta <= fim_janela:
            fim_slot = atual + delta
            candidatos.append(
                (
                    atual.astimezone(_UTC),
                    fim_slot.astimezone(_UTC),
                )
            )
            atual = fim_slot
        return candidatos

    async def _tem_conflito(self, inicio_utc: datetime, fim_utc: datetime) -> bool:
        """Retorna True se há agendamento confirmado/pendente que sobrepõe o slot."""
        stmt = select(Agendamento.id).where(
            Agendamento.escritorio_id == self._escritorio_id,
            Agendamento.status.in_(["confirmado", "aguardando_advogado"]),
            and_(
                Agendamento.data_hora_inicio.isnot(None),
                Agendamento.data_hora_fim.isnot(None),
                # Sobreposição: início do existente < fim do candidato E fim do existente > início
                or_(
                    and_(
                        Agendamento.data_hora_inicio < fim_utc,
                        Agendamento.data_hora_fim > inicio_utc,
                    )
                ),
            ),
        )
        result = await self._db.execute(stmt)
        return result.first() is not None

    def _formatar_label(self, inicio_utc: datetime) -> str:
        local = inicio_utc.astimezone(self._tz)
        nome_dia = _DIAS_PT[local.weekday()]
        return f"{nome_dia}, {local.strftime('%d/%m')} às {local.strftime('%Hh')}"
