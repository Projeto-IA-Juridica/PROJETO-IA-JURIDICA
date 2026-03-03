import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class DataJudRealClient:
    """
    Cliente REST real para consumo da API Pública do CNJ (DataJud).
    Usa um header com 'API-Key' para obter a listagem de andamentos.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        # Usamos o endpoint de processos unificados (pode variar de tribunal,
        # mas o alias '_all' busca em todos os índices disponíveis na API pública para pesquisa estruturada)
        self.base_url = "https://api-publica.datajud.cnj.jus.br/api_publica_"
        self.headers = {
            "Authorization": f"APIKey {self.api_key}",
            "Content-Type": "application/json",
        }

    async def consultar_numero_cnj(self, numero_cnj: str) -> dict[str, Any] | None:
        """
        Retorna todos os dados que a API Pública possui de um dado CNJ.
        Usaremos um delay pequeno após a requisição e timeout longo, pois a API do governo pode ser instável.
        """
        # Limpar mascara do CNJ se enviada, pois o CNJ espera com ou sem mascara, mas buscar exato
        # Na documentação eles buscam no campo `numeroProcesso` (sem formatação geralmente, mas suporta com máscara dependendo do index)
        numero_cnj_limpo = numero_cnj.replace("-", "").replace(".", "")

        # A documentação deles diz que o numeroProcesso na busca exata precisa manter a formatação original na maioria dos índices
        payload = {
            "query": {
                "bool": {
                    "should": [
                        {"match": {"numeroProcesso": numero_cnj}},
                        {"match": {"numeroProcesso": numero_cnj_limpo}},
                    ]
                }
            }
        }

        # Para ter abrangencia geral, a API usa alias especifico do tribunal.
        # Exemplo: https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search
        # Vamos tentar inferir o tribunal pelo próprio CNJ (14 primeiros = NN, depois AAAA, J, TR, OOOO)
        # Formato: NNNNNNN-DD.AAAA.J.TR.OOOO.  TR = Tribunal.
        # 8 = Justiça Estadual, TR 26 = SP -> tjsp
        tribunal_index = "_all"
        if len(numero_cnj) == 25:
            partes = numero_cnj.split(".")
            if len(partes) >= 4:
                j = partes[2]
                tr = partes[3]
                if j == "8" and tr == "26":
                    tribunal_index = "tjsp"
                elif j == "4" and tr == "03":
                    tribunal_index = "trf3"

        url = f"{self.base_url}{tribunal_index}/_search"
        if tribunal_index == "_all":
            url = "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search"  # Fallback temporário

        logger.info(f"[DataJud via HTTPX] Buscando CNJ {numero_cnj} na rota {url}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                data = response.json()

                # Se encontrou hits
                hits = data.get("hits", {}).get("hits", [])
                if not hits:
                    logger.warning(
                        f"CNJ {numero_cnj} encontrou 0 resultados no Datajud."
                    )
                    return {
                        "erro": "Processo não encontrado nos repositórios do CNJ indexados.",
                        "raw": data,
                    }

                return hits[0].get("_source", {})

            except httpx.HTTPError as e:
                logger.error(f"Erro HTTP ao contatar DataJud: {e}")
                return {"erro": str(e)}
            except Exception as e:
                logger.error(f"Erro inesperado no DataJud: {e}")
                return {"erro": str(e)}

    async def consultar_cpf_cnpj(
        self, documento: str, tribunal: str = "tjsp"
    ) -> dict[str, Any]:
        """
        Busca processos associados a um CPF ou CNPJ específico usando query_string no Elasticsearch.
        Retorna uma lista dos processos encontrados.
        """
        import httpx

        documento_limpo = re.sub(r"[^\d]", "", documento)
        url = f"{self.base_url}{tribunal}/_search"

        payload = {
            "query": {
                "query_string": {"query": f'"{documento_limpo}" OR "{documento}"'}
            },
            "size": 10,
        }

        logger.info(f"[DataJud via HTTPX] Buscando CPF/CNPJ {documento} na rota {url}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                data = response.json()

                hits = data.get("hits", {}).get("hits", [])
                if not hits:
                    logger.warning(
                        f"Documento {documento} encontrou 0 resultados no Datajud."
                    )
                    return {
                        "erro": "Nenhum processo encontrado para este documento.",
                        "processos": [],
                    }

                processos = [hit.get("_source", {}) for hit in hits]
                return {"sucesso": True, "processos": processos}

            except httpx.HTTPError as e:
                logger.error(f"Erro HTTP ao contatar DataJud: {e}")
                return {"erro": str(e)}
            except Exception as e:
                logger.error(f"Erro inesperado no DataJud: {e}")
                return {"erro": str(e)}
