"""
MatchingService
===============
Cruza o DNA do escritório com os dados de inteligência do lead
(empresa B2B ou pessoa física B2C) e devolve score + abordagem sugerida.

Fluxo:
    1. calcular_score detecta o tipo do lead via isinstance
    2. Delega para _score_heuristico_empresa ou _score_heuristico_pessoa
    3. Score < 30  → retorna sem chamar a Claude (gerado_por_ia=False)
    4. Score ≥ 30  → chama Claude para refinar score, motivo e abordagem
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field

import httpx

from feature_1_ia_personalizada.services.prospeccao.dna_advogado import DNAEscritorio
from feature_1_ia_personalizada.services.prospeccao.empresa_intelligence import EmpresaInteligencia
from feature_1_ia_personalizada.services.prospeccao.pessoa_intelligence import PessoaInteligencia

# ---------------------------------------------------------------------------
# Dataclass de saída
# ---------------------------------------------------------------------------


@dataclass
class ResultadoMatch:
    score: int
    motivo: str
    abordagem_sugerida: str
    gerado_por_ia: bool
    tipo_lead: str  # 'empresa' | 'pessoa'
    componentes: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_MATCH_SCORE_EMPRESA = """
Você é um consultor de desenvolvimento de negócios para escritórios de advocacia.
Receberá o perfil estratégico (DNA) de um escritório e dados públicos de uma empresa
identificada como potencial lead B2B.

Sua tarefa:
1. Revisar o score heurístico já calculado e ajustá-lo se necessário (0-100).
2. Redigir um "motivo" objetivo (1-2 frases) explicando por que este lead é relevante.
3. Sugerir uma abordagem de prospecção profissional e ética.
   - Foque em valor jurídico: como o escritório pode resolver o problema da empresa.
   - Não use cold call de tom agressivo.
   - Baseie a abordagem em dados concretos dos processos públicos da empresa.

Responda APENAS em JSON com a estrutura:
{"score": <int 0-100>, "motivo": "<string>", "abordagem_sugerida": "<string>"}
""".strip()

SYSTEM_PROMPT_MATCH_SCORE_PESSOA = """
Você é um consultor de desenvolvimento de negócios para escritórios de advocacia.
Receberá o perfil estratégico (DNA) de um escritório e dados de um litigante
pessoa física identificado como potencial lead B2C.

⚠️ RESTRIÇÕES OBRIGATÓRIAS DE COMPLIANCE:
- NÃO mencione dados pessoais (CPF, telefone, email, endereço) — eles não existem aqui.
- NÃO sugira cold call ou contato direto por número pessoal.
- A abordagem DEVE ser baseada exclusivamente no processo público.
- Canais permitidos: publicação no processo, correspondência via tribunal, anúncio
  segmentado por perfil processual, ou indicação de terceiros.

Sua tarefa:
1. Revisar o score heurístico já calculado e ajustá-lo se necessário (0-100).
2. Redigir um "motivo" objetivo (1-2 frases) explicando por que este lead é relevante.
3. Sugerir uma abordagem ética e legal de como o escritório pode chegar até essa pessoa
   sem violar LGPD ou normas da OAB.

