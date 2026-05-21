"""
Testes de integração — Rotas /prospeccao/*
==========================================
Cobre os critérios de aceite da task 3.14.

Padrão: chamadas diretas às funções de rota com mocks de dependências
(mesmo padrão usado em test_onboarding_fluxo.py neste projeto).

Critérios testados:
1. Role guard: cliente → 403, advogado → 200
2. POST /prospeccao/descobrir com mock DataJud → leads salvos no banco
3. Pipeline B2C: aviso_lgpd presente no response
4. Lead de outro escritório → 403 no PATCH
5. Deduplicação: mesmo CNPJ pesquisado duas vezes → atualiza, não duplica
"""

from __future__ import annotations

from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from feature_1_ia_personalizada.services.prospeccao.datajud_prospeccao import LitiganteEncontrado
from feature_1_ia_personalizada.services.prospeccao.dna_advogado import DNAEscritorio
from feature_1_ia_personalizada.services.prospeccao.empresa_intelligence import EmpresaInteligencia
from feature_1_ia_personalizada.services.prospeccao.matching import ResultadoMatch
from feature_1_ia_personalizada.services.prospeccao.pessoa_intelligence import PessoaInteligencia
from shared.schemas.prospeccao import (
    DescobertaRequest,
    LeadStatusUpdate,
    PipelineResponse,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _payload(role: str = "advogado", escritorio_id: int = 1, user_id: int = 10) -> dict:
    return {"role": role, "escritorio_id": escritorio_id, "sub": str(user_id)}


def _dna(escritorio_id: int = 1, tipo: str = "empresa") -> DNAEscritorio:
    return DNAEscritorio(
        escritorio_id=escritorio_id,
        especialidades=["Direito Trabalhista"],
        setores_alvo=["Indústria"],
        tipo_lead_predominante=tipo,
        perfil_cliente_ideal="Empresas com demandas trabalhistas",
        diferenciais=["Agilidade"],
        top_tipos_acao=[{"tipo": "Reclamação Trabalhista", "contagem": 50, "percentual": 83.0}],
        dados_insuficientes=False,
    )


def _litigante_pj() -> LitiganteEncontrado:
    return LitiganteEncontrado(
        nome="EMPRESA TESTE LTDA (11.222.333/0001-81)",
        tipo="pessoa_juridica",
        polo="passivo",
        processos_count=4,
        numero_cnj_exemplo="0001234-56.2024.5.02.0100",
        tipo_acao="Reclamação Trabalhista",
        tribunal="TRT2",
        sem_advogado=False,
    )


def _empresa_intel(cnpj: str = "11222333000181") -> EmpresaInteligencia:
    return EmpresaInteligencia(
        razao_social="EMPRESA TESTE LTDA",
        processos_count=4,
        cnpj=cnpj,
        situacao="ATIVA",
        porte="MEDIA",
        setor_cnae="Indústria",
        socios=[],
        contatos_linkedin=[],
        linkedin_disponivel=False,
        enriquecimento_parcial=False,
    )


def _resultado(score: int = 75, tipo: str = "empresa") -> ResultadoMatch:
    return ResultadoMatch(
        score=score,
        motivo="Alta demanda trabalhista no setor-alvo.",
        abordagem_sugerida="Contatar o sócio-administrador.",
        gerado_por_ia=True,
        tipo_lead=tipo,
        componentes={},
    )


def _make_lead_mock(id: int = 1, escritorio_id: int = 1, score: int = 75, tipo: str = "empresa"):
    """Simula um LeadProspeccao retornado pelo banco."""
    lead = MagicMock()
    lead.id = id
    lead.escritorio_id = escritorio_id
    lead.tipo_lead = tipo
    lead.nome = "EMPRESA TESTE LTDA"
    lead.score_match = score
    lead.score_motivo = "Alta demanda."
    lead.abordagem_sugerida = "Contatar sócio."
    lead.status = "novo"
    lead.notas_advogado = None
    lead.fonte_descoberta = "Reclamação Trabalhista"
    lead.cnpj = "11222333000181"
    lead.empresa_setor = "Indústria"
    lead.empresa_porte = "MEDIA"
    lead.socios = []
    lead.contatos_linkedin = []
    lead.linkedin_disponivel = False
    lead.polo_processo = None
    lead.tipo_acao_origem = None
    lead.numero_cnj_exemplo = None
    lead.processos_publicos_count = 4
    from datetime import datetime

    lead.created_at = datetime.now(UTC)
    lead.criado_em = lead.created_at
    return lead


# ---------------------------------------------------------------------------
# 1. Role guard — require_advogado
# ---------------------------------------------------------------------------


class TestRoleGuard:
    @pytest.mark.asyncio
    async def test_cliente_recebe_403(self):
        """Role 'cliente' deve levantar 403 ao chamar require_advogado."""
        from feature_1_ia_personalizada.api.middleware.auth import require_advogado

        payload = _payload(role="cliente")
        with pytest.raises(HTTPException) as exc:
            require_advogado(payload=payload)

        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_estagiario_recebe_403(self):
        payload = _payload(role="estagiario")
        from feature_1_ia_personalizada.api.middleware.auth import require_advogado

        with pytest.raises(HTTPException) as exc:
            require_advogado(payload=payload)

        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_advogado_passa(self):
        from feature_1_ia_personalizada.api.middleware.auth import require_advogado

        payload = _payload(role="advogado")
        result = require_advogado(payload=payload)
        assert result["role"] == "advogado"

    @pytest.mark.asyncio
    async def test_admin_passa(self):
        from feature_1_ia_personalizada.api.middleware.auth import require_advogado

        payload = _payload(role="admin")
        result = require_advogado(payload=payload)
        assert result["role"] == "admin"

    @pytest.mark.asyncio
    async def test_get_escritorio_id_retorna_int(self):
        from feature_1_ia_personalizada.api.middleware.auth import get_escritorio_id_advogado

        payload = _payload(escritorio_id=42)
        eid = get_escritorio_id_advogado(payload=payload)
        assert eid == 42

    @pytest.mark.asyncio
    async def test_get_advogado_id_retorna_int(self):
        from feature_1_ia_personalizada.api.middleware.auth import get_advogado_id

        payload = _payload(user_id=99)
        uid = get_advogado_id(payload=payload)
        assert uid == 99


# ---------------------------------------------------------------------------
# 2. GET /prospeccao/dna — retorna DNA ou dados_insuficientes
# ---------------------------------------------------------------------------


class TestGetDNA:
    @pytest.mark.asyncio
    async def test_retorna_dna_quando_disponivel(self):
        from feature_1_ia_personalizada.api.routes.prospeccao import get_dna

        dna = _dna()
        dna_service = MagicMock()
        dna_service.obter_dna_salvo = AsyncMock(return_value=dna)
        db = AsyncMock()

        import feature_1_ia_personalizada.api.routes.prospeccao as mod

        original = mod._dna_service
        mod._dna_service = dna_service

        try:
            result = await get_dna(escritorio_id=1, db=db)
        finally:
            mod._dna_service = original

        assert result.tipo_lead_predominante == "empresa"
        assert not result.dados_insuficientes

    @pytest.mark.asyncio
    async def test_retorna_dados_insuficientes_quando_sem_dna(self):
        from feature_1_ia_personalizada.api.routes.prospeccao import get_dna
        from shared.schemas.prospeccao import DNAEscritorioResponse

        dna_service = MagicMock()
        dna_service.obter_dna_salvo = AsyncMock(return_value=None)
        db = AsyncMock()

        import feature_1_ia_personalizada.api.routes.prospeccao as mod

        original = mod._dna_service
        mod._dna_service = dna_service

        try:
            result = await get_dna(escritorio_id=1, db=db)
        finally:
            mod._dna_service = original

        assert isinstance(result, DNAEscritorioResponse)
        assert result.dados_insuficientes is True


# ---------------------------------------------------------------------------
# 3. POST /prospeccao/descobrir — salva lead e filtra por score_minimo
# ---------------------------------------------------------------------------


class TestDescobrirLeads:
    @pytest.mark.asyncio
    async def test_descobrir_salva_lead_com_score_suficiente(self):
        from feature_1_ia_personalizada.api.routes.prospeccao import descobrir_leads

        lead_mock = _make_lead_mock(score=75)

        db = AsyncMock()
        # Simula: não encontra lead existente → cria novo
        result_empty = MagicMock()
        result_empty.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=result_empty)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()

        # Simula o refresh retornando o mock com todos os campos
        async def _refresh(obj):
            obj.id = 1
            obj.created_at = lead_mock.created_at
            obj.criado_em = lead_mock.created_at

        db.refresh = AsyncMock(side_effect=_refresh)

        import feature_1_ia_personalizada.api.routes.prospeccao as mod

        mocks = {
            "_dna_service": MagicMock(obter_dna_salvo=AsyncMock(return_value=_dna())),
            "_datajud": MagicMock(buscar_litigantes=AsyncMock(return_value=[_litigante_pj()])),
            "_empresa_svc": MagicMock(
                enriquecer=AsyncMock(return_value=_empresa_intel()),
                linkedin_disponivel=AsyncMock(return_value=False),
            ),
            "_matching_svc": MagicMock(calcular_score=AsyncMock(return_value=_resultado(75))),
        }
        originals = {k: getattr(mod, k) for k in mocks}
        for k, v in mocks.items():
            setattr(mod, k, v)

        try:
            body = DescobertaRequest(
                tipo_lead="empresa",
                tipo_acao="Reclamação Trabalhista",
                tribunal="TRT2",
                limite=10,
                score_minimo=40,
            )
            result = await descobrir_leads(body=body, escritorio_id=1, db=db)
        finally:
            for k, v in originals.items():
                setattr(mod, k, v)

        assert isinstance(result, PipelineResponse)
        assert result.total == 1
        assert result.leads[0].score_match == 75

    @pytest.mark.asyncio
    async def test_lead_abaixo_score_minimo_descartado(self):
        import feature_1_ia_personalizada.api.routes.prospeccao as mod
        from feature_1_ia_personalizada.api.routes.prospeccao import descobrir_leads

        mocks = {
            "_dna_service": MagicMock(obter_dna_salvo=AsyncMock(return_value=_dna())),
            "_datajud": MagicMock(buscar_litigantes=AsyncMock(return_value=[_litigante_pj()])),
            "_empresa_svc": MagicMock(
                enriquecer=AsyncMock(return_value=_empresa_intel()),
                linkedin_disponivel=AsyncMock(return_value=False),
            ),
            "_matching_svc": MagicMock(calcular_score=AsyncMock(return_value=_resultado(15))),
        }
        originals = {k: getattr(mod, k) for k in mocks}
        for k, v in mocks.items():
            setattr(mod, k, v)

        db = AsyncMock()
        try:
            body = DescobertaRequest(
                tipo_lead="empresa",
                tipo_acao="Reclamação Trabalhista",
                limite=10,
                score_minimo=40,
            )
            result = await descobrir_leads(body=body, escritorio_id=1, db=db)
        finally:
            for k, v in originals.items():
                setattr(mod, k, v)

        assert result.total == 0


