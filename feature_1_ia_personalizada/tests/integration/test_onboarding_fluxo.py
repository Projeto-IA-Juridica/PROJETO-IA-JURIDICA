"""
Testes de integração — Feature 4: Fluxo completo de onboarding
Critério de aceite (TASKS.md 4.6):
    - Fluxo completo das 5 etapas
    - go-live ativa monitoramento
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_escritorio(etapa: int = 0) -> MagicMock:
    e = MagicMock()
    e.id = 1
    e.nome = "Escritório Teste"
    e.cnpj = "11222333000181"
    e.email = "admin@teste.com"
    e.oab_responsavel = "SP123456"
    e.nome_responsavel = "Dr. Teste"
    e.plano = "basico"
    e.ativo = True
    e.max_processos = 100
    e.max_clientes = 200
    e.webhook_whatsapp_instance = None
    e.persona_nome = "Assistente Jurídico"
    e.persona_tom = "formal"
    e.horario_inicio = None
    e.horario_fim = None
    e.onboarding_etapa = etapa
    e.onboarding_completo = False
    e.onboarding_at = None
    from datetime import datetime
    e.created_at = datetime(2026, 3, 19)
    e.updated_at = datetime(2026, 3, 19)
    return e


def _make_request_state(role: str = "admin", escritorio_id: int = 1) -> MagicMock:
    req = MagicMock()
    req.state.user_payload = {"role": role, "escritorio_id": escritorio_id, "sub": "10"}
    return req


# ---------------------------------------------------------------------------
# Etapa 1 — configure-ia
# ---------------------------------------------------------------------------


class TestConfigureIA:
    @pytest.mark.asyncio
    async def test_salva_persona_e_avanca_etapa(self):
        """configure-ia deve salvar persona e avançar onboarding_etapa para 1."""
        from feature_1_ia_personalizada.api.routes.onboarding import (
            configure_ia,
            ConfigurarIARequest,
        )

        escritorio = _make_escritorio(etapa=0)
        db = AsyncMock()
        db.get = AsyncMock(return_value=escritorio)
        db.commit = AsyncMock()

        body = ConfigurarIARequest(
            persona_nome="Dra. Ana",
            persona_tom="amigavel",
            horario_inicio="09:00",
            horario_fim="17:00",
        )
        request = _make_request_state()

        resultado = await configure_ia(body=body, request=request, db=db)

        assert escritorio.persona_nome == "Dra. Ana"
        assert escritorio.persona_tom == "amigavel"
        assert escritorio.onboarding_etapa == 1
        assert "preview" in resultado
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_horario_inicio_maior_que_fim_retorna_400(self):
        """horario_inicio >= horario_fim deve retornar 400."""
        from fastapi import HTTPException
        from feature_1_ia_personalizada.api.routes.onboarding import (
            configure_ia,
            ConfigurarIARequest,
        )

        escritorio = _make_escritorio()
        db = AsyncMock()
        db.get = AsyncMock(return_value=escritorio)

        body = ConfigurarIARequest(
            persona_nome="Assistente",
            persona_tom="neutro",
            horario_inicio="18:00",
            horario_fim="08:00",  # fim < início
        )
        request = _make_request_state()

        with pytest.raises(HTTPException) as exc_info:
            await configure_ia(body=body, request=request, db=db)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_tom_invalido_rejeitado(self):
        """Tom inválido na Pydantic deve falhar antes de chegar ao endpoint."""
        from pydantic import ValidationError
        from feature_1_ia_personalizada.api.routes.onboarding import ConfigurarIARequest

        with pytest.raises(ValidationError):
            ConfigurarIARequest(
                persona_nome="Assistente",
                persona_tom="super_formal",  # inválido
                horario_inicio="08:00",
                horario_fim="18:00",
            )


# ---------------------------------------------------------------------------
# Etapa 3 — connect-whatsapp (polling)
# ---------------------------------------------------------------------------


class TestWhatsappStatus:
    @pytest.mark.asyncio
    async def test_retorna_not_configured_sem_instancia(self):
        """Sem instância configurada deve retornar connected=False."""
        from feature_1_ia_personalizada.api.routes.onboarding import whatsapp_status

        escritorio = _make_escritorio()
        escritorio.webhook_whatsapp_instance = None

        db = AsyncMock()
        db.get = AsyncMock(return_value=escritorio)
        request = _make_request_state()

        resultado = await whatsapp_status(request=request, db=db)

        assert resultado["connected"] is False
        assert resultado["state"] == "not_configured"

    @pytest.mark.asyncio
    async def test_retorna_connected_quando_open(self):
        """Quando Evolution API retorna state='open', connected deve ser True."""
        from feature_1_ia_personalizada.api.routes.onboarding import whatsapp_status

        escritorio = _make_escritorio(etapa=3)
        escritorio.webhook_whatsapp_instance = "escritorio_1"

        db = AsyncMock()
        db.get = AsyncMock(return_value=escritorio)
        db.commit = AsyncMock()
        request = _make_request_state()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={"instance": {"state": "open"}})

        with patch("feature_1_ia_personalizada.api.routes.onboarding.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(get=AsyncMock(return_value=mock_resp))
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            resultado = await whatsapp_status(request=request, db=db)

        assert resultado["connected"] is True
        assert resultado["state"] == "open"


# ---------------------------------------------------------------------------
# Etapa 5 — go-live ativa monitoramento
# ---------------------------------------------------------------------------


class TestGoLive:
    @pytest.mark.asyncio
    async def test_go_live_ativa_monitoramento_de_processos(self):
        """go-live deve setar monitoramento_ativo=True em todos os processos."""
        from feature_1_ia_personalizada.api.routes.onboarding import go_live

        escritorio = _make_escritorio(etapa=4)
        escritorio.onboarding_completo = False

        # 3 processos, 2 sem monitoramento
        processos = []
        for i in range(3):
            p = MagicMock()
            p.monitoramento_ativo = i == 0  # só o primeiro já ativo
            p.tipo_acao = "indenizatoria" if i < 2 else None
            processos.append(p)

        db = AsyncMock()
        db.get = AsyncMock(return_value=escritorio)
        db.commit = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=processos)))
        db.execute = AsyncMock(return_value=mock_result)

        request = _make_request_state()

        with patch(
            "feature_1_ia_personalizada.api.routes.onboarding.ingest_jurisprudencia_publica",
            create=True,
        ):
            resultado = await go_live(request=request, db=db)

        # Verifica que processos inativos foram ativados
        assert processos[1].monitoramento_ativo is True
        assert processos[2].monitoramento_ativo is True
        assert resultado["processos_ativados"] == 2

        # Verifica que onboarding foi concluído
        assert escritorio.onboarding_completo is True
        assert escritorio.onboarding_etapa == 5
        assert escritorio.onboarding_at is not None
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_go_live_retorna_mensagem_operacional(self):
        """go-live deve retornar mensagem de sucesso."""
        from feature_1_ia_personalizada.api.routes.onboarding import go_live

        escritorio = _make_escritorio(etapa=4)
        escritorio.onboarding_completo = False

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

        db = AsyncMock()
        db.get = AsyncMock(return_value=escritorio)
        db.commit = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        request = _make_request_state()

        resultado = await go_live(request=request, db=db)

        assert resultado["onboarding_completo"] is True
        assert "operacional" in resultado["mensagem"].lower()

    @pytest.mark.asyncio
    async def test_nao_admin_retorna_403(self):
        """Usuário não-admin tentando go-live deve receber 403."""
        from fastapi import HTTPException
        from feature_1_ia_personalizada.api.routes.onboarding import go_live

        db = AsyncMock()
        request = _make_request_state(role="advogado")

        with pytest.raises(HTTPException) as exc_info:
            await go_live(request=request, db=db)

        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# GET /onboarding/status — checklist
# ---------------------------------------------------------------------------


class TestOnboardingStatus:
    @pytest.mark.asyncio
    async def test_retorna_checklist_correto(self):
        """GET /status deve retornar percentual e lista de etapas."""
        from feature_1_ia_personalizada.api.routes.onboarding import onboarding_status

        escritorio = _make_escritorio(etapa=3)
        db = AsyncMock()
        db.get = AsyncMock(return_value=escritorio)
        request = _make_request_state()

        resultado = await onboarding_status(request=request, db=db)

        assert resultado["etapa_atual"] == 3
        assert resultado["percentual_completo"] == 60  # 3/5 = 60%
        assert len(resultado["etapas"]) == 6  # etapas 0 a 5
        # Etapas 0-3 concluídas
        for i in range(4):
            assert resultado["etapas"][i]["concluida"] is True
        # Etapas 4-5 pendentes
        for i in range(4, 6):
            assert resultado["etapas"][i]["concluida"] is False