Responda APENAS em JSON com a estrutura:
{"score": <int 0-100>, "motivo": "<string>", "abordagem_sugerida": "<string>"}
""".strip()


# ---------------------------------------------------------------------------
# Serviço
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_MODELO_CLAUDE = "claude-sonnet-4-20250514"
_SCORE_MINIMO_IA = 30


class MatchingService:
    """
    Calcula score de compatibilidade entre o DNA do escritório e um lead.
    Suporta leads B2B (EmpresaInteligencia) e B2C (PessoaInteligencia).
    """

    def __init__(self, anthropic_api_key: str | None = None) -> None:
        self._api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")

    # ------------------------------------------------------------------
    # Método público principal
    # ------------------------------------------------------------------

    async def calcular_score(
        self,
        dna: DNAEscritorio | None,
        inteligencia: EmpresaInteligencia | PessoaInteligencia,
    ) -> ResultadoMatch:
        """
        Detecta o tipo do lead e delega para o método privado correto.
        Se o score heurístico for < 30, retorna sem chamar a Claude.
        """
        tipo_lead = "empresa" if isinstance(inteligencia, EmpresaInteligencia) else "pessoa"

        if dna is None or getattr(dna, "dados_insuficientes", False):
            return ResultadoMatch(
                score=40,
                motivo="DNA do escritório não disponível — score genérico baseado nos dados do lead.",
                abordagem_sugerida=(
                    "Gere o DNA do escritório (POST /prospeccao/dna/atualizar) "
                    "para obter análise personalizada e abordagem sugerida."
                ),
                gerado_por_ia=False,
                tipo_lead=tipo_lead,
            )

        if isinstance(inteligencia, EmpresaInteligencia):
            score_bruto, componentes = self._score_heuristico_empresa(dna, inteligencia)
            tipo_lead = "empresa"
            system_prompt = SYSTEM_PROMPT_MATCH_SCORE_EMPRESA
        elif isinstance(inteligencia, PessoaInteligencia):
            score_bruto, componentes = self._score_heuristico_pessoa(dna, inteligencia)
            tipo_lead = "pessoa"
            system_prompt = SYSTEM_PROMPT_MATCH_SCORE_PESSOA
        else:
            raise TypeError(
                f"Tipo de inteligência não suportado: {type(inteligencia).__name__}. "
                "Esperado: EmpresaInteligencia ou PessoaInteligencia."
            )

        if score_bruto < _SCORE_MINIMO_IA:
            return ResultadoMatch(
                score=score_bruto,
                motivo="Score abaixo do limiar mínimo — lead não qualificado.",
                abordagem_sugerida="",
                gerado_por_ia=False,
                tipo_lead=tipo_lead,
                componentes=componentes,
            )

        return await self._refinar_com_claude(
            dna=dna,
            inteligencia=inteligencia,
            score_heuristico=score_bruto,
            componentes=componentes,
            tipo_lead=tipo_lead,
            system_prompt=system_prompt,
        )

    # ------------------------------------------------------------------
    # Heurística B2B — EmpresaInteligencia
    # ------------------------------------------------------------------

    def _score_heuristico_empresa(
        self,
        dna: DNAEscritorio,
        empresa: EmpresaInteligencia,
    ) -> tuple[int, dict]:
        """
        Componentes:
            +30  processos da empresa em tipos de ação = especialidades do escritório
            +20  setor CNAE em dna.setores_alvo
            +15  empresa com 3+ processos (demanda ativa)
            +15  contatos LinkedIn encontrados
            +10  porte MÉDIA ou GRANDE
            +10  situação ATIVA
        """
        componentes: dict[str, int] = {}

        especialidades_lower = {e.lower() for e in dna.especialidades}
        tipos_empresa_lower = {t.lower() for t in empresa.tipos_acao_envolvida}
        if especialidades_lower & tipos_empresa_lower:
            componentes["especialidade_match"] = 30

        setores_lower = {s.lower() for s in dna.setores_alvo}
        if empresa.setor_cnae.lower() in setores_lower:
            componentes["setor_alvo"] = 20

        if empresa.processos_count >= 3:
            componentes["demanda_ativa"] = 15

        if len(empresa.contatos_linkedin) > 0:
            componentes["linkedin_contatos"] = 15

        if empresa.porte.upper() in ("MEDIA", "GRANDE"):
            componentes["porte_relevante"] = 10

        if empresa.situacao.upper() == "ATIVA":
            componentes["situacao_ativa"] = 10

        return min(sum(componentes.values()), 100), componentes

    # ------------------------------------------------------------------
    # Heurística B2C — PessoaInteligencia
    # ------------------------------------------------------------------

    def _score_heuristico_pessoa(
        self,
        dna: DNAEscritorio,
        pessoa: PessoaInteligencia,
    ) -> tuple[int, dict]:
        """
        Componentes:
            +35  tipo de ação = especialidade do escritório (sinal mais forte)
            +25  polo compatível com o perfil típico de cliente do escritório
            +20  fase processual inicial (pessoa pode ainda não ter advogado)
            +20  tipo de ação com alta recorrência no escritório (> 30% dos processos)
        """
        componentes: dict[str, int] = {}

        tipo_lower = pessoa.tipo_acao.lower()
        especialidades_lower = {e.lower() for e in dna.especialidades}

        if any(esp in tipo_lower for esp in especialidades_lower):
            componentes["especialidade_match"] = 35

        # Polo compatível: se o escritório é B2C pessoa, o polo ativo é o mais comum
        polo_preferido = "ativo" if dna.tipo_lead_predominante in ("pessoa", "ambos") else "ativo"
        if pessoa.polo.lower() == polo_preferido:
            componentes["polo_compativel"] = 25

        fases_iniciais = {"conhecimento", "inicial", "distribuição", "petição inicial"}
        if pessoa.fase_processual.lower() in fases_iniciais:
            componentes["fase_inicial"] = 20

        # Tipos recorrentes: top_tipos_acao com percentual > 30%
        recorrentes_lower = {
            t["tipo"].lower() for t in dna.top_tipos_acao if t.get("percentual", 0) > 30
        }
        if any(rec in tipo_lower for rec in recorrentes_lower):
            componentes["alta_recorrencia"] = 20

        return min(sum(componentes.values()), 100), componentes

    # ------------------------------------------------------------------
    # Refinamento com Claude
    # ------------------------------------------------------------------

    async def _refinar_com_claude(
        self,
        dna: DNAEscritorio,
        inteligencia: EmpresaInteligencia | PessoaInteligencia,
        score_heuristico: int,
        componentes: dict,
        tipo_lead: str,
        system_prompt: str,
    ) -> ResultadoMatch:
        """
        Chama a API da Claude para refinar o score e gerar motivo + abordagem.
        Em caso de falha na API, retorna o resultado heurístico sem quebrar o fluxo.
        """
        payload_usuario = {
            "dna_escritorio": {
                "especialidades": dna.especialidades,
                "setores_alvo": dna.setores_alvo,
                "tipo_lead_predominante": dna.tipo_lead_predominante,
                "top_tipos_acao": dna.top_tipos_acao,
                "perfil_cliente_ideal": dna.perfil_cliente_ideal,
            },
            "lead": {k: v for k, v in asdict(inteligencia).items() if v not in (None, "", [])},
            "score_heuristico": score_heuristico,
            "componentes_score": componentes,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    _ANTHROPIC_API_URL,
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": _MODELO_CLAUDE,
                        "max_tokens": 512,
                        "system": system_prompt,
                        "messages": [
                            {
                                "role": "user",
                                "content": json.dumps(payload_usuario, ensure_ascii=False),
                            }
                        ],
                    },
                )
                response.raise_for_status()
                data = response.json()

            texto = data["content"][0]["text"].strip()
            if texto.startswith("```"):
                texto = texto.split("```")[1]
                if texto.startswith("json"):
                    texto = texto[4:]
            resultado_ia = json.loads(texto)

            return ResultadoMatch(
                score=int(resultado_ia.get("score", score_heuristico)),
                motivo=resultado_ia.get("motivo", ""),
                abordagem_sugerida=resultado_ia.get("abordagem_sugerida", ""),
                gerado_por_ia=True,
                tipo_lead=tipo_lead,
                componentes=componentes,
            )

        except Exception as exc:
            logger.warning(
                "Falha ao refinar score com Claude: %s. Retornando score heurístico.", exc
            )
            return ResultadoMatch(
                score=score_heuristico,
                motivo="Score calculado por heurística (IA indisponível).",
                abordagem_sugerida="",
                gerado_por_ia=False,
                tipo_lead=tipo_lead,
                componentes=componentes,
            )
