"""
Testes unitários — PessoaIntelligenceService
=============================================
Verifica que:
- PessoaInteligencia NÃO contém CPF, telefone, email ou endereço
- validar_compliance descarta ações com dados sensíveis (art. 11 LGPD)
- validar_compliance aprova ações trabalhistas e de consumidor
- is_lead_valido retorna corretamente por tipo de ação e polo
- Litigante já representado é descartado
"""

from __future__ import annotations

import dataclasses

import pytest

from feature_1_ia_personalizada.services.prospeccao.pessoa_intelligence import (
    LitiganteEncontrado,
    PessoaInteligencia,
    PessoaIntelligenceService,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _litigante(
    *,
    nome: str = "João da Silva",
    polo: str = "ativo",
    tipo_acao: str = "Reclamação Trabalhista",
    tribunal: str = "TRT-2",
    fase: str = "Conhecimento",
    numero_cnj: str = "0001234-56.2024.5.02.0100",
    representado: bool = False,
) -> LitiganteEncontrado:
    return LitiganteEncontrado(
        nome=nome,
        polo=polo,
        tipo_acao=tipo_acao,
        tribunal=tribunal,
        fase_processual=fase,
        numero_cnj=numero_cnj,
        representado=representado,
    )


# ---------------------------------------------------------------------------
# Compliance LGPD — campos proibidos no dataclass
# ---------------------------------------------------------------------------

class TestPessoaInteligenciaLGPD:
    def test_dataclass_nao_tem_cpf(self):
        """PessoaInteligencia não deve ter campo cpf."""
        campos = {f.name for f in dataclasses.fields(PessoaInteligencia)}
        assert "cpf" not in campos

    def test_dataclass_nao_tem_telefone(self):
        campos = {f.name for f in dataclasses.fields(PessoaInteligencia)}
        assert "telefone" not in campos

    def test_dataclass_nao_tem_email(self):
        campos = {f.name for f in dataclasses.fields(PessoaInteligencia)}
        assert "email" not in campos

    def test_dataclass_nao_tem_endereco(self):
        campos = {f.name for f in dataclasses.fields(PessoaInteligencia)}
        assert "endereco" not in campos

    def test_dataclass_tem_campos_publicos_permitidos(self):
        """PessoaInteligencia deve ter apenas dados do processo público."""
        campos = {f.name for f in dataclasses.fields(PessoaInteligencia)}
        esperados = {"nome", "polo", "tipo_acao", "tribunal", "fase_processual", "numero_cnj_exemplo"}
        assert esperados.issubset(campos)


# ---------------------------------------------------------------------------
# validar_compliance — ações sensíveis (art. 11 LGPD)
# ---------------------------------------------------------------------------

class TestValidarCompliance:
    @pytest.mark.parametrize("tipo_acao", [
        "internação compulsória",
        "INTERNAÇÃO COMPULSÓRIA",           # case-insensitive
        "Internação Compulsória",
        "curatela por doença mental",
        "internação involuntária por transtorno",
        "retificação de registro civil",
        "exame de dna - investigação de paternidade",
        "teste de paternidade",
        "discriminação racial",
        "racismo no ambiente de trabalho",
        "orientação sexual - discriminação",
        "liberdade religiosa",
    ])
    def test_acoes_sensiveis_retornam_false(self, tipo_acao: str):
        """Ações com dados sensíveis devem ser descartadas."""
        litigante = _litigante(tipo_acao=tipo_acao)
        assert PessoaIntelligenceService.validar_compliance(litigante) is False

    @pytest.mark.parametrize("tipo_acao", [
        "Reclamação Trabalhista",
        "Horas Extras",
        "Ação de Divórcio",
        "Ação de Alimentos",
        "Ação de Cobrança",
        "Indenização por Danos Morais",
        "Execução de Título Extrajudicial",
        "Negativação Indevida",
    ])
    def test_acoes_publicas_retornam_true(self, tipo_acao: str):
        """Ações comuns sem dados sensíveis devem ser aprovadas."""
        litigante = _litigante(tipo_acao=tipo_acao)
        assert PessoaIntelligenceService.validar_compliance(litigante) is True


# ---------------------------------------------------------------------------
# enriquecer — resultado e compliance
# ---------------------------------------------------------------------------

class TestEnriquecer:
    @pytest.mark.asyncio
    async def test_enriquecer_retorna_pessoa_inteligencia(self):
        """Enriquecer deve retornar PessoaInteligencia com os dados do litigante."""
        svc = PessoaIntelligenceService()
        litigante = _litigante(
            nome="Maria Souza",
            polo="ativo",
            tipo_acao="Reclamação Trabalhista",
            tribunal="TRT-2",
            fase="Conhecimento",
            numero_cnj="0001234-56.2024.5.02.0100",
        )
        intel = await svc.enriquecer(litigante)

        assert intel.nome == "Maria Souza"
        assert intel.polo == "ativo"
        assert intel.tipo_acao == "Reclamação Trabalhista"
        assert intel.tribunal == "TRT-2"
        assert intel.numero_cnj_exemplo == "0001234-56.2024.5.02.0100"

    @pytest.mark.asyncio
    async def test_enriquecer_levanta_para_acao_sensivel(self):
        """Enriquecer deve levantar ValueError para ação com dados sensíveis."""
        svc = PessoaIntelligenceService()
        litigante = _litigante(tipo_acao="curatela por doença mental")

        with pytest.raises(ValueError, match="LGPD"):
            await svc.enriquecer(litigante)


# ---------------------------------------------------------------------------
# is_lead_valido — lógica de negócio
# ---------------------------------------------------------------------------

class TestIsLeadValido:
    def test_trabalhista_polo_ativo_valido(self):
        svc = PessoaIntelligenceService()
        lit = _litigante(tipo_acao="Reclamação Trabalhista", polo="ativo")
        assert svc.is_lead_valido(lit) is True

    def test_trabalhista_polo_passivo_invalido(self):
        """Empresa no polo passivo não é o lead que precisa de advogado."""
        svc = PessoaIntelligenceService()
        lit = _litigante(tipo_acao="Reclamação Trabalhista", polo="passivo")
        assert svc.is_lead_valido(lit) is False

    def test_consumidor_polo_ativo_valido(self):
        svc = PessoaIntelligenceService()
        lit = _litigante(tipo_acao="Código de Defesa do Consumidor", polo="ativo")
        assert svc.is_lead_valido(lit) is True

    def test_familia_ambos_polos_validos(self):
        svc = PessoaIntelligenceService()
        for polo in ("ativo", "passivo"):
            lit = _litigante(tipo_acao="Ação de Divórcio", polo=polo)
            assert svc.is_lead_valido(lit) is True, f"polo={polo} deveria ser válido em família"

    def test_representado_invalido(self):
        """Parte já representada não deve ser prospectada."""
        svc = PessoaIntelligenceService()
        lit = _litigante(
            tipo_acao="Reclamação Trabalhista", polo="ativo", representado=True
        )
        assert svc.is_lead_valido(lit) is False
