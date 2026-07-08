from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


# Exceções


class EvolutionError(Exception):
    """Erro base de integração com Evolution API."""


class EvolutionTimeoutError(EvolutionError):
    """Timeout ao chamar Evolution API."""


class EvolutionOfflineError(EvolutionError):
    """Instância offline / indisponível."""


class EvolutionRequestError(EvolutionError):
    """Erro HTTP/Resposta inválida."""


# Config


@dataclass(frozen=True)
class EvolutionConfig:
    base_url: str
    api_key: str
    timeout_seconds: float = 15.0
    max_tentativas: int = 3
    backoff_base_seconds: float = 0.7  # tempo base do backoff (ex.: 0.7, 1.4, 2.8)
    backoff_max_seconds: float = 4.0


# Client


class EvolutionClient:
    """
    Cliente async para Evolution API (WhatsApp).
    Implementa:
    - timeout de 15s
    - retry com backoff (3 tentativas)
    - tratamento de erros (conexão, timeout, instância offline)
    """

    def __init__(self, base_url: str, api_key: str, timeout_seconds: float = 15.0) -> None:
        base_url = base_url.rstrip("/")
        self._config = EvolutionConfig(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "apikey": api_key,  # muita gente usa 'apikey' na Evolution; se o seu for 'Authorization', me fala
        }

        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            headers=self._headers,
            timeout=httpx.Timeout(self._config.timeout_seconds),
        )

    async def close(self) -> None:
        await self._client.aclose()

        # Helpers (retry/backoff)

    async def _request_com_retry(
        self,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ultima_excecao: Exception | None = None

        for tentativa in range(1, self._config.max_tentativas + 1):
            try:
                resp = await self._client.request(method, url, json=json, params=params)

                # 2xx ok
                if 200 <= resp.status_code < 300:
                    if resp.content:
                        return resp.json()  # type: ignore[no-any-return]
                    return {}

                # alguns cenários comuns: instância offline / indisponível
                texto = ""
                try:
                    texto = resp.text
                except Exception:
                    texto = "<sem corpo>"

                # Se você souber exatamente o status/erro que a sua Evolution usa para offline, dá pra refinar aqui.
                if resp.status_code in (408, 409, 423, 424, 503):
                    raise EvolutionOfflineError(
                        f"Instância possivelmente offline: HTTP {resp.status_code} | {texto}"
                    )

                raise EvolutionRequestError(f"Erro HTTP {resp.status_code} | {texto}")

            except httpx.ReadTimeout as e:
                ultima_excecao = e
                logger.warning(
                    "evolution_timeout",
                    tentativa=tentativa,
                    max_tentativas=self._config.max_tentativas,
                    erro=str(e),
                )
                if tentativa == self._config.max_tentativas:
                    raise EvolutionTimeoutError("Timeout ao chamar Evolution API") from e

            except httpx.ConnectError as e:
                ultima_excecao = e
                logger.warning(
                    "evolution_connect_error",
                    tentativa=tentativa,
                    max_tentativas=self._config.max_tentativas,
                    erro=str(e),
                )
                if tentativa == self._config.max_tentativas:
                    raise EvolutionRequestError("Falha de conexão com Evolution API") from e

            except EvolutionOfflineError as e:
                ultima_excecao = e
                logger.warning(
                    "evolution_instancia_offline",
                    tentativa=tentativa,
                    max_tentativas=self._config.max_tentativas,
                    erro=str(e),
                )
                if tentativa == self._config.max_tentativas:
                    raise

            except httpx.HTTPError as e:
                ultima_excecao = e
                logger.warning(
                    "evolution_http_error",
                    tentativa=tentativa,
                    max_tentativas=self._config.max_tentativas,
                    erro=str(e),
                )
                if tentativa == self._config.max_tentativas:
                    raise EvolutionRequestError("Erro HTTP ao chamar Evolution API") from e

            # backoff antes da próxima tentativa
            await asyncio.sleep(self._calcular_backoff(tentativa))

        # não deve chegar aqui
        raise EvolutionRequestError("Falha inesperada em _request_com_retry") from ultima_excecao

    def _calcular_backoff(self, tentativa: int) -> float:
        # tentativa=1 => backoff_base*1, tentativa=2 => *2, tentativa=3 => *4
        delay = self._config.backoff_base_seconds * (2 ** (tentativa - 1))
        return float(min(delay, self._config.backoff_max_seconds))

    # Métodos do enunciado

    async def enviar_texto(self, instance: str, numero: str, texto: str) -> dict[str, Any]:
        """
        POST /message/sendText/{instance}
        """
        payload = {
            "number": numero,
            "text": texto,
        }
        return await self._request_com_retry("POST", f"/message/sendText/{instance}", json=payload)

    async def marcar_como_lida(self, instance: str, numero: str, message_id: str) -> dict[str, Any]:
        """
        POST /chat/markMessageAsRead/{instance}
        Marca uma mensagem específica como lida (tick azul).
        """
        payload = {
            "readMessages": [
                {
                    "remoteJid": numero if "@" in numero else f"{numero}@s.whatsapp.net",
                    "fromMe": False,
                    "id": message_id,
                }
            ]
        }
        return await self._request_com_retry(
            "POST", f"/chat/markMessageAsRead/{instance}", json=payload
        )

    async def enviar_botoes(
        self,
        instance: str,
        numero: str,
        texto: str,
        botoes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Envia mensagem com botões interativos.
        OBS: o formato exato do payload pode variar conforme sua Evolution.
        """
        payload = {
            "number": numero,
            "text": texto,
            "buttons": botoes,
        }
        return await self._request_com_retry(
            "POST", f"/message/sendButtons/{instance}", json=payload
        )

    async def enviar_lista(
        self,
        instance: str,
        numero: str,
        titulo: str,
        secoes: list[dict[str, Any]],
        texto: str = "",
    ) -> dict[str, Any]:
        """
        Envia mensagem com lista de opções.
        OBS: o endpoint também pode variar conforme sua versão.
        """
        payload = {
            "number": numero,
            "title": titulo,
            "text": texto,
            "sections": secoes,
        }
        return await self._request_com_retry("POST", f"/message/sendList/{instance}", json=payload)

    async def buscar_status_mensagem(self, instance: str, message_id: str) -> str:
        """
        Verifica se foi entregue/lida.
        Endpoint varia muito; deixei como exemplo.
        """
        data = await self._request_com_retry(
            "GET", f"/message/status/{instance}", params={"messageId": message_id}
        )

        # tenta padronizar retorno
        status = (
            data.get("status")
            or data.get("message", {}).get("status")
            or data.get("data", {}).get("status")
            or "unknown"
        )
        return str(status)

    async def baixar_media(self, instance: str, message_id: str) -> bytes:
        """
        Baixa áudio/imagem recebida.
        Muitas Evolutions têm endpoint que retorna base64 ou URL.
        Aqui deixo como "GET bytes" (se seu endpoint retornar JSON/base64, me fala que eu ajusto).
        """
        try:
            resp = await self._client.get(
                f"/message/downloadMedia/{instance}", params={"messageId": message_id}
            )
            if 200 <= resp.status_code < 300:
                return resp.content
            raise EvolutionRequestError(
                f"Erro ao baixar mídia: HTTP {resp.status_code} | {resp.text}"
            )
        except httpx.ReadTimeout as e:
            raise EvolutionTimeoutError("Timeout ao baixar mídia") from e
        except httpx.HTTPError as e:
            raise EvolutionRequestError("Erro HTTP ao baixar mídia") from e