# ---------------------------------------------------------------------------
# 4. Pipeline B2C — aviso_lgpd injetado automaticamente
# ---------------------------------------------------------------------------


class TestPipelineB2C:
    @pytest.mark.asyncio
    async def test_aviso_lgpd_presente_para_leads_pessoa(self):
        from feature_1_ia_personalizada.api.routes.prospeccao import descobrir_leads

        litigante_b2c = LitiganteEncontrado(
            nome="João Trabalhador",
            tipo="pessoa_fisica",
            polo="ativo",
            processos_count=1,
            numero_cnj_exemplo="0009876-54.2024.5.02.0100",
            tipo_acao="Reclamação Trabalhista",
            tribunal="TRT2",
            sem_advogado=True,
        )
        pessoa = PessoaInteligencia(
            nome="João Trabalhador",
            polo="ativo",
            tipo_acao="Reclamação Trabalhista",
            tribunal="TRT2",
            fase_processual="Conhecimento",
            numero_cnj_exemplo="0009876-54.2024.5.02.0100",
        )
        resultado_b2c = _resultado(score=65, tipo="pessoa")

        lead_mock = _make_lead_mock(tipo="pessoa")
        lead_mock.tipo_lead = "pessoa"
        lead_mock.cnpj = None
        lead_mock.numero_cnj_exemplo = "0009876-54.2024.5.02.0100"

        db = AsyncMock()
        result_empty = MagicMock()
        result_empty.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=result_empty)
        db.commit = AsyncMock()
        db.add = MagicMock()

        async def _refresh(obj):
            obj.id = 1
            obj.created_at = lead_mock.created_at
            obj.criado_em = lead_mock.created_at
            obj.tipo_lead = "pessoa"
            obj.nome = "João Trabalhador"
            obj.score_match = 65
            obj.score_motivo = "Lead trabalhista B2C."
            obj.abordagem_sugerida = "Via processo."
            obj.status = "novo"
            obj.notas_advogado = None
            obj.fonte_descoberta = "Reclamação Trabalhista"
            obj.cnpj = None
            obj.empresa_setor = None
            obj.empresa_porte = None
            obj.socios = []
            obj.contatos_linkedin = []
            obj.linkedin_disponivel = False
            obj.polo_processo = "ativo"
            obj.tipo_acao_origem = "Reclamação Trabalhista"
            obj.numero_cnj_exemplo = "0009876-54.2024.5.02.0100"
            obj.processos_publicos_count = 1

        db.refresh = AsyncMock(side_effect=_refresh)

        import feature_1_ia_personalizada.api.routes.prospeccao as mod

        dna_b2c = DNAEscritorio(
            escritorio_id=1,
            especialidades=["Direito Trabalhista"],
            setores_alvo=["Trabalhadores CLT"],
            tipo_lead_predominante="pessoa",
            perfil_cliente_ideal="Trabalhadores sem representação",
            diferenciais=["Atendimento rápido"],
            top_tipos_acao=[{"tipo": "Reclamação Trabalhista", "contagem": 80, "percentual": 80.0}],
            dados_insuficientes=False,
        )
        mocks = {
            "_dna_service": MagicMock(obter_dna_salvo=AsyncMock(return_value=dna_b2c)),
            "_datajud": MagicMock(buscar_litigantes=AsyncMock(return_value=[litigante_b2c])),
            "_pessoa_svc": MagicMock(
                validar_compliance=MagicMock(return_value=True),
                enriquecer=AsyncMock(return_value=pessoa),
            ),
            "_matching_svc": MagicMock(calcular_score=AsyncMock(return_value=resultado_b2c)),
            "_empresa_svc": MagicMock(linkedin_disponivel=AsyncMock(return_value=False)),
        }
        originals = {k: getattr(mod, k) for k in mocks}
        for k, v in mocks.items():
            setattr(mod, k, v)

        try:
            body = DescobertaRequest(
                tipo_lead="pessoa",
                tipo_acao="Reclamação Trabalhista",
                limite=10,
                score_minimo=40,
            )
            result = await descobrir_leads(body=body, escritorio_id=1, db=db)
        finally:
            for k, v in originals.items():
                setattr(mod, k, v)

        assert result.aviso_lgpd is not None
        assert "LGPD" in result.aviso_lgpd or "OAB" in result.aviso_lgpd

    def test_pipeline_response_montar_injeta_aviso_b2c(self):
        """PipelineResponse.montar injeta aviso_lgpd quando há leads pessoa."""
        from datetime import datetime

        from shared.schemas.prospeccao import LeadProspeccaoResponse

        def _lead_response(tipo: str) -> LeadProspeccaoResponse:
            return LeadProspeccaoResponse(
                id=1,
                tipo_lead=tipo,
                nome="Lead Teste",
                score_match=75,
                score_motivo="Motivo",
                abordagem_sugerida="Abordagem",
                status="novo",
                notas_advogado=None,
                fonte_descoberta="Reclamação",
                criado_em=datetime.now(UTC),
            )

        # Sem leads B2C → sem aviso
        leads_empresa = [_lead_response("empresa")]
        resp = PipelineResponse.montar(
            leads=leads_empresa,
            dna_disponivel=True,
            linkedin_disponivel=False,
        )
        assert resp.aviso_lgpd is None

        # Com lead B2C → com aviso
        leads_b2c = [_lead_response("pessoa")]
        resp_b2c = PipelineResponse.montar(
            leads=leads_b2c,
            dna_disponivel=True,
            linkedin_disponivel=False,
        )
        assert resp_b2c.aviso_lgpd is not None
        assert "LGPD" in resp_b2c.aviso_lgpd


