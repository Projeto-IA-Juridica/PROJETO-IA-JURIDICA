"""
Testes unitários — Feature 4: Onboarding register
Critério de aceite (TASKS.md 4.6):
    - Validação de CNPJ
    - Duplicata retorna 409
    - Usuário admin criado com role correto
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_VALID_REGISTER_PAYLOAD = {
    "nome_escritorio": "Escritório Silva Advocacia",
    "cnpj": "11.222.333/0001-81",  # CNPJ válido
    "email_admin": "admin@silva.adv.br",
    "senha": "Senha@2026",
    "nome_responsavel": "Dr. João Silva",
    "oab_responsavel": "SP123456",
}


# ---------------------------------------------------------------------------
# Testes de validação de CNPJ
# ---------------------------------------------------------------------------


class TestCNPJValidation:
    def test_cnpj_invalido_rejeitado(self):
        """CNPJ com dígitos verificadores errados deve falhar na validação Pydantic."""
        from pydantic import ValidationError

        from feature_1_ia_personalizada.api.routes.onboarding import RegisterRequest

        payload = {**_VALID_REGISTER_PAYLOAD, "cnpj": "00.000.000/0000-00"}
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(**payload)

        errors = exc_info.value.errors()
        assert any("cnpj" in str(e["loc"]).lower() or "CNPJ" in str(e.get("msg", "")) for e in errors)

    def test_cnpj_formato_sem_pontuacao_aceito(self):
        """CNPJ sem pontuação deve ser normalizado e aceito."""
        from feature_1_ia_personalizada.api.routes.onboarding import RegisterRequest

        payload = {**_VALID_REGISTER_PAYLOAD, "cnpj": "11222333000181"}
        req = RegisterRequest(**payload)
        assert req.cnpj == "11222333000181"  # normalizado (só dígitos)

    def test_cnpj_com_pontuacao_aceito(self):
        """CNPJ com pontuação deve ser normalizado e aceito."""
        from feature_1_ia_personalizada.api.routes.onboarding import RegisterRequest

        req = RegisterRequest(**_VALID_REGISTER_PAYLOAD)
        assert len(req.cnpj) == 14  # normalizado para 14 dígitos

    def test_oab_invalida_rejeitada(self):
        """OAB fora do formato UFNNNNN deve falhar."""
        from pydantic import ValidationError

        from feature_1_ia_personalizada.api.routes.onboarding import RegisterRequest

        payload = {**_VALID_REGISTER_PAYLOAD, "oab_responsavel": "123456"}
        with pytest.raises(ValidationError):
            RegisterRequest(**payload)

    def test_senha_curta_rejeitada(self):
        """Senha com menos de 8 caracteres deve falhar."""
        from pydantic import ValidationError

        from feature_1_ia_personalizada.api.routes.onboarding import RegisterRequest

        payload = {**_VALID_REGISTER_PAYLOAD, "senha": "abc"}
        with pytest.raises(ValidationError):
            RegisterRequest(**payload)


# ---------------------------------------------------------------------------
# Testes de endpoint (mock do banco)
# ---------------------------------------------------------------------------


class TestRegisterEndpoint:
    @pytest.mark.asyncio
    async def test_register_cria_escritorio_e_admin(self):
        """POST /onboarding/register cria escritório + admin e retorna JWT."""
        from datetime import datetime

        from sqlalchemy.ext.asyncio import AsyncSession

        from feature_1_ia_personalizada.api.routes.onboarding import RegisterRequest, register
        from shared.models.escritorio import Escritorio as EscritorioModel

        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))))
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        # Simula DB populando defaults após flush/commit
        _ids = iter([1, 10])
        async def _refresh(obj):
            obj.id = next(_ids)
            if isinstance(obj, EscritorioModel):
                obj.ativo = True
                obj.max_processos = 100
                obj.max_clientes = 200
                obj.created_at = datetime(2026, 3, 19)
                obj.updated_at = datetime(2026, 3, 19)
        db.refresh = AsyncMock(side_effect=_refresh)

        mock_usuario = MagicMock()
        mock_usuario.id = 10
        mock_usuario.escritorio_id = 1
        mock_usuario.role = "admin"

        with (
            patch("feature_1_ia_personalizada.api.routes.onboarding.hash_senha", return_value="hashed"),
            patch("feature_1_ia_personalizada.api.routes.onboarding.criar_token", return_value="access_token_mock"),
            patch("feature_1_ia_personalizada.api.routes.onboarding.criar_refresh_token", return_value="refresh_token_mock"),
            patch("feature_1_ia_personalizada.api.routes.onboarding.Usuario", return_value=mock_usuario),
        ):
            body = RegisterRequest(**_VALID_REGISTER_PAYLOAD)
            response = await register(body=body, db=db)

        assert response.access_token == "access_token_mock"
        assert response.refresh_token == "refresh_token_mock"

    @pytest.mark.asyncio
    async def test_register_cnpj_duplicado_retorna_409(self):
        """Segundo cadastro com mesmo CNPJ deve retornar 409 Conflict."""
        from fastapi import HTTPException
        from sqlalchemy.ext.asyncio import AsyncSession

        from feature_1_ia_personalizada.api.routes.onboarding import RegisterRequest, register

        db = AsyncMock(spec=AsyncSession)

        # Simula escritório já existente
        mock_existente = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=mock_existente))
                )
            )
        )

        body = RegisterRequest(**_VALID_REGISTER_PAYLOAD)
        with pytest.raises(HTTPException) as exc_info:
            await register(body=body, db=db)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "CNPJ" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_usuario_admin_criado_com_role_correto(self):
        """Usuário criado no register deve ter role='admin'."""
        from datetime import datetime

        from sqlalchemy.ext.asyncio import AsyncSession

        from feature_1_ia_personalizada.api.routes.onboarding import RegisterRequest, register
        from shared.models.escritorio import Escritorio as EscritorioModel

        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
            )
        )
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        _counter = [0]
        async def _refresh(obj):
            _counter[0] += 1
            obj.id = _counter[0]
            if isinstance(obj, EscritorioModel):
                obj.ativo = True
                obj.max_processos = 100
                obj.max_clientes = 200
                obj.created_at = datetime(2026, 3, 19)
                obj.updated_at = datetime(2026, 3, 19)
        db.refresh = AsyncMock(side_effect=_refresh)

        usuarios_criados = []

        class _CapturadorUsuario:
            def __init__(self, **kwargs):
                usuarios_criados.append(kwargs)
                for k, v in kwargs.items():
                    setattr(self, k, v)

        with (
            patch("feature_1_ia_personalizada.api.routes.onboarding.Usuario", side_effect=_CapturadorUsuario),
            patch("feature_1_ia_personalizada.api.routes.onboarding.hash_senha", return_value="hashed"),
            patch("feature_1_ia_personalizada.api.routes.onboarding.criar_token", return_value="tok"),
            patch("feature_1_ia_personalizada.api.routes.onboarding.criar_refresh_token", return_value="ref"),
        ):
            body = RegisterRequest(**_VALID_REGISTER_PAYLOAD)
            await register(body=body, db=db)

        assert len(usuarios_criados) == 1
        assert usuarios_criados[0]["role"] == "admin"
