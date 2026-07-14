"""
Wrapper do EvolutionClient com o campo `delay` do sendText.

A Evolution aceita `delay` (ms) no payload de sendText: ela exibe o presence
"composing" (o "digitando..." do WhatsApp) por esse tempo e só então entrega
a mensagem. Usar o delay nativo, em vez de nós dispararmos presence + sleep +
send separados, mantém o "digitando" e o envio atômicos — se o processo cair
no meio, não fica um "digitando..." fantasma preso na tela do lead.

Este wrapper vive em feature_vendas e não toca o EvolutionClient do produto
(dependência de mão única: vendas usa o produto, nunca o contrário).
"""

from __future__ import annotations

from typing import Any

from feature_1_ia_personalizada.services.messaging.evolution_client import EvolutionClient


class EvolutionHumano(EvolutionClient):
    """EvolutionClient que suporta delay_ms (presence "digitando") no envio."""

    async def enviar_texto(  # type: ignore[override]
        self,
        instance: str,
        numero: str,
        texto: str,
        delay_ms: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"number": numero, "text": texto}
        if delay_ms and delay_ms > 0:
            # Cap defensivo: a Evolution ignora ou trava com valores absurdos;
            # 8s é mais que suficiente para o balão mais longo que enviamos.
            payload["delay"] = min(int(delay_ms), 8000)
            payload["presence"] = "composing"
        return await self._request_com_retry("POST", f"/message/sendText/{instance}", json=payload)
