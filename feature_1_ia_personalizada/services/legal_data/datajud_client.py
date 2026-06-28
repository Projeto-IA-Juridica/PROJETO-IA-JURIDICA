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
from datetime import datetime
from typing import Any

import httpx
import pybreaker
import structlog

logger = structlog.get_logger(__name__)

# Circuit breaker para a API DataJud (CNJ).
# Após 5 falhas consecutivas, o circuito abre e calls subsequentes retornam
# fallback imediatamente (sem aguardar timeout de rede) por 120 segundos.
# Evita que um DataJud instável paralise todos os workers de monitoramento.
_datajud_cb = pybreaker.CircuitBreaker(
    fail_max=5,  # abre após 5 falhas consecutivas
    reset_timeout=120,  # tenta novamente após 2 minutos (half-open)
    name="datajud",
)

_BASE_URL = "https://api-publica.datajud.cnj.jus.br"

# Mapeamento TT → índice ElasticSearch para ramo Estadual (J=8)
_TJ_INDICES: dict[str, str] = {
    "01": "api_publica_tjac",
    "02": "api_publica_tjal",
    "03": "api_publica_tjap",
    "04": "api_publica_tjam",
    "05": "api_publica_tjba",
    "06": "api_publica_tjce",
    "07": "api_publica_tjdf",
    "08": "api_publica_tjes",
    "09": "api_publica_tjgo",
    "10": "api_publica_tjma",
    "11": "api_publica_tjmt",
    "12": "api_publica_tjms",
    "13": "api_publica_tjmg",
    "14": "api_publica_tjpa",
    "15": "api_publica_tjpb",
    "16": "api_publica_tjpr",
    "17": "api_publica_tjpe",
    "18": "api_publica_tjpi",
    "19": "api_publica_tjrj",
    "20": "api_publica_tjrn",
    "21": "api_publica_tjrs",
    "22": "api_publica_tjro",
    "23": "api_publica_tjrr",
    "24": "api_publica_tjsc",
    "25": "api_publica_tjse",
    "26": "api_publica_tjsp",
    "27": "api_publica_tjto",
}

# Mapeamento TT → índice para TRF (J=5)
_TRF_INDICES: dict[str, str] = {
    "01": "api_publica_trf1",
    "02": "api_publica_trf2",
    "03": "api_publica_trf3",
    "04": "api_publica_trf4",
    "05": "api_publica_trf5",
    "06": "api_publica_trf6",
}

# Mapeamento TT → índice para TRT (J=6)
_TRT_INDICES: dict[str, str] = {f"{i:02d}": f"api_publica_trt{i}" for i in range(1, 25)}

_CNJ_FORMATADO = re.compile(r"^(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$")
_CNJ_RAW = re.compile(r"^\d{20}$")


class DataJudClientError(Exception):
    """Exceção para erros originários da API Pública do CNJ / DataJud."""

    pass


