"""
feature_1_ia_personalizada/services/prospeccao/empresa_intelligence.py

Agrega dados de múltiplas fontes para um litigante pessoa jurídica (B2B).

Fluxo:
  1. Extrai ou infere o CNPJ a partir do LitiganteEncontrado.
  2. Busca paralela: ReceitaFederalClient + LinkedInClient.
  3. Monta EmpresaInteligencia com tudo que foi encontrado.
  4. Se CNPJ indisponível, cria inteligência parcial apenas com dados DataJud.
  5. Cache Redis: `empresa_intel:{cnpj}` TTL 6h.

LGPD: sócios armazenados com nome + qualificação apenas — nunca CPF.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import structlog

from feature_1_ia_personalizada.services.prospeccao.datajud_prospeccao import (
    LitiganteEncontrado,
)
from feature_1_ia_personalizada.services.prospeccao.linkedin_client import (
    ContatoLinkedIn,
    LinkedInClient,
)
from feature_1_ia_personalizada.services.prospeccao.receita_federal_client import (
    EmpresaDados,
    ReceitaFederalClient,
)
from shared.utils.validators import normalizar_cnpj, validar_cnpj

logger = structlog.get_logger(__name__)

_CACHE_TTL_S = 60 * 60 * 6  # 6h


# --------------------------------------------------------------------------
# Dataclass de resultado
# --------------------------------------------------------------------------


@dataclass
class EmpresaInteligencia:
    razao_social: str
    processos_count: int
    tipos_acao_envolvida: list[str] = field(default_factory=list)
    # None quando CNPJ não foi identificado
    cnpj: str | None = None
    situacao: str = ""           # ATIVA | BAIXADA | SUSPENSA | ...
    porte: str = ""              # MEI | ME | EPP | DEMAIS
    setor_cnae: str = ""         # descrição do CNAE principal
    # [{nome, qualificacao}] — sem CPF (LGPD)
    socios: list[dict[str, str]] = field(default_factory=list)
    contatos_linkedin: list[dict[str, str]] = field(default_factory=list)
    linkedin_disponivel: bool = False
    # True quando montada sem Receita Federal (CNPJ não identificado)
    enriquecimento_parcial: bool = False
    tribunal: str = ""
    polo: str = ""
    sem_advogado: bool = False


# --------------------------------------------------------------------------
# Serviço
# --------------------------------------------------------------------------


class EmpresaIntelligenceService:
    """
    Enriquece um litigante pessoa jurídica com dados de todas as fontes B2B.

    Uso:
        svc = EmpresaIntelligenceService(receita_client, linkedin_client, redis)
        inteligencia = await svc.enriquecer(litigante)
    """

    def __init__(
        self,
        receita: ReceitaFederalClient,
        linkedin: LinkedInClient,
        redis: Any = None,
    ) -> None:
        self._receita = receita
        self._linkedin = linkedin
        self._redis = redis

    # ------------------------------------------------------------------
    # Interface pública
    # ------------------------------------------------------------------

    async def enriquecer(
        self, litigante: LitiganteEncontrado
    ) -> EmpresaInteligencia:
        """
        Agrega dados de Receita Federal e LinkedIn para o litigante.

        Nunca levanta exceção — falhas parciais geram inteligência parcial.
        """
        cnpj = self._extrair_cnpj(litigante.nome)

        if cnpj:
            cache_key = f"empresa_intel:{cnpj}"
            cached = await self._get_cache(cache_key)
            if cached is not None:
                logger.debug("empresa_intel.cache_hit", cnpj=cnpj)
                return cached

        empresa_dados, contatos = await asyncio.gather(
            self._buscar_receita(cnpj),
            self._buscar_linkedin(litigante.nome),
        )

        inteligencia = self._montar(litigante, cnpj, empresa_dados, contatos)

        if cnpj:
            await self._set_cache(f"empresa_intel:{cnpj}", inteligencia)

        logger.info(
            "empresa_intel.enriquecida",
            nome=litigante.nome,
            cnpj=cnpj,
            enriquecimento_parcial=inteligencia.enriquecimento_parcial,
            linkedin_disponivel=inteligencia.linkedin_disponivel,
        )
        return inteligencia

    # ------------------------------------------------------------------
    # Internos — extração de CNPJ
    # ------------------------------------------------------------------

    @staticmethod
    def _extrair_cnpj(nome: str) -> str | None:
        """
        Tenta extrair um CNPJ embutido no nome da parte.

        O DataJud às vezes retorna nome no formato "EMPRESA X LTDA (12.345.678/0001-90)".
        Se não encontrar, retorna None — o enriquecimento continuará sem Receita.
        """
        import re

        match = re.search(r"\b(\d{2}\.?\d{3}\.?\d{3}[/\-]\d{4}[-\.]\d{2})\b", nome)
        if not match:
            return None
        candidato = normalizar_cnpj(match.group(1))
        return candidato if validar_cnpj(candidato) else None

    # ------------------------------------------------------------------
    # Internos — fontes externas
    # ------------------------------------------------------------------

    async def _buscar_receita(self, cnpj: str | None) -> EmpresaDados | None:
        if not cnpj:
            return None
        try:
            return await self._receita.buscar_cnpj(cnpj)
        except Exception as exc:
            logger.debug("empresa_intel.receita_erro", cnpj=cnpj, error=str(exc))
            return None

    async def _buscar_linkedin(self, nome_empresa: str) -> list[ContatoLinkedIn]:
        try:
            return await self._linkedin.buscar_funcionarios(nome_empresa)
        except Exception as exc:
            logger.debug(
                "empresa_intel.linkedin_erro",
                nome=nome_empresa,
                error=str(exc),
            )
            return []

    # ------------------------------------------------------------------
    # Internos — montagem
    # ------------------------------------------------------------------

    def _montar(
        self,
        litigante: LitiganteEncontrado,
        cnpj: str | None,
        empresa: EmpresaDados | None,
        contatos: list[ContatoLinkedIn],
    ) -> EmpresaInteligencia:
        socios: list[dict[str, str]] = []
        if empresa and empresa.socios:
            # Filtra CPF — armazena só nome e qualificação (LGPD)
            socios = [
                {
                    "nome": s.get("nome", ""),
                    "qualificacao": s.get("qualificacao", ""),
                }
                for s in empresa.socios
                if s.get("nome")
            ]

        contatos_dict = [
            {
                "nome": c.nome,
                "cargo": c.cargo,
                "url_perfil": c.url_perfil or "",
            }
            for c in contatos
        ]

        return EmpresaInteligencia(
            cnpj=cnpj,
            razao_social=empresa.razao_social if empresa else litigante.nome,
            situacao=empresa.situacao if empresa else "",
            porte=empresa.porte if empresa else "",
            setor_cnae=empresa.cnae_descricao if empresa else "",
            socios=socios,
            processos_count=litigante.processos_count,
            tipos_acao_envolvida=[litigante.tipo_acao],
            contatos_linkedin=contatos_dict,
            linkedin_disponivel=self._linkedin.disponivel,
            enriquecimento_parcial=(empresa is None),
            tribunal=litigante.tribunal,
            polo=litigante.polo,
            sem_advogado=litigante.sem_advogado,
        )

    # ------------------------------------------------------------------
    # Internos — cache
    # ------------------------------------------------------------------

    async def _get_cache(self, key: str) -> EmpresaInteligencia | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw:
                data = json.loads(raw)
                return EmpresaInteligencia(**data)
        except (TypeError, KeyError) as exc:
            logger.debug(
                "empresa_intel.cache_schema_error", key=key, error=str(exc)
            )
        except Exception as exc:
            logger.debug("empresa_intel.cache_erro", key=key, error=str(exc))
        return None

    async def _set_cache(self, key: str, intel: EmpresaInteligencia) -> None:
        if self._redis is None:
            return
        try:
            payload = {
                "cnpj": intel.cnpj,
                "razao_social": intel.razao_social,
                "situacao": intel.situacao,
                "porte": intel.porte,
                "setor_cnae": intel.setor_cnae,
                "socios": intel.socios,
                "processos_count": intel.processos_count,
                "tipos_acao_envolvida": intel.tipos_acao_envolvida,
                "contatos_linkedin": intel.contatos_linkedin,
                "linkedin_disponivel": intel.linkedin_disponivel,
                "enriquecimento_parcial": intel.enriquecimento_parcial,
                "tribunal": intel.tribunal,
                "polo": intel.polo,
                "sem_advogado": intel.sem_advogado,
            }
            await self._redis.setex(
                key,
                _CACHE_TTL_S,
                json.dumps(payload, ensure_ascii=False),
            )
        except Exception:
            pass
