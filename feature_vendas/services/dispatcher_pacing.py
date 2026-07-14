"""
Pacing do disparo frio (etapa 4 do roteiro) — e os cintos de segurança do chip.

Disparo automatizado no WhatsApp é o ponto de maior risco da máquina: volume
e regularidade derrubam número. Este módulo concentra TODAS as regras que
protegem o chip, porque proteger o chip é proteger a máquina inteira.

Regras:
  - Janela: só dispara em dia útil, entre 8h30 e 11h (horário de Brasília).
  - Intervalo: 3 a 12 min entre envios, aleatório (nunca cadência de relógio).
  - Cap diário com WARM-UP: chip novo começa em 5/dia e sobe gradualmente até
    o teto (25–30). Chip novo cuspindo 50 no dia 1 é ban em 48h.
  - Circuit breaker: bloqueios/denúncias no dia acima do limite → pausa tudo e
    avisa. Também para se a taxa de resposta despencar (mensagem ruim).
  - Dedup e opt-out são responsabilidade do worker (checa antes de enfileirar);
    aqui ficam só as regras de tempo e volume.

Nada de estado global: o breaker e o cap vivem no Redis (contadores por dia),
então funcionam com múltiplos workers.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

_TZ = ZoneInfo("America/Sao_Paulo")

_JANELA_INICIO = time(8, 30)
_JANELA_FIM = time(11, 0)

_INTERVALO_MIN_S = 3 * 60
_INTERVALO_MAX_S = 12 * 60

# Warm-up: cap por dia de vida do chip (índice = dias desde o 1º disparo).
# Depois do fim da lista, usa o teto.
_WARMUP = [5, 8, 12, 15, 18, 22, 25]
_TETO_DIARIO = 30

# Circuit breaker
_MAX_BLOQUEIOS_DIA = 2
_MIN_ENVIOS_P_TAXA = 15  # só avalia taxa de resposta a partir de N envios
_TAXA_RESPOSTA_MINIMA = 0.10


def _hoje() -> date:
    return datetime.now(_TZ).date()


def _k_cap(dia: date) -> str:
    return f"vendas:disparo:cap:{dia.isoformat()}"


def _k_bloqueios(dia: date) -> str:
    return f"vendas:disparo:bloqueios:{dia.isoformat()}"


def _k_breaker() -> str:
    return "vendas:disparo:breaker"


@dataclass(frozen=True)
class DecisaoDisparo:
    pode_enviar: bool
    motivo: str
    proximo_intervalo_s: int  # quanto esperar antes do próximo, se enviar agora


def dentro_da_janela(agora: datetime | None = None) -> bool:
    agora = agora or datetime.now(_TZ)
    if agora.weekday() >= 5:  # sáb/dom
        return False
    return _JANELA_INICIO <= agora.time() <= _JANELA_FIM


def cap_do_dia(dias_de_vida: int) -> int:
    if dias_de_vida < len(_WARMUP):
        return _WARMUP[dias_de_vida]
    return _TETO_DIARIO


class DispatcherPacing:
    def __init__(self, redis: Redis, chip_iniciado_em: date) -> None:
        self._redis = redis
        self._chip_iniciado_em = chip_iniciado_em

    async def _breaker_ativo(self) -> bool:
        return bool(await self._redis.get(_k_breaker()))

    async def ativar_breaker(self, motivo: str) -> None:
        # Sem TTL: só um humano rearma, depois de entender o que houve.
        await self._redis.set(_k_breaker(), motivo)

    async def registrar_bloqueio(self) -> int:
        """Chamado quando um número devolve bloqueio/denúncia. Pode disparar o breaker."""
        dia = _hoje()
        n = int(await self._redis.incr(_k_bloqueios(dia)))
        await self._redis.expire(_k_bloqueios(dia), 3 * 24 * 3600)
        if n >= _MAX_BLOQUEIOS_DIA:
            await self.ativar_breaker(f"{n} bloqueios em {dia.isoformat()}")
        return n

    async def avaliar(self, enviados_hoje: int | None = None) -> DecisaoDisparo:
        """Decisão única de 'posso disparar o próximo agora?'."""
        if await self._breaker_ativo():
            return DecisaoDisparo(False, "circuit breaker ativo (revisar manualmente)", 0)

        if not dentro_da_janela():
            return DecisaoDisparo(False, "fora da janela (dia útil, 8h30-11h)", 0)

        dia = _hoje()
        if enviados_hoje is None:
            enviados_hoje = int(await self._redis.get(_k_cap(dia)) or 0)

        dias_vida = (dia - self._chip_iniciado_em).days
        cap = cap_do_dia(max(0, dias_vida))
        if enviados_hoje >= cap:
            return DecisaoDisparo(False, f"cap diário atingido ({enviados_hoje}/{cap})", 0)

        intervalo = random.randint(_INTERVALO_MIN_S, _INTERVALO_MAX_S)
        return DecisaoDisparo(True, f"ok ({enviados_hoje}/{cap})", intervalo)

    async def registrar_envio(self) -> None:
        dia = _hoje()
        await self._redis.incr(_k_cap(dia))
        await self._redis.expire(_k_cap(dia), 3 * 24 * 3600)
