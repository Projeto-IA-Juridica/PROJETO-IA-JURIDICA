"""
PessoaIntelligenceService — B2C
=================================
Serviço mais sensível da feature de prospecção.

Regra de ouro: APENAS dados que já estão no processo público (DataJud/Jusbrasil).
Nunca coleta CPF, telefone, e-mail ou endereço. Violação dessas regras
configura infração à LGPD (art. 7º, 11) e às normas da OAB.

Revisável por DPO sem necessidade de alterações de código.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

# ---------------------------------------------------------------------------
# Tipo de entrada — definido em prospeccao/types.py (reproduzido aqui para
# referência; importe do módulo correto no seu projeto)
# ---------------------------------------------------------------------------
if TYPE_CHECKING:
    pass


@dataclass
class LitiganteEncontrado:
    """
    Representa um litigante identificado como pessoa física a partir de dados
    já públicos retornados pelo DataJud / Jusbrasil.

    ATENÇÃO: Este dataclass NÃO deve conter CPF, telefone, e-mail ou endereço.
    Se o DataJud retornar esses campos, descarte-os antes de instanciar.
    """

    nome: str  # Nome público conforme consta no processo
    polo: str  # 'ativo' | 'passivo'
    tipo_acao: str  # Ex: "Reclamação Trabalhista", "Ação de Alimentos"
    tribunal: str  # Ex: "TRT-2", "TJSP"
    fase_processual: str  # Ex: "Conhecimento", "Execução", "Recurso"
    numero_cnj: str  # Número CNJ do processo (público)
    representado: bool = False  # True se já há advogado cadastrado no polo


# ---------------------------------------------------------------------------
# Dataclass de saída — sem nenhum dado pessoal além do que consta no processo
# ---------------------------------------------------------------------------


@dataclass
class PessoaInteligencia:
    """
    Dados de inteligência sobre um litigante pessoa física.

    ⚠️  PROIBIDO adicionar: cpf, telefone, email, endereço, renda,
        dados de saúde, orientação sexual, religião ou qualquer outro
        dado pessoal além dos listados abaixo.

    Qualquer campo novo deve ser aprovado pelo DPO antes do merge.
    """

    nome: str  # Nome público do processo
    polo: str  # 'ativo' | 'passivo'
    tipo_acao: str
    tribunal: str
    fase_processual: str
    numero_cnj_exemplo: str  # Para o advogado verificar no sistema do tribunal

    # SEM: cpf · telefone · email · endereço · dados de saúde


# ---------------------------------------------------------------------------
# Palavras-chave que indicam dados especialmente sensíveis (art. 11 LGPD)
# ---------------------------------------------------------------------------

_ACOES_SENSIVEIS: frozenset[str] = frozenset(
    {
        # Saúde / condição médica
        "internação compulsória",
        "internação involuntária",
        "curatela por doença mental",
        "curatela por transtorno mental",
        "interdição por doença",
        "ação de saúde mental",
        "fornecimento de medicamento",
        "tratamento de saúde",
        "plano de saúde negativa",
        "custeio de tratamento",
        "internação psiquiátrica",
        "dependência química",
        "dependência de drogas",
        # Orientação sexual / identidade de gênero
        "retificação de registro civil",
        "mudança de nome e gênero",
        "identidade de gênero",
        "orientação sexual",
        "discriminação por orientação",
        # Religião / convicção
        "liberdade religiosa",
        "discriminação religiosa",
        "objeção de consciência",
        # Origem racial / étnica
        "discriminação racial",
        "injúria racial",
        "racismo",
        # Dados genéticos / biométricos
        "teste de paternidade",
        "exame de dna",
        "dados biométricos",
    }
)


# ---------------------------------------------------------------------------
# Serviço principal
# ---------------------------------------------------------------------------


class PessoaIntelligenceService:
    """
    Gera inteligência sobre litigantes pessoa física usando exclusivamente
    dados do processo público. Sem enriquecimento externo.
    """

    # ------------------------------------------------------------------
    # Método principal
    # ------------------------------------------------------------------

    async def enriquecer(
        self,
        litigante: LitiganteEncontrado,
    ) -> PessoaInteligencia:
        """
        Retorna um objeto PessoaInteligencia a partir dos dados públicos
        do processo. Não faz nenhuma requisição a APIs externas de dados
        pessoais (Serasa, SPC, LinkedIn, etc.).

        Raises:
            ValueError: se `validar_compliance` retornar False (ação sensível).
        """
        if not self.validar_compliance(litigante):
            raise ValueError(
                f"Lead descartado por compliance LGPD art. 11: "
                f"tipo_acao='{litigante.tipo_acao}' contém dados especialmente "
                f"sensíveis. Não prospectar."
            )

        return PessoaInteligencia(
            nome=litigante.nome,
            polo=litigante.polo,
            tipo_acao=litigante.tipo_acao,
            tribunal=litigante.tribunal,
            fase_processual=litigante.fase_processual,
            numero_cnj_exemplo=litigante.numero_cnj,
            # CPF ........... NÃO — proibido por design
            # telefone ...... NÃO — proibido por design
            # email ......... NÃO — proibido por design
        )

    # ------------------------------------------------------------------
    # Helpers de negócio
    # ------------------------------------------------------------------

    def is_lead_valido(self, litigante: LitiganteEncontrado) -> bool:
        """
        Verifica se o litigante provavelmente precisa de advogado,
        com base no tipo de ação e polo processual.

        Lógica por área:
        - Trabalhista: polo ativo (empregado) → costuma estar sem advogado
        - Consumidor: polo ativo (consumidor) → lead válido
        - Família: ambos os polos podem precisar de representação

        Retorna False também se o litigante já tiver representação cadastrada.
        """
        if litigante.representado:
            return False

        tipo = litigante.tipo_acao.lower()
        polo = litigante.polo.lower()

        trabalhista = any(
            t in tipo
            for t in (
                "trabalhista",
                "reclamação trabalhista",
                "horas extras",
                "verbas rescisórias",
                "clt",
                "fgts",
            )
        )
        consumidor = any(
            t in tipo
            for t in (
                "consumidor",
                "código de defesa",
                "cdc",
                "negativação indevida",
                "cobrança indevida",
                "recall",
                "produto defeituoso",
            )
        )
        familia = any(
            t in tipo
            for t in (
                "família",
                "divórcio",
                "alimentos",
                "guarda",
                "inventário",
                "união estável",
                "adoção",
            )
        )

        if trabalhista and polo == "ativo":
            return True
        if consumidor and polo == "ativo":
            return True
        if familia:  # Ambos os polos podem precisar de advogado
            return True

        return False

    # ------------------------------------------------------------------
    # Compliance LGPD — art. 11 (dados sensíveis)
    # ------------------------------------------------------------------

    @staticmethod
    def validar_compliance(litigante: LitiganteEncontrado) -> bool:
        """
        Retorna False (descarta o lead) se o tipo de ação envolver dados
        especialmente sensíveis conforme o art. 11 da LGPD:
        saúde, orientação sexual, religião, origem racial/étnica,
        dados genéticos ou biométricos.

        Exemplos que retornam False:
            - "internação compulsória"
            - "curatela por doença mental"
            - "retificação de registro civil"
            - "exame de DNA / teste de paternidade"

        Este método é a única porta de entrada para o enriquecimento.
        Não há exceções — se retornar False, o lead é silenciosamente
        descartado pelo chamador.
        """
        tipo_normalizado = litigante.tipo_acao.lower().strip()

        for palavra_chave in _ACOES_SENSIVEIS:
            if palavra_chave in tipo_normalizado:
                return False  # Lead descartado

        return True  # Ação pública, sem dados sensíveis detectados
