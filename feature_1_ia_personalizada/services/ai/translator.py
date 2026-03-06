# feature_1_ia_personalizada/services/ai/translator.py
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_TERMOS_JSON = (
    Path(__file__).parent.parent.parent  # feature_1_ia_personalizada/
    / "data"
    / "termos_juridicos"
    / "traducoes.json"
)


def _normalizar(texto: str) -> str:
    """Lowercase + remove acentos para busca case/acento-insensitive."""
    nfkd = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


class JuridicalTranslator:
    """
    Traduz termos jurídicos usando dicionário local (O(1)) como primeira camada.
    Termos não encontrados no dicionário são resolvidos via Claude (ver orchestrator).

    O dicionário é carregado uma única vez na instanciação e mantido em memória.
    Chaves são normalizadas (sem acento, lowercase) para busca robusta.
    """

    def __init__(self) -> None:
        self._dicionario: dict[str, dict[str, str]] = {}
        # Mapeia chave normalizada → termo original (com acento) para exibição
        self._original: dict[str, str] = {}
        self._disponivel: bool = False
        self._carregar_dicionario()

    def _carregar_dicionario(self) -> None:
        try:
            raw = json.loads(_TERMOS_JSON.read_text(encoding="utf-8"))
            self._dicionario = {
                _normalizar(termo): dados for termo, dados in raw.items()
            }
            self._original = {_normalizar(termo): termo for termo in raw}
            self._disponivel = True
            logger.info(
                "tradutor_dicionario_carregado", total_termos=len(self._dicionario)
            )
        except FileNotFoundError:
            logger.error("tradutor_dicionario_nao_encontrado", path=str(_TERMOS_JSON))
        except json.JSONDecodeError as exc:
            logger.error("tradutor_dicionario_json_invalido", erro=str(exc))

    @property
    def dicionario_disponivel(self) -> bool:
        """False se o JSON não foi carregado — toda tradução cairá no Claude."""
        return self._disponivel

    def traduzir_termo(self, termo: str) -> str | None:
        """
        Busca o termo no dicionário local.

        Returns:
            String formatada com tradução (e exemplo, se houver), ou None se não encontrado.
        """
        entrada = self._dicionario.get(_normalizar(termo))
        if not entrada:
            return None

        traducao = entrada.get("traducao", "")
        exemplo = entrada.get("exemplo", "")

        if exemplo:
            return f"{traducao}\n\nExemplo: {exemplo}"
        return traducao

    def identificar_termos_tecnicos(self, texto: str) -> list[str]:
        """
        Identifica termos jurídicos presentes no texto usando os termos do dicionário.

        Estratégia: para cada termo do dicionário, verifica se aparece no texto
        como palavra completa (word boundary). Retorna os termos originais (com acento).

        Returns:
            Lista de termos jurídicos encontrados, sem duplicatas, na ordem de aparição.
        """
        texto_normalizado = _normalizar(texto)
        encontrados: list[str] = []
        vistos: set[str] = set()

        # Ordena por tamanho decrescente: termos mais longos têm prioridade
        # ex: "agravo de instrumento" antes de "agravo"
        termos_ordenados = sorted(self._dicionario.keys(), key=len, reverse=True)

        # texto_restante é consumido à medida que termos são encontrados —
        # evita que subtermos (ex: "agravo") batam dentro de termos compostos já capturados
        # (ex: "agravo de instrumento"). O espaço entre palavras satisfaz (?!\w), então
        # sem essa lógica "agravo" matcharia dentro de "agravo de instrumento".
        texto_restante = texto_normalizado

        for termo_norm in termos_ordenados:
            if termo_norm in vistos:
                continue
            pattern = r"(?<!\w)" + re.escape(termo_norm) + r"(?!\w)"
            if re.search(pattern, texto_restante):
                encontrados.append(self._original[termo_norm])
                vistos.add(termo_norm)
                # Remove este termo do texto restante para bloquear matches de subtermos
                texto_restante = re.sub(pattern, " ", texto_restante)

        return encontrados

    @property
    def total_termos(self) -> int:
        """Número de termos carregados no dicionário. Útil para health check."""
        return len(self._dicionario)
