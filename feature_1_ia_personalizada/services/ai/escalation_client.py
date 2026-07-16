# feature_1_ia_personalizada/services/ai/escalation_client.py
"""
Cliente de Escalação — Claude Opus para perguntas jurídicas complexas.

Usado pelo ConfidenceRouter quando o score de confiança do Claude padrão
(Haiku/Sonnet) fica abaixo do threshold ou há forçamento por termos legais.

Usa o mesmo SDK Anthropic já presente no projeto, apenas com um modelo
mais capaz (claude-opus-4-6 por padrão, configurável via MODELO_ESCALACAO).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

import anthropic
import structlog

from shared.config.settings import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Custo estimado Claude Opus 4.6 (verificar em anthropic.com/pricing)
# ---------------------------------------------------------------------------
_CUSTO_INPUT_POR_MILHAO = Decimal("15.00")  # USD
_CUSTO_OUTPUT_POR_MILHAO = Decimal("75.00")  # USD


def _calcular_custo(tokens_input: int, tokens_output: int) -> Decimal:
    custo_in = (Decimal(tokens_input) / Decimal(1_000_000)) * _CUSTO_INPUT_POR_MILHAO
    custo_out = (Decimal(tokens_output) / Decimal(1_000_000)) * _CUSTO_OUTPUT_POR_MILHAO
    return custo_in + custo_out


# ---------------------------------------------------------------------------
# Enums e dataclasses públicos
# ---------------------------------------------------------------------------


class TipoAnalise(str, Enum):
    ANALISE_COMPLETA = "analise_completa"
    PONTOS_FRACOS = "pontos_fracos"
    JURISPRUDENCIA_RELACIONADA = "jurisprudencia_relacionada"
    RESUMO_EXECUTIVO = "resumo_executivo"
    CONTRA_ARGUMENTOS = "contra_argumentos"


@dataclass
class EscalacaoResponse:
    conteudo: str
    tokens_input: int
    tokens_output: int
    custo_estimado: Decimal
    modelo: str
    latencia_ms: int


@dataclass
class AnalisePecaResponse:
    tipo_peca: str
    pontos_fortes: list[str]
    vulnerabilidades: list[str]
    argumentos_ausentes: list[str]
    precedentes_relevantes: list[str]
    score_geral: int  # 0-100
    sugestoes: list[str] = field(default_factory=list)
    tokens_input: int = 0
    tokens_output: int = 0
    custo_estimado: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass
class Jurisprudencia:
    ementa: str
    tribunal: str
    numero_processo: str
    data_julgamento: str
    aplicabilidade: str  # "FAVORAVEL" | "DESFAVORAVEL" | "NEUTRO"
    relevancia_score: float


# ---------------------------------------------------------------------------
# Exceção pública
# ---------------------------------------------------------------------------


class EscalacaoIndisponivelError(RuntimeError):
    """Levantada quando o modelo de escalação falha — caller usa Claude padrão como fallback."""


# ---------------------------------------------------------------------------
# Cliente principal
# ---------------------------------------------------------------------------


class EscalacaoClient:
    """
    Wrapper sobre o SDK Anthropic usando Claude Opus para escalação jurídica.

    Reutiliza a mesma chave ANTHROPIC_API_KEY já configurada no projeto.
    O modelo é configurável via settings.MODELO_ESCALACAO (padrão: claude-opus-4-6).

    Retry de 3 tentativas com backoff — mesmo padrão do ClaudeClient padrão.
    """

    MAX_TOKENS = 2048
    # Análises estruturadas (JSON com 6 listas) estouram 2048 tokens com
    # petições reais — o JSON chega truncado e o parse falha. Limite maior
    # só para as chamadas que retornam JSON.
    MAX_TOKENS_JSON = 8192
    MAX_RETRIES = 3

    def __init__(self) -> None:
        self._modelo = settings.MODELO_ESCALACAO
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    # ------------------------------------------------------------------
    # Resposta jurídica livre
    # ------------------------------------------------------------------

    async def gerar_resposta(
        self,
        system_prompt: str,
        mensagem_usuario: str,
        contexto_rag: str = "",
        escritorio_id: int | None = None,
        historico: list[dict[str, str]] | None = None,
    ) -> EscalacaoResponse:
        """
        Gera uma resposta jurídica usando o modelo de escalação.

        `historico` permite passar turnos anteriores da mesma conversa
        (lista de {"role": "user"|"assistant", "content": str}) para que o
        modelo tenha memória entre perguntas.

        Raises:
            EscalacaoIndisponivelError: Se todas as tentativas falharem.
        """
        conteudo_usuario = (
            f"{contexto_rag}\n\n{mensagem_usuario}".strip() if contexto_rag else mensagem_usuario
        )

        inicio = time.perf_counter()
        resposta = await self._chamar_com_retry(
            system_prompt=system_prompt,
            mensagem=conteudo_usuario,
            historico=historico,
        )
        latencia_ms = int((time.perf_counter() - inicio) * 1000)

        tokens_in = resposta.usage.input_tokens
        tokens_out = resposta.usage.output_tokens
        custo = _calcular_custo(tokens_in, tokens_out)

        logger.info(
            "escalacao_resposta_ok",
            modelo=self._modelo,
            escritorio_id=escritorio_id,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            latencia_ms=latencia_ms,
            custo_usd=str(custo),
        )

        return EscalacaoResponse(
            conteudo=self._extrair_texto(resposta),
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            custo_estimado=custo,
            modelo=self._modelo,
            latencia_ms=latencia_ms,
        )

    # ------------------------------------------------------------------
    # Análise de petição PDF
    # ------------------------------------------------------------------

    async def analisar_peca(
        self,
        conteudo_peca: str,
        tipo_analise: TipoAnalise = TipoAnalise.ANALISE_COMPLETA,
        contexto_processo: str = "",
    ) -> AnalisePecaResponse:
        """
        Analisa uma peça jurídica e retorna resposta estruturada.

        Raises:
            EscalacaoIndisponivelError: Se a chamada falhar ou o JSON for inválido.
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
            f"Peça jurídica:\n{conteudo_peca}"
        )

        resposta = await self._chamar_com_retry(
            system_prompt=system_prompt, mensagem=mensagem, max_tokens=self.MAX_TOKENS_JSON
        )
        conteudo = self._extrair_texto(resposta)
        if resposta.stop_reason == "max_tokens":
            raise EscalacaoIndisponivelError(
                "Análise excedeu o limite de tokens de saída — JSON incompleto."
            )
        dados = self._extrair_json(conteudo, contexto="análise de peça")

        tokens_in = getattr(getattr(resposta, "usage", None), "input_tokens", 0)
        tokens_out = getattr(getattr(resposta, "usage", None), "output_tokens", 0)

        return AnalisePecaResponse(
            tipo_peca=dados.get("tipo_peca", "desconhecido"),
            pontos_fortes=dados.get("pontos_fortes", []),
            vulnerabilidades=dados.get("vulnerabilidades", []),
            argumentos_ausentes=dados.get("argumentos_ausentes", []),
            precedentes_relevantes=dados.get("precedentes_relevantes", []),
            score_geral=int(dados.get("score_geral", 0)),
            sugestoes=dados.get("sugestoes", []),
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            custo_estimado=_calcular_custo(tokens_in, tokens_out),
        )

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
        Pesquisa jurisprudência usando o conhecimento do modelo de escalação.

        Raises:
            EscalacaoIndisponivelError: Se a chamada falhar ou o JSON for inválido.
        """
        system_prompt = (
            "Você é um especialista em jurisprudência brasileira. "
            "Retorne JSON com lista 'resultados', cada item com: "
            "ementa, tribunal, numero_processo, data_julgamento, "
            "aplicabilidade (FAVORAVEL|DESFAVORAVEL|NEUTRO), relevancia_score (0.0-1.0). "
            "Ordene do mais recente para o mais antigo. "
            "Responda APENAS com JSON válido, sem markdown."
        )
        filtros = [f"Query: {query}"]
        if tribunal:
            filtros.append(f"Tribunal: {tribunal}")
        if periodo:
            filtros.append(f"Período: {periodo}")

        resposta = await self._chamar_com_retry(
            system_prompt=system_prompt,
            mensagem="\n".join(filtros),
            max_tokens=self.MAX_TOKENS_JSON,
        )
        conteudo = self._extrair_texto(resposta)
        dados = self._extrair_json(conteudo, contexto="pesquisa de jurisprudência")

        return [
            Jurisprudencia(
                ementa=item.get("ementa", ""),
                tribunal=item.get("tribunal", ""),
                numero_processo=item.get("numero_processo", ""),
                data_julgamento=item.get("data_julgamento", ""),
                aplicabilidade=item.get("aplicabilidade", "NEUTRO"),
                relevancia_score=float(item.get("relevancia_score", 0.0)),
            )
            for item in dados.get("resultados", [])
        ]

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    async def _chamar_com_retry(
        self,
        system_prompt: str,
        mensagem: str,
        historico: list[dict[str, str]] | None = None,
        max_tokens: int | None = None,
    ) -> anthropic.types.Message:
        """Chama o modelo de escalação com retry e backoff exponencial."""
        import asyncio
        import random

        mensagens: list[Any] = [*(historico or []), {"role": "user", "content": mensagem}]
        ultimo_erro: Exception | None = None

        for tentativa in range(1, self.MAX_RETRIES + 1):
            try:
                return await self._client.messages.create(
                    model=self._modelo,
                    max_tokens=max_tokens or self.MAX_TOKENS,
                    system=system_prompt,
                    messages=mensagens,
                )
            except anthropic.AuthenticationError as exc:
                raise EscalacaoIndisponivelError("Chave Anthropic inválida.") from exc
            except (anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.APIError) as exc:
                ultimo_erro = exc
                espera = 2**tentativa + random.uniform(0.0, 1.0)
                logger.warning(
                    "escalacao_retry",
                    tentativa=tentativa,
                    erro=type(exc).__name__,
                    espera_s=round(espera, 2),
                )
                await asyncio.sleep(espera)

        raise EscalacaoIndisponivelError(
            f"Modelo de escalação indisponível após {self.MAX_RETRIES} tentativas: {ultimo_erro}"
        ) from ultimo_erro

    @staticmethod
    def _extrair_texto(resposta: anthropic.types.Message) -> str:
        blocos = [b for b in resposta.content if b.type == "text"]
        if not blocos:
            raise EscalacaoIndisponivelError("Modelo de escalação não retornou bloco de texto.")
        return str(blocos[0].text)

    @staticmethod
    def _extrair_json(conteudo: str, contexto: str) -> Any:
        """
        Extrai JSON da resposta do modelo de forma tolerante.

        Mesmo instruído a responder "APENAS com JSON válido, sem markdown",
        o modelo frequentemente envolve a resposta em cercas ```json ... ```
        ou adiciona uma frase antes/depois. Aqui recortamos do primeiro
        delimitador de abertura ({ ou [) até o último de fechamento
        correspondente antes de parsear.

        Raises:
            EscalacaoIndisponivelError: Se nenhum JSON válido for encontrado.
        """
        try:
            return json.loads(conteudo)
        except json.JSONDecodeError:
            pass

        inicio_obj = conteudo.find("{")
        inicio_lista = conteudo.find("[")
        candidatos = [i for i in (inicio_obj, inicio_lista) if i != -1]
        if candidatos:
            inicio = min(candidatos)
            fechamento = "}" if inicio == inicio_obj else "]"
            fim = conteudo.rfind(fechamento)
            if fim > inicio:
                try:
                    return json.loads(conteudo[inicio : fim + 1])
                except json.JSONDecodeError:
                    pass

        raise EscalacaoIndisponivelError(f"JSON inválido na {contexto}: {conteudo[:200]}")
