# feature_1_ia_personalizada/services/ai/harvey_client.py
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

import httpx
import pybreaker
import structlog

from shared.config.settings import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Circuit breaker — mesmo padrão do DataJud
# Após 3 falhas consecutivas, abre por 120 segundos.
# ---------------------------------------------------------------------------
_harvey_cb = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=120,
    name="harvey",
)

# ---------------------------------------------------------------------------
# Custo estimado Harvey (placeholder — confirmar com equipe Harvey)
# ---------------------------------------------------------------------------
_CUSTO_INPUT_POR_MILHAO = Decimal("15.00")   # USD — raciocínio denso
_CUSTO_OUTPUT_POR_MILHAO = Decimal("60.00")  # USD


def _calcular_custo(tokens_input: int, tokens_output: int) -> Decimal:
    custo_in = (Decimal(tokens_input) / Decimal(1_000_000)) * _CUSTO_INPUT_POR_MILHAO
    custo_out = (Decimal(tokens_output) / Decimal(1_000_000)) * _CUSTO_OUTPUT_POR_MILHAO
    return custo_in + custo_out


def _backoff(tentativa: int) -> float:
    return 2**tentativa + random.uniform(0.0, 1.0)


# ---------------------------------------------------------------------------
# Enums e dataclasses públicos
# ---------------------------------------------------------------------------

class TipoAnaliseHarvey(str, Enum):
    ANALISE_COMPLETA = "analise_completa"
    PONTOS_FRACOS = "pontos_fracos"
    JURISPRUDENCIA_RELACIONADA = "jurisprudencia_relacionada"
    RESUMO_EXECUTIVO = "resumo_executivo"
    CONTRA_ARGUMENTOS = "contra_argumentos"


@dataclass
class HarveyResponse:
    conteudo: str
    tokens_input: int
    tokens_output: int
    custo_estimado: Decimal
    modelo: str
    latencia_ms: int


@dataclass
class AnaliseHarveyResponse:
    tipo_peca: str
    pontos_fortes: list[str]
    vulnerabilidades: list[str]
    argumentos_ausentes: list[str]
    precedentes_relevantes: list[str]
    score_geral: int                    # 0-100
    sugestoes: list[str] = field(default_factory=list)


@dataclass
class Jurisprudencia:
    ementa: str
    tribunal: str
    numero_processo: str
    data_julgamento: str
    aplicabilidade: str                 # "FAVORAVEL" | "DESFAVORAVEL" | "NEUTRO"
    relevancia_score: float


# ---------------------------------------------------------------------------
# Exceção pública — callers tratam com fallback para Claude
# ---------------------------------------------------------------------------

class HarveyUnavailableError(RuntimeError):
    """Levantada quando o circuit breaker está aberto ou Harvey retorna erro fatal."""


# ---------------------------------------------------------------------------
# Cliente principal
# ---------------------------------------------------------------------------