# ---------------------------------------------------------------------------
# 5. Isolamento — lead de outro escritório → 403
# ---------------------------------------------------------------------------


class TestIsolamentoEscritorios:
    @pytest.mark.asyncio
    async def test_patch_lead_outro_escritorio_retorna_403(self):
        from feature_1_ia_personalizada.api.routes.prospeccao import atualizar_status

        # Lead pertence ao escritório 1; requisição vem do escritório 2
        lead = MagicMock()
        lead.escritorio_id = 1
        lead.id = 99

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=lead)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        body = LeadStatusUpdate(status="contatado")

        with pytest.raises(HTTPException) as exc:
            await atualizar_status(
                lead_id=99,
                body=body,
                escritorio_id=2,  # escritório diferente
                db=db,
            )

        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_patch_lead_nao_encontrado_retorna_404(self):
        from feature_1_ia_personalizada.api.routes.prospeccao import atualizar_status

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        body = LeadStatusUpdate(status="qualificado")

        with pytest.raises(HTTPException) as exc:
            await atualizar_status(lead_id=999, body=body, escritorio_id=1, db=db)

        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# 6. Deduplicação — mesmo CNPJ atualiza, não duplica
# ---------------------------------------------------------------------------


class TestDeduplicacao:
    @pytest.mark.asyncio
    async def test_mesmo_cnpj_atualiza_lead_existente(self):
        from feature_1_ia_personalizada.api.routes.prospeccao import _salvar_lead

        lead_existente = _make_lead_mock(score=50)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=lead_existente)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        intel = _empresa_intel(cnpj="11222333000181")
        resultado = _resultado(score=85)

        await _salvar_lead(
            escritorio_id=1,
            litigante=_litigante_pj(),
            inteligencia=intel,
            resultado=resultado,
            tipo_lead="empresa",
            fonte="Reclamação Trabalhista",
            db=db,
        )

        # Deve atualizar o score existente, não criar novo
        assert lead_existente.score_match == 85
        db.commit.assert_called_once()
        db.add.assert_not_called()  # não chama add para update

    @pytest.mark.asyncio
    async def test_sem_cnpj_existente_cria_novo_lead(self):
        from feature_1_ia_personalizada.api.routes.prospeccao import _salvar_lead

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)  # sem lead existente
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()
        db.add = MagicMock()

        novo_lead = _make_lead_mock(score=75)

        async def _refresh(obj):
            obj.id = 1
            obj.created_at = novo_lead.created_at
            obj.criado_em = novo_lead.created_at

        db.refresh = AsyncMock(side_effect=_refresh)

        intel = _empresa_intel(cnpj="99888777000166")
        resultado = _resultado(score=75)
        litigante = LitiganteEncontrado(
            nome="NOVA EMPRESA LTDA",
            tipo="pessoa_juridica",
            polo="passivo",
            processos_count=3,
            numero_cnj_exemplo="0005678-12.2024.5.02.0100",
            tipo_acao="Reclamação Trabalhista",
            tribunal="TRT2",
            sem_advogado=False,
        )

        await _salvar_lead(
            escritorio_id=1,
            litigante=litigante,
            inteligencia=intel,
            resultado=resultado,
            tipo_lead="empresa",
            fonte="Reclamação Trabalhista",
            db=db,
        )

        db.add.assert_called_once()
        db.commit.assert_called_once()
