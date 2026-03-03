"""
feature_1_ia_personalizada/services/legal_data/jusbrasil_client.py

Client de integração com o portal Jusbrasil para captura de andamentos judiciais.
Durante o MVP, implementa um sistema de Mock (dados fictícios robustos) para
nós podermos testar a Inteligência Artificial (Claude) e o RAG sem depender
de cotas pagas caras de APIs judiciais de terceiros.

A estrutura foi desenhada de forma assíncrona para que a troca pelo Client
Real (HTTP/Requests) no futuro exija apenas a mudança da string de retorno,
sem afetar o resto do sistema.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import structlog
from prometheus_client import Counter

logger = structlog.get_logger(__name__)

_jusbrasil_requests_total = Counter(
    "jusbrasil_requests_total",
    "Total de requisições ao Jusbrasil (ou mock)",
    labelnames=["endpoint", "status"],
)


class JusbrasilClientError(Exception):
    """Exceção base para erros na integração com o Jusbrasil."""

    pass


class JusbrasilClient:
    """Client assíncrono para interagir com a API do Jusbrasil (ou Mock no MVP)."""

    def __init__(self, api_key: str | None = None):
        """
        No MVP, a api_key pode vir vazia pois usaremos o simulador local.
        """
        self.api_key = api_key
        self._is_mock = True  # Flag indicando uso de simulador
        logger.info(
            "jusbrasil_client_iniciado", mode="MOCK" if self._is_mock else "LIVE"
        )

    async def buscar_dados_processo(self, numero_cnj: str) -> dict[str, Any]:
        """
        Busca a "Capa do Processo" (Metadados: Tribunal, Vara, Partes).

        Args:
            numero_cnj (str): Número do processo no formato NNNNNNN-DD.AAAA.J.TR.OOOO

        Returns:
            Dict com tribunal, comarca, vara, assunto principal e data de ajuizamento.
        """
        logger.info("jusbrasil_buscando_capa_processo", cnj=numero_cnj)

        # Simula latência de rede ir até a internet (1 a 2 segundos)
        await asyncio.sleep(1.5)
        _jusbrasil_requests_total.labels(
            endpoint="buscar_dados_processo", status="ok"
        ).inc()

        # Retorno Simulado (MOCK) para o teste da IA
        return {
            "numero_cnj": numero_cnj,
            "tribunal": "Tribunal de Justiça de São Paulo (TJSP)",
            "comarca": "São Paulo / SP",
            "vara": "3ª Vara Cível do Foro Central",
            "assunto": "Indenização por Danos Morais",
            "data_distribuicao": (datetime.now() - timedelta(days=365)).isoformat(),
            "partes": [
                {"polo": "ATIVO", "nome": "Maria José da Silva"},
                {"polo": "PASSIVO", "nome": "Banco Finanças S.A."},
            ],
        }

    async def sincronizar_andamentos(self, numero_cnj: str) -> list[dict[str, Any]]:
        """
        Busca a lista cronológica (Timeline) dos andamentos judiciais deste CNJ.
        Estes são os textos que a IA vai ler para conseguir explicar pro cliente.

        Args:
            numero_cnj (str): Número do processo.

        Returns:
            Lista de dicionários [{data, descricao, tipo}]. Ordenado do mais recente para o mais antigo.
        """
        logger.info("jusbrasil_buscando_andamentos", cnj=numero_cnj)

        # Simula tempo de requisição e parsing da página/API
        await asyncio.sleep(2.0)
        _jusbrasil_requests_total.labels(
            endpoint="sincronizar_andamentos", status="ok"
        ).inc()

        # Gerando andamentos fictícios contextualizados
        hoje = datetime.now()

        extrato_mock = [
            {
                "data": hoje.isoformat(),
                "tipo": "Publicação",
                "descricao": "Publicado o Despacho Concedendo Antecipação de Tutela. Intime-se a parte ré para cumprimento em 48 horas sob pena de multa diária.",
                "caderno": "Diário de Justiça Eletrônico de São Paulo",
            },
            {
                "data": (hoje - timedelta(days=5)).isoformat(),
                "tipo": "Conclusão",
                "descricao": "Autos conclusos ao Juiz de Direito para Decisão Interlocutória.",
                "caderno": None,
            },
            {
                "data": (hoje - timedelta(days=12)).isoformat(),
                "tipo": "Petição",
                "descricao": "Juntada de Petição de Emenda à Inicial requererendo a juntada de novos documentos comprobatórios do dano sofrido.",
                "caderno": None,
            },
            {
                "data": (hoje - timedelta(days=40)).isoformat(),
                "tipo": "Distribuição",
                "descricao": "Processo distribuído por Sorteio na 3ª Vara Cível do Foro Central.",
                "caderno": "Sistema de Distribuição Automática",
            },
        ]

        return extrato_mock
