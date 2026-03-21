# feature_1_ia_personalizada/services/ai/claude_client.py
from __future__ import annotations

import asyncio
import random
import time
from decimal import Decimal
from typing import Any

import anthropic
import structlog
from prometheus_client import Counter, Histogram

from shared.config.constants import (
    MAX_TOKENS_RESPOSTA,
    MODELO_CLAUDE,
    TEMPERATURA_CLAUDE,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Métricas Prometheus
# ---------------------------------------------------------------------------

_latencia = Histogram(
    "ia_response_time_seconds",
    "Latência das chamadas ao Claude",
    labelnames=["intencao"],
)
_tokens_consumidos = Counter(
    "ia_tokens_consumed_total",
    "Total de tokens consumidos pelo Claude",
    labelnames=["tipo"],  # input | output
)
_erros = Counter(
    "ia_errors_total",
    "Total de erros nas chamadas ao Claude",
    labelnames=["tipo_erro"],
)

# ---------------------------------------------------------------------------
# Custo por token — preços claude-sonnet-4 verificados em 2026-02
# Referência: https://www.anthropic.com/pricing
# ---------------------------------------------------------------------------

_CUSTO_INPUT_POR_MILHAO = Decimal("3.00")  # USD
_CUSTO_OUTPUT_POR_MILHAO = Decimal("15.00")  # USD

_MAX_TENTATIVAS = 3
_TIMEOUT_SEGUNDOS = 30.0


def _calcular_custo(tokens_input: int, tokens_output: int) -> Decimal:
    custo_in = (Decimal(tokens_input) / Decimal(1_000_000)) * _CUSTO_INPUT_POR_MILHAO
    custo_out = (Decimal(tokens_output) / Decimal(1_000_000)) * _CUSTO_OUTPUT_POR_MILHAO
    return custo_in + custo_out


def _backoff(tentativa: int) -> float:
    """Backoff exponencial com jitter — evita thundering herd em múltiplos workers."""
    return 2**tentativa + random.uniform(0.0, 1.0)  # type: ignore[no-any-return]


def _extrair_texto(response: anthropic.types.Message) -> str:
    """Extrai o texto do primeiro bloco de tipo 'text' da resposta."""
    text_blocks = [b for b in response.content if b.type == "text"]
    if not text_blocks:
        raise RuntimeError(
            f"Claude não retornou bloco de texto. Blocos recebidos: "
            f"{[b.type for b in response.content]}"
        )
    return str(text_blocks[0].text)


async def _com_retry(coro_fn, max_tentativas: int = _MAX_TENTATIVAS) -> Any:
    """
    Executa uma coroutine com retry + backoff exponencial com jitter.
    AuthenticationError falha imediatamente (sem retry).
    """
    ultimo_erro: Exception | None = None
    for tentativa in range(1, max_tentativas + 1):
        try:
            return await coro_fn()
        except anthropic.AuthenticationError as exc:
            _erros.labels(tipo_erro="auth").inc()
            logger.error("claude_auth_error", detalhe=str(exc))
            raise RuntimeError("Chave de API do Claude inválida.") from exc
        except anthropic.RateLimitError as exc:
            _erros.labels(tipo_erro="rate_limit").inc()
            ultimo_erro = exc
            espera = _backoff(tentativa)
            logger.warning("claude_rate_limit", tentativa=tentativa, espera_s=round(espera, 2))
            await asyncio.sleep(espera)
        except anthropic.APITimeoutError as exc:
            _erros.labels(tipo_erro="timeout").inc()
            ultimo_erro = exc
            espera = _backoff(tentativa)
            logger.warning("claude_timeout", tentativa=tentativa, espera_s=round(espera, 2))
            await asyncio.sleep(espera)
        except anthropic.APIError as exc:
            _erros.labels(tipo_erro="api_error").inc()
            ultimo_erro = exc
            espera = _backoff(tentativa)
            logger.warning(
                "claude_api_error",
                tentativa=tentativa,
                status=getattr(exc, "status_code", 500),
                espera_s=round(espera, 2),
            )
            await asyncio.sleep(espera)

    logger.error(
        "claude_falhou_todas_tentativas",
        tentativas=max_tentativas,
        erro=str(ultimo_erro),
    )
    raise RuntimeError(
        f"Claude indisponível após {max_tentativas} tentativas: {ultimo_erro}"
    ) from ultimo_erro


class ClaudeClient:
    """Wrapper assíncrono sobre o SDK do Anthropic com retry, timeout e métricas."""

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=_TIMEOUT_SEGUNDOS,
        )

    async def enviar_mensagem(
        self,
        system_prompt: str,
        mensagens_historico: list[dict[str, str]],
        mensagem_usuario: str,
        intencao: str = "outro",
    ) -> dict[str, Any]:
        """
        Envia uma mensagem ao Claude e retorna a resposta com métricas.

        Args:
            system_prompt: Prompt de sistema já formatado.
            mensagens_historico: Lista de dicts [{role, content}] — conversa anterior.
            mensagem_usuario: Mensagem atual do usuário.
            intencao: Label para métricas Prometheus (status, duvida_termo, etc.).

        Returns:
            {
                "resposta": str,
                "tokens_input": int,
                "tokens_output": int,
                "custo": Decimal,
            }

        Raises:
            RuntimeError: Se todas as tentativas falharem.
        """
        messages = mensagens_historico + [{"role": "user", "content": mensagem_usuario}]
        inicio = time.perf_counter()

        async def _chamar() -> anthropic.types.Message:
            return await self._client.messages.create(
                model=MODELO_CLAUDE,
                max_tokens=MAX_TOKENS_RESPOSTA,
                temperature=TEMPERATURA_CLAUDE,
                system=system_prompt,
                messages=messages,  # type: ignore[arg-type]
            )

        response = await _com_retry(_chamar)

        duracao = time.perf_counter() - inicio
        _latencia.labels(intencao=intencao).observe(duracao)

        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        _tokens_consumidos.labels(tipo="input").inc(tokens_in)
        _tokens_consumidos.labels(tipo="output").inc(tokens_out)

        resposta_texto = _extrair_texto(response)

        logger.info(
            "claude_resposta_ok",
            intencao=intencao,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            duracao_s=round(duracao, 3),
        )

        return {
            "resposta": resposta_texto,
            "tokens_input": tokens_in,
            "tokens_output": tokens_out,
            "custo": _calcular_custo(tokens_in, tokens_out),
        }

    async def chamar_direto(
        self,
        system_prompt: str,
        mensagem: str,
        modelo: str,
        max_tokens: int,
        temperature: float = 0.3,
    ) -> dict:
        """
        Chamada com modelo e parâmetros explícitos — usada quando o caller
        precisa de um modelo diferente do padrão (ex: Haiku para CRM).

        Returns:
            {"resposta": str, "tokens_input": int, "tokens_output": int, "custo": Decimal}
        """
        async def _chamar() -> anthropic.types.Message:
            return await self._client.messages.create(
                model=modelo,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": mensagem}],
            )

        response = await _com_retry(_chamar)
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        return {
            "resposta": _extrair_texto(response),
            "tokens_input": tokens_in,
            "tokens_output": tokens_out,
            "custo": _calcular_custo(tokens_in, tokens_out),
        }

    async def classificar_intencao(self, system_prompt: str, mensagem: str) -> str:
        """
        Chamada leve usada apenas para classificar a intenção.
        max_tokens=32 — suficiente para {"intencao": "duvida_termo"} com folga.
        temperature=0.0 — determinístico para classificação.

        Returns:
            String JSON, ex: '{"intencao": "status"}'.
            O chamador é responsável por fazer json.loads().

        Raises:
            RuntimeError: Se todas as tentativas falharem.
        """

        async def _chamar() -> anthropic.types.Message:
            return await self._client.messages.create(
                model=MODELO_CLAUDE,
                max_tokens=32,
                temperature=0.0,
                system=system_prompt,
                messages=[{"role": "user", "content": mensagem}],
            )

        response = await _com_retry(_chamar)
        return _extrair_texto(response).strip()