def _parse_iso_dt(iso_str: str | None) -> datetime | None:
    """Converte string ISO 8601 (Z ou +HH:MM) em datetime timezone-aware.

    Necessário porque DataJud retorna .000Z e o banco pode persistir +00:00,
    tornando a comparação lexicográfica incorreta quando há milissegundos.
    """
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        return None


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
    j = digits[13]  # ramo da justiça
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
        raise DataJudClientError(f"Tribunal não mapeado para CNJ {numero_cnj!r} (J={j}, TT={tt})")
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

        query = {"query": {"match": {"numeroProcesso": cnj_raw}}}

        logger.info("datajud_consultando", cnj=cnj_raw, indice=indice)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=query, headers=self._headers())
            except httpx.TimeoutException as exc:
                raise DataJudClientError(f"Timeout ao consultar DataJud para {numero_cnj}") from exc
            except httpx.RequestError as exc:
                raise DataJudClientError(f"Erro de rede ao consultar DataJud: {exc}") from exc

        if response.status_code == 401:
            raise DataJudClientError(
                "DataJud: autenticação inválida (401). Verifique DATAJUD_API_KEY."
            )
        if response.status_code == 404:
            raise DataJudClientError(
                f"DataJud: índice não encontrado ({indice}). Tribunal pode não estar disponível."
            )
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

        return data  # type: ignore[no-any-return]

    @staticmethod
    def _extrair_metadados(source: dict[str, Any]) -> dict[str, Any]:
        """
        Extrai tribunal, vara, comarca, data_distribuicao e tipo_acao do _source DataJud.
        Retorna apenas os campos com valor (ignora None/vazios).
        """
        metadados: dict[str, Any] = {}

        tribunal_raw = source.get("tribunal")
        if isinstance(tribunal_raw, dict):
            tribunal_sigla = tribunal_raw.get("sigla") or tribunal_raw.get("nome", "")
            if tribunal_sigla:
                metadados["tribunal"] = str(tribunal_sigla).upper()
        elif tribunal_raw:
            metadados["tribunal"] = str(tribunal_raw).upper()

        orgao = source.get("orgaoJulgador") or {}
        vara_nome = orgao.get("nome")
        if vara_nome:
            metadados["vara"] = str(vara_nome)

        # DataJud raramente expõe comarca diretamente — tenta campo direto primeiro,
        # depois extrai do nome do órgão julgador (ex: "7ª Vara Cível da comarca de Uberlândia")
        comarca_raw = source.get("comarca") or source.get("municipio")
        if not comarca_raw and vara_nome:
            m = re.search(r"comarca\s+de\s+(.+)", vara_nome, re.IGNORECASE)
            if m:
                comarca_raw = m.group(1).strip()
        if comarca_raw:
            metadados["comarca"] = str(comarca_raw)

        data_ajuiz = source.get("dataAjuizamento")
        if data_ajuiz:
            # DataJud pode retornar YYYYMMDDHHMMSS (14 dígitos) ou ISO 8601
            data_str = str(data_ajuiz)
            if len(data_str) == 14 and data_str.isdigit():
                data_str = (
                    f"{data_str[:4]}-{data_str[4:6]}-{data_str[6:8]}"
                    f"T{data_str[8:10]}:{data_str[10:12]}:{data_str[12:14]}"
                )
            metadados["data_distribuicao"] = data_str

        classe = source.get("classe") or {}
        tipo_acao = classe.get("nome")
        if tipo_acao:
            metadados["tipo_acao"] = str(tipo_acao)

        valor_causa = source.get("valorCausa")
        if valor_causa is not None:
            try:
                metadados["valor_causa"] = float(valor_causa)
            except (TypeError, ValueError):
                pass

        return metadados

    def buscar_dados_completos(
        self,
        numero_cnj: str,
        data_referencia_iso: str | None = None,
    ) -> tuple[list[dict], dict[str, Any]]:
        """
        Wrapper síncrono que consulta DataJud UMA ÚNICA VEZ e retorna:
          - lista de andamentos filtrados por data_referencia_iso
          - dicionário com metadados do processo (tribunal, vara, comarca, etc.)

        Usado pelo worker na primeira execução para preencher campos do processo.
        Retorna ([], {}) quando o circuit breaker está aberto.
        """
        import asyncio

        try:
            data = _datajud_cb.call(asyncio.run, self.consultar_processo(numero_cnj))
        except pybreaker.CircuitBreakerError:
            logger.warning(
                "datajud_circuit_aberto",
                cnj=numero_cnj,
                msg="DataJud indisponível — retornando fallback vazio",
            )
            return [], {}

        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return [], {}

        source = hits[0].get("_source", {})
        metadados = self._extrair_metadados(source)

        movimentos = source.get("movimentos", [])
        ref_dt = _parse_iso_dt(data_referencia_iso)
        andamentos: list[dict] = []

        for m in movimentos:
            nome = m.get("nome", "")
            complementos = m.get("complementosTabelados", [])
            if complementos:
                valores = "; ".join(
                    (c.get("nome") or str(c.get("valor", ""))) for c in complementos if c.get("nome") or c.get("valor") is not None
                )
                if valores:
                    nome = f"{nome}: {valores}"

            data_hora = m.get("dataHora")

            if ref_dt and data_hora:
                mov_dt = _parse_iso_dt(data_hora)
                if mov_dt and mov_dt <= ref_dt:
                    continue

            andamentos.append({"texto": nome, "data": data_hora})

        logger.info(
            "datajud_dados_completos",
            cnj=numero_cnj,
            andamentos=len(andamentos),
            tribunal=metadados.get("tribunal"),
        )
        return andamentos, metadados

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

        Retorna lista vazia (fallback) quando o circuit breaker está aberto,
        evitando que um DataJud instável paralise os workers de monitoramento.
        """
        import asyncio

        try:
            data = _datajud_cb.call(asyncio.run, self.consultar_processo(numero_cnj))
        except pybreaker.CircuitBreakerError:
            logger.warning(
                "datajud_circuit_aberto",
                cnj=numero_cnj,
                msg="DataJud indisponível — retornando lista vazia como fallback",
            )
            return []

        hits = data.get("hits", {}).get("hits", [])

        if not hits:
            return []

        movimentos = hits[0].get("_source", {}).get("movimentos", [])
        andamentos = []

        # Converte a referência para datetime para comparação correta entre formatos
        # ISO 8601: DataJud usa .000Z, banco pode persistir +00:00 sem milissegundos.
        # Comparação lexicográfica falha nesses casos — datetime resolve corretamente.
        ref_dt = _parse_iso_dt(data_referencia_iso)

        for m in movimentos:
            nome = m.get("nome", "")
            complementos = m.get("complementosTabelados", [])
            if complementos:
                valores = "; ".join(
                    (c.get("nome") or str(c.get("valor", ""))) for c in complementos if c.get("nome") or c.get("valor") is not None
                )
                if valores:
                    nome = f"{nome}: {valores}"

            data_hora = m.get("dataHora")

            # Exclui movimentos anteriores ou iguais ao último andamento salvo
            if ref_dt and data_hora:
                mov_dt = _parse_iso_dt(data_hora)
                if mov_dt and mov_dt <= ref_dt:
                    continue

            andamentos.append({"texto": nome, "data": data_hora})

        logger.info(
            "datajud_andamentos_filtrados",
            cnj=numero_cnj,
            total=len(andamentos),
            referencia=data_referencia_iso,
        )
        return andamentos

    async def buscar_andamentos_async(self, numero_cnj: str) -> list[dict]:
        """
        Versão assíncrona para o caminho real-time do orchestrator.
        Retorna [{"descricao": str, "data": str|None}] ou [] em caso de falha.
        """
        try:
            data = await self.consultar_processo(numero_cnj)
        except DataJudClientError as exc:
            logger.warning("datajud_async_erro", cnj=numero_cnj, erro=str(exc))
            return []

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
                    (c.get("nome") or str(c.get("valor", ""))) for c in complementos if c.get("nome") or c.get("valor") is not None
                )
                if valores:
                    nome = f"{nome}: {valores}"
            andamentos.append({"texto": nome, "data": m.get("dataHora")})

        logger.info("datajud_async_andamentos", cnj=numero_cnj, total=len(andamentos))
        return andamentos