class HarveyClient:
    """
    Cliente assíncrono para a Harvey AI.

    Usa httpx.AsyncClient com timeout configurável, retry com backoff
    exponencial e circuit breaker (pybreaker) — mesmo padrão do DataJud.

    Quando o circuit breaker abre, levanta HarveyUnavailableError para que
    o chamador possa usar Claude como fallback.
    """

    MODELO_HARVEY = settings.HARVEY_MODELO
    MAX_TOKENS = 2048
    TIMEOUT = settings.HARVEY_TIMEOUT
    MAX_RETRIES = 3

    def __init__(self) -> None:
        if not settings.HARVEY_API_KEY:
            logger.warning(
                "harvey_api_key_ausente",
                msg="HARVEY_API_KEY vazia — client instanciado mas chamadas vão falhar",
            )

        self._base_url = settings.HARVEY_API_URL.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {settings.HARVEY_API_KEY}",
            "Content-Type": "application/json",
        }
        # Client SÍNCRONO — usado exclusivamente dentro de run_in_executor,
        # para que o pybreaker (síncrono) possa envolver a chamada sem cruzar
        # event loops. Nunca chamar self._sync_client fora de um executor.
        self._sync_client = httpx.Client(
            timeout=httpx.Timeout(self.TIMEOUT),
            headers=self._headers,
        )

    # ------------------------------------------------------------------
    # Método principal — resposta jurídica livre
    # ------------------------------------------------------------------

    async def gerar_resposta(
        self,
        system_prompt: str,
        mensagem_usuario: str,
        contexto_rag: str = "",
        escritorio_id: int | None = None,
    ) -> HarveyResponse:
        """
        Envia uma pergunta para Harvey e retorna a resposta com métricas.

        Raises:
            HarveyUnavailableError: Se circuit breaker aberto ou falha irrecuperável.
        """
        payload = {
            "model": self.MODELO_HARVEY,
            "max_tokens": self.MAX_TOKENS,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"{contexto_rag}\n\n{mensagem_usuario}".strip() if contexto_rag else mensagem_usuario,
                },
            ],
        }

        inicio = time.perf_counter()
        dados = await self._post_com_retry("/chat/completions", payload)
        latencia_ms = int((time.perf_counter() - inicio) * 1000)

        conteudo, tokens_in, tokens_out = self._extrair_resposta(dados)
        custo = _calcular_custo(tokens_in, tokens_out)

        logger.info(
            "harvey_resposta_ok",
            escritorio_id=escritorio_id,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            latencia_ms=latencia_ms,
            custo_usd=str(custo),
        )

        return HarveyResponse(
            conteudo=conteudo,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            custo_estimado=custo,
            modelo=self.MODELO_HARVEY,
            latencia_ms=latencia_ms,
        )

    # ------------------------------------------------------------------
    # Análise de petição PDF
    # ------------------------------------------------------------------

    async def analisar_peticao(
        self,
        conteudo_peticao: str,
        tipo_analise: TipoAnaliseHarvey = TipoAnaliseHarvey.ANALISE_COMPLETA,
        contexto_processo: str = "",
    ) -> AnaliseHarveyResponse:
        """
        Envia o texto de uma petição para análise estruturada pelo Harvey.

        Raises:
            HarveyUnavailableError: Se circuit breaker aberto ou falha irrecuperável.
        """
        system_prompt = (
            "Você é um especialista em direito processual brasileiro. "
            "Analise a peça jurídica fornecida e retorne JSON com os campos: "
            "tipo_peca, pontos_fortes (lista), vulnerabilidades (lista), "
            "argumentos_ausentes (lista), precedentes_relevantes (lista), "
            "score_geral (0-100), sugestoes (lista). "
            "Responda APENAS com JSON válido, sem markdown."
        )
        mensagem = (
            f"Tipo de análise: {tipo_analise.value}\n"
            f"Contexto processual: {contexto_processo}\n\n"
            f"Peça jurídica:\n{conteudo_peticao}"
        )

        payload = {
            "model": self.MODELO_HARVEY,
            "max_tokens": self.MAX_TOKENS,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": mensagem},
            ],
        }

        dados = await self._post_com_retry("/chat/completions", payload)
        conteudo, _, _ = self._extrair_resposta(dados)

        return self._parsear_analise(conteudo)

    # ------------------------------------------------------------------
    # Pesquisa de jurisprudência
    # ------------------------------------------------------------------

    async def pesquisar_jurisprudencia(
        self,
        query: str,
        tribunal: str = "",
        periodo: str = "",
    ) -> list[Jurisprudencia]:
        """
        Pesquisa jurisprudência na base Harvey.

        Returns:
            Lista de Jurisprudencia ordenada do mais recente para o mais antigo.

        Raises:
            HarveyUnavailableError: Se circuit breaker aberto ou falha irrecuperável.
        """
        system_prompt = (
            "Você é um especialista em jurisprudência brasileira. "
            "Retorne JSON com lista 'resultados', cada item com: "
            "ementa, tribunal, numero_processo, data_julgamento, "
            "aplicabilidade (FAVORAVEL|DESFAVORAVEL|NEUTRO), relevancia_score (0.0-1.0). "
            "Ordene do mais recente para o mais antigo. "
            "Responda APENAS com JSON válido, sem markdown."
        )
        filtros = []
        if tribunal:
            filtros.append(f"Tribunal: {tribunal}")
        if periodo:
            filtros.append(f"Período: {periodo}")
        filtros_str = "\n".join(filtros)
        mensagem = f"Query: {query}\n{filtros_str}".strip()

        payload = {
            "model": self.MODELO_HARVEY,
            "max_tokens": self.MAX_TOKENS,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": mensagem},
            ],
        }

        dados = await self._post_com_retry("/chat/completions", payload)
        conteudo, _, _ = self._extrair_resposta(dados)

        return self._parsear_jurisprudencias(conteudo)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    async def _post_com_retry(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        POST com retry + backoff exponencial + circuit breaker.

        A chamada HTTP real é síncrona (httpx.Client) e roda em run_in_executor,
        permitindo que o pybreaker (síncrono) envolva a chamada sem cruzar
        event loops.
        """
        ultimo_erro: Exception | None = None
        loop = asyncio.get_event_loop()

        for tentativa in range(1, self.MAX_RETRIES + 1):
            try:
                dados = await loop.run_in_executor(
                    None,
                    lambda: _harvey_cb.call(self._http_post_sync, endpoint, payload),
                )
                return dados  # type: ignore[return-value]
            except pybreaker.CircuitBreakerError as exc:
                logger.warning(
                    "harvey_circuit_aberto",
                    msg="Harvey indisponível — circuit breaker aberto",
                )
                raise HarveyUnavailableError("Harvey circuit breaker aberto") from exc
            except HarveyUnavailableError:
                raise
            except httpx.TimeoutException as exc:
                ultimo_erro = exc
                espera = _backoff(tentativa)
                logger.warning("harvey_timeout", tentativa=tentativa, espera_s=round(espera, 2))
                await asyncio.sleep(espera)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    raise HarveyUnavailableError(
                        f"Harvey retornou erro {exc.response.status_code}: {exc.response.text}"
                    ) from exc
                ultimo_erro = exc
                espera = _backoff(tentativa)
                logger.warning(
                    "harvey_erro_servidor",
                    tentativa=tentativa,
                    status=exc.response.status_code,
                    espera_s=round(espera, 2),
                )
                await asyncio.sleep(espera)
            except httpx.HTTPError as exc:
                ultimo_erro = exc
                espera = _backoff(tentativa)
                logger.warning(
                    "harvey_erro_http",
                    tentativa=tentativa,
                    erro=str(exc),
                    espera_s=round(espera, 2),
                )
                await asyncio.sleep(espera)

        logger.error(
            "harvey_falhou_todas_tentativas",
            tentativas=self.MAX_RETRIES,
            erro=str(ultimo_erro),
        )
        raise HarveyUnavailableError(
            f"Harvey indisponível após {self.MAX_RETRIES} tentativas: {ultimo_erro}"
        ) from ultimo_erro

    def _http_post_sync(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Chamada HTTP síncrona real ao endpoint Harvey.

        Deve ser chamada apenas dentro de run_in_executor.
        O pybreaker envolve este método diretamente, sem cruzar event loops.
        """
        url = f"{self._base_url}{endpoint}"
        response = self._sync_client.post(url, json=payload)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    @staticmethod
    def _extrair_resposta(dados: dict[str, Any]) -> tuple[str, int, int]:
        """Extrai (conteudo, tokens_input, tokens_output) da resposta Harvey."""
        try:
            conteudo = dados["choices"][0]["message"]["content"]
            uso = dados.get("usage", {})
            tokens_in = uso.get("prompt_tokens", 0)
            tokens_out = uso.get("completion_tokens", 0)
            return conteudo, tokens_in, tokens_out
        except (KeyError, IndexError) as exc:
            raise HarveyUnavailableError(
                f"Resposta Harvey em formato inesperado: {dados}"
            ) from exc

    @staticmethod
    def _parsear_analise(conteudo: str) -> AnaliseHarveyResponse:
        import json

        try:
            dados = json.loads(conteudo)
        except json.JSONDecodeError as exc:
            raise HarveyUnavailableError(
                f"Harvey retornou JSON inválido na análise de petição: {conteudo[:200]}"
            ) from exc

        return AnaliseHarveyResponse(
            tipo_peca=dados.get("tipo_peca", "desconhecido"),
            pontos_fortes=dados.get("pontos_fortes", []),
            vulnerabilidades=dados.get("vulnerabilidades", []),
            argumentos_ausentes=dados.get("argumentos_ausentes", []),
            precedentes_relevantes=dados.get("precedentes_relevantes", []),
            score_geral=int(dados.get("score_geral", 0)),
            sugestoes=dados.get("sugestoes", []),
        )

    @staticmethod
    def _parsear_jurisprudencias(conteudo: str) -> list[Jurisprudencia]:
        import json

        try:
            dados = json.loads(conteudo)
        except json.JSONDecodeError as exc:
            raise HarveyUnavailableError(
                f"Harvey retornou JSON inválido na pesquisa de jurisprudência: {conteudo[:200]}"
            ) from exc

        resultados = dados.get("resultados", [])
        jurisprudencias = []
        for item in resultados:
            jurisprudencias.append(
                Jurisprudencia(
                    ementa=item.get("ementa", ""),
                    tribunal=item.get("tribunal", ""),
                    numero_processo=item.get("numero_processo", ""),
                    data_julgamento=item.get("data_julgamento", ""),
                    aplicabilidade=item.get("aplicabilidade", "NEUTRO"),
                    relevancia_score=float(item.get("relevancia_score", 0.0)),
                )
            )
        return jurisprudencias

    def __enter__(self) -> "HarveyClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self._sync_client.close()
