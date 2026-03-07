"""
feature_1_ia_personalizada/services/legal_data/datajud_client.py

Client de integração com a API DataJud do Conselho Nacional de Justiça (CNJ).

A API DataJud é baseada em ElasticSearch e requer autenticação via header:
    Authorization: ApiKey <base64_encoded_key>

Endpoint base: https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/_search

O índice do tribunal é derivado dos campos J e TT do número CNJ:
    NNNNNNN-DD.AAAA.J.TT.OOOO
    J=8 (Estadual), J=5 (Federal/TRF), J=4 (TST), J=3 (STJ), J=1 (STF)
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api-publica.datajud.cnj.jus.br"

# Mapeamento TT → índice ElasticSearch para ramo Estadual (J=8)
_TJ_INDICES: dict[str, str] = {
    "01": "api_publica_tjac", "02": "api_publica_tjal", "03": "api_publica_tjap",
    "04": "api_publica_tjam", "05": "api_publica_tjba", "06": "api_publica_tjce",
    "07": "api_publica_tjdf", "08": "api_publica_tjes", "09": "api_publica_tjgo",
    "10": "api_publica_tjma", "11": "api_publica_tjmt", "12": "api_publica_tjms",
    "13": "api_publica_tjmg", "14": "api_publica_tjpa", "15": "api_publica_tjpb",
    "16": "api_publica_tjpr", "17": "api_publica_tjpe", "18": "api_publica_tjpi",
    "19": "api_publica_tjrj", "20": "api_publica_tjrn", "21": "api_publica_tjrs",
    "22": "api_publica_tjro", "23": "api_publica_tjrr", "24": "api_publica_tjsc",
    "25": "api_publica_tjse", "26": "api_publica_tjsp", "27": "api_publica_tjto",
}

# Mapeamento TT → índice para TRF (J=5)
_TRF_INDICES: dict[str, str] = {
    "01": "api_publica_trf1", "02": "api_publica_trf2", "03": "api_publica_trf3",
    "04": "api_publica_trf4", "05": "api_publica_trf5", "06": "api_publica_trf6",
}

# Mapeamento TT → índice para TRT (J=6)
_TRT_INDICES: dict[str, str] = {f"{i:02d}": f"api_publica_trt{i}" for i in range(1, 25)}

_CNJ_FORMATADO = re.compile(
    r"^(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$"
)
_CNJ_RAW = re.compile(r"^\d{20}$")


class DataJudClientError(Exception):
    """Exceção para erros originários da API Pública do CNJ / DataJud."""
    pass


def _normalizar_cnj(numero_cnj: str) -> str:
    """Remove pontuação do CNJ, retornando apenas os 20 dígitos."""
    digits = re.sub(r"[.\-]", "", numero_cnj.strip())
    if not _CNJ_RAW.match(digits):
        raise DataJudClientError(f"Número CNJ inválido: {numero_cnj!r}")
    return digits


def _indice_para_cnj(numero_cnj: str) -> str:
    """Deriva o índice ElasticSearch do DataJud a partir do número CNJ.

    Aceita tanto o formato formatado (NNNNNNN-DD.AAAA.J.TT.OOOO)
    quanto o raw (20 dígitos sem pontuação).
    """
    digits = _normalizar_cnj(numero_cnj)
    # Estrutura: NNNNNNN(7) DD(2) AAAA(4) J(1) TT(2) OOOO(4)
    j = digits[13]    # ramo da justiça
    tt = digits[14:16]  # tribunal

    if j == "8":
        indice = _TJ_INDICES.get(tt)
    elif j == "5":
        indice = _TRF_INDICES.get(tt)
    elif j == "6":
        indice = _TRT_INDICES.get(tt)
    elif j == "4":
        indice = "api_publica_tst"
    elif j == "3":
        indice = "api_publica_stj"
    elif j == "2":
        indice = "api_publica_csjt"
    elif j == "1":
        indice = "api_publica_stf"
    elif j == "9":
        indice = "api_publica_tjmmg"  # TJM-MG como fallback militar
    else:
        indice = None

    if not indice:
        raise DataJudClientError(
            f"Tribunal não mapeado para CNJ {numero_cnj!r} (J={j}, TT={tt})"
        )
    return indice


class DataJudClient:
    """Client assíncrono para a API pública DataJud (CNJ/ElasticSearch)."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        self._base_url = _BASE_URL
        mode = "REAL" if api_key else "SEM_KEY"
        logger.info("datajud_client_iniciado", mode=mode)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"
        return headers

    async def consultar_processo(self, numero_cnj: str) -> dict[str, Any]:
        """
        Consulta o processo na API DataJud pelo número CNJ.

        Retorna o payload ElasticSearch com `hits.hits[0]._source` contendo:
          - numeroProcesso, classe, tribunal, dataAjuizamento, movimentos, etc.

        Levanta DataJudClientError em caso de número inválido, tribunal
        não mapeado ou erro HTTP da API.
        """
        indice = _indice_para_cnj(numero_cnj)
        url = f"{self._base_url}/{indice}/_search"
        # DataJud armazena o número sem formatação (20 dígitos puros)
        cnj_raw = _normalizar_cnj(numero_cnj)

        query = {
            "query": {
                "match": {
                    "numeroProcesso": cnj_raw
                }
            }
        }

        logger.info("datajud_consultando", cnj=cnj_raw, indice=indice)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=query, headers=self._headers())
            except httpx.TimeoutException as exc:
                raise DataJudClientError(
                    f"Timeout ao consultar DataJud para {numero_cnj}"
                ) from exc
            except httpx.RequestError as exc:
                raise DataJudClientError(
                    f"Erro de rede ao consultar DataJud: {exc}"
                ) from exc

        if response.status_code == 401:
            raise DataJudClientError("DataJud: autenticação inválida (401). Verifique DATAJUD_API_KEY.")
        if response.status_code == 404:
            raise DataJudClientError(f"DataJud: índice não encontrado ({indice}). Tribunal pode não estar disponível.")
        if response.status_code != 200:
            raise DataJudClientError(
                f"DataJud retornou HTTP {response.status_code}: {response.text[:300]}"
            )

        data = response.json()
        hits = data.get("hits", {}).get("hits", [])

        logger.info(
            "datajud_resposta_recebida",
            cnj=numero_cnj,
            total_hits=len(hits),
        )

        return data

    def buscar_novos_andamentos(
        self,
        numero_cnj: str,
        data_referencia_iso: str | None = None,
    ) -> list[dict]:
        """
        Wrapper síncrono que consulta a API DataJud e retorna andamentos
        no formato padrão do pipeline: [{"texto": str, "data": str|None}].

        Filtra movimentos anteriores a `data_referencia_iso` quando fornecida.
        Chamado pelo worker Celery (contexto síncrono — sem event loop ativo).
        """
        import asyncio

        data = asyncio.run(self.consultar_processo(numero_cnj))
        hits = data.get("hits", {}).get("hits", [])

        if not hits:
            return []

        movimentos = hits[0].get("_source", {}).get("movimentos", [])
        andamentos = []

        for m in movimentos:
            nome = m.get("nome", "")
            complementos = m.get("complementosTabelados", [])
            if complementos:
                valores = "; ".join(
                    str(c.get("valor", "")) for c in complementos if c.get("valor") is not None
                )
                if valores:
                    nome = f"{nome}: {valores}"

            data_hora = m.get("dataHora")

            # Exclui movimentos anteriores ou iguais ao último andamento salvo
            if data_referencia_iso and data_hora and data_hora <= data_referencia_iso:
                continue

            andamentos.append({"texto": nome, "data": data_hora})

        logger.info(
            "datajud_andamentos_filtrados",
            cnj=numero_cnj,
            total=len(andamentos),
            referencia=data_referencia_iso,
        )
        return andamentos
