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
_cache_tokens = Counter(
    "ia_cache_tokens_total",
    "Tokens de prompt caching do Claude",
    labelnames=["tipo"],  # write | read
)
_erros = Counter(
    "ia_errors_total",
    "Total de erros nas chamadas ao Claude",
    labelnames=["tipo_erro"],
)

# ---------------------------------------------------------------------------
# Custo por token — claude-sonnet-4-20250514 (verificado 2026-05)
# Prompt caching: write custa 25% a mais que input; read custa 10% do input.
# ---------------------------------------------------------------------------

_CUSTO_INPUT_POR_MILHAO = Decimal("3.00")
_CUSTO_OUTPUT_POR_MILHAO = Decimal("15.00")
_CUSTO_CACHE_WRITE_POR_MILHAO = Decimal("3.75")  # 125% do input
_CUSTO_CACHE_READ_POR_MILHAO = Decimal("0.30")  # 10% do input

_MAX_TENTATIVAS = 3
_TIMEOUT_SEGUNDOS = 30.0


def _calcular_custo(
    tokens_input: int,
    tokens_output: int,
    tokens_cache_write: int = 0,
    tokens_cache_read: int = 0,
) -> Decimal:
    return (
        Decimal(tokens_input) / Decimal(1_000_000) * _CUSTO_INPUT_POR_MILHAO
        + Decimal(tokens_output) / Decimal(1_000_000) * _CUSTO_OUTPUT_POR_MILHAO
        + Decimal(tokens_cache_write) / Decimal(1_000_000) * _CUSTO_CACHE_WRITE_POR_MILHAO
        + Decimal(tokens_cache_read) / Decimal(1_000_000) * _CUSTO_CACHE_READ_POR_MILHAO
    )


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


def _extrair_uso(response: anthropic.types.Message) -> tuple[int, int, int, int]:
    """Retorna (input, output, cache_write, cache_read) tokens da resposta."""
    usage = response.usage
    return (
        usage.input_tokens,
        usage.output_tokens,
        getattr(usage, "cache_creation_input_tokens", 0) or 0,
        getattr(usage, "cache_read_input_tokens", 0) or 0,
    )


def _registrar_uso(
    tokens_in: int,
    tokens_out: int,
    cache_write: int,
    cache_read: int,
    intencao: str,
    duracao: float,
) -> None:
    _latencia.labels(intencao=intencao).observe(duracao)
    _tokens_consumidos.labels(tipo="input").inc(tokens_in)
    _tokens_consumidos.labels(tipo="output").inc(tokens_out)
    if cache_write:
        _cache_tokens.labels(tipo="write").inc(cache_write)
    if cache_read:
        _cache_tokens.labels(tipo="read").inc(cache_read)
    logger.info(
        "claude_resposta_ok",
        intencao=intencao,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        cache_write=cache_write,
        cache_read=cache_read,
        duracao_s=round(duracao, 3),
    )


async def _com_retry(coro_fn: Any, max_tentativas: int = _MAX_TENTATIVAS) -> Any:
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


def _system_com_cache(system_prompt: str) -> list[dict[str, Any]]:
    """Converte system prompt em bloco cacheável (economiza ~90% nos tokens de input)."""
    return [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]


def _historico_com_cache(
    mensagens_historico: list[dict[str, str]],
    mensagem_usuario: str,
) -> list[Any]:
    """
    Monta a lista de mensagens para a API com cache_control no último turn do histórico.

    O marcador no último turn do histórico faz com que, na chamada seguinte,
    toda aquela conversa seja lida do cache — sem recusto de input.
    """
    messages: list[Any] = []

    for i, msg in enumerate(mensagens_historico):
        if i == len(mensagens_historico) - 1:
            # Último turn do histórico vira checkpoint de cache para a próxima chamada
            messages.append(
                {
                    "role": msg["role"],
                    "content": [
                        {
                            "type": "text",
                            "text": msg["content"],
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            )
        else:
            messages.append(msg)

    messages.append({"role": "user", "content": mensagem_usuario})
    return messages


class ClaudeClient:
    """Wrapper assíncrono sobre o SDK do Anthropic com retry, timeout, métricas e prompt caching."""

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

        O system prompt e o histórico de conversa são cacheados automaticamente:
        - System prompt: cacheado em toda chamada (payback após 1ª requisição).
        - Histórico: o último turn é marcado para cache — na próxima chamada,
          toda a conversa anterior vira cache hit (~90% de desconto nesses tokens).

        Returns:
            {
                "resposta": str,
                "tokens_input": int,
                "tokens_output": int,
                "tokens_cache_write": int,
                "tokens_cache_read": int,
                "custo": Decimal,
            }
        """
        system_blocks = _system_com_cache(system_prompt)
        messages = _historico_com_cache(mensagens_historico, mensagem_usuario)
        inicio = time.perf_counter()

        async def _chamar() -> anthropic.types.Message:
            return await self._client.messages.create(
                model=MODELO_CLAUDE,
                max_tokens=MAX_TOKENS_RESPOSTA,
                system=system_blocks,  # type: ignore[arg-type]
                messages=messages,
            )

        response = await _com_retry(_chamar)
        duracao = time.perf_counter() - inicio

        tokens_in, tokens_out, cache_write, cache_read = _extrair_uso(response)
        _registrar_uso(tokens_in, tokens_out, cache_write, cache_read, intencao, duracao)

        return {
            "resposta": _extrair_texto(response),
            "tokens_input": tokens_in,
            "tokens_output": tokens_out,
            "tokens_cache_write": cache_write,
            "tokens_cache_read": cache_read,
            "custo": _calcular_custo(tokens_in, tokens_out, cache_write, cache_read),
        }

    async def chamar_direto(
        self,
        system_prompt: str,
        mensagem: str,
        modelo: str,
        max_tokens: int,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """
        Chamada com modelo e parâmetros explícitos — usada quando o caller
        precisa de um modelo diferente do padrão (ex: Haiku para CRM).

        Returns:
            {"resposta": str, "tokens_input": int, "tokens_output": int,
             "tokens_cache_write": int, "tokens_cache_read": int, "custo": Decimal}
        """
        system_blocks = _system_com_cache(system_prompt)

        async def _chamar() -> anthropic.types.Message:
            return await self._client.messages.create(
                model=modelo,
                max_tokens=max_tokens,
                system=system_blocks,  # type: ignore[arg-type]
                messages=[{"role": "user", "content": mensagem}],
            )

        response = await _com_retry(_chamar)
        tokens_in, tokens_out, cache_write, cache_read = _extrair_uso(response)
        return {
            "resposta": _extrair_texto(response),
            "tokens_input": tokens_in,
            "tokens_output": tokens_out,
            "tokens_cache_write": cache_write,
            "tokens_cache_read": cache_read,
            "custo": _calcular_custo(tokens_in, tokens_out, cache_write, cache_read),
        }

    async def classificar_intencao(self, system_prompt: str, mensagem: str) -> str:
        """
        Chamada leve usada apenas para classificar a intenção.
        max_tokens=32 — suficiente para {"intencao": "duvida_termo"} com folga.
        temperature=0.0 — determinístico para classificação.

        O system prompt de classificação é cacheado: como é chamado a cada mensagem,
        o cache hit paga a diferença já na segunda requisição do dia.

        Returns:
            String JSON, ex: '{"intencao": "status"}'.
        """
        system_blocks = _system_com_cache(system_prompt)

        async def _chamar() -> anthropic.types.Message:
            return await self._client.messages.create(
                model=MODELO_CLAUDE,
                max_tokens=32,
                system=system_blocks,  # type: ignore[arg-type]
                messages=[{"role": "user", "content": mensagem}],
            )

        response = await _com_retry(_chamar)
        return _extrair_texto(response).strip()
