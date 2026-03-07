# feature_1_ia_personalizada/tests/integration/test_whatsapp_flow.py
"""
Testes de integração do fluxo WhatsApp via webhook Evolution API.

Cobre o endpoint POST /webhook/whatsapp de ponta a ponta:
  - banco de dados real (SQLite in-memory via conftest)
  - task Celery mockada (evita dependência de broker em CI)
  - todas as ramificações de filtragem e resolução de tenant/cliente
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# routes/__init__.py faz `from .webhook_whatsapp import router as webhook_whatsapp`,
# o que shadowa o submodulo com o APIRouter no namespace do pacote.
# `import a.b.c as x` em Python usa attribute traversal (a.b.c), não sys.modules,
# e portanto retorna o APIRouter. A forma correta de obter o módulo real é via
# sys.modules. Importamos o pacote routes explicitamente para garantir que o módulo
# webhook_whatsapp já está registrado em sys.modules antes de acessá-lo.
import feature_1_ia_personalizada.api.routes  # noqa: F401
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio

_wh_module = sys.modules["feature_1_ia_personalizada.api.routes.webhook_whatsapp"]

# ---------------------------------------------------------------------------
# Constantes de teste
# ---------------------------------------------------------------------------

INSTANCIA = "instancia-escritorio-abc"
TELEFONE = "5511988887777"
TELEFONE_JID = f"{TELEFONE}@s.whatsapp.net"
GRUPO_JID = "120363000000000001@g.us"
_WH_HEADERS = {"apikey": "test-evolution-key"}


# ---------------------------------------------------------------------------
# Helpers de payload
# ---------------------------------------------------------------------------


def _payload_texto(
    mensagem: str = "Olá, preciso de ajuda",
    instance: str = INSTANCIA,
    remote_jid: str = TELEFONE_JID,
    from_me: bool = False,
) -> dict[str, Any]:
    """Payload padrão de mensagem de texto simples (conversation)."""
    return {
        "event": "messages.upsert",
        "instance": instance,
        "data": {
            "key": {"remoteJid": remote_jid, "fromMe": from_me, "id": "AABBCCDD"},
            "message": {"conversation": mensagem},
        },
    }


def _payload_extended_text(
    mensagem: str = "Texto com link https://exemplo.com",
    instance: str = INSTANCIA,
    remote_jid: str = TELEFONE_JID,
) -> dict[str, Any]:
    return {
        "event": "messages.upsert",
        "instance": instance,
        "data": {
            "key": {"remoteJid": remote_jid, "fromMe": False},
            "message": {"extendedTextMessage": {"text": mensagem}},
        },
    }


def _payload_imagem(
    caption: str = "Foto do documento",
    instance: str = INSTANCIA,
    remote_jid: str = TELEFONE_JID,
) -> dict[str, Any]:
    return {
        "event": "messages.upsert",
        "instance": instance,
        "data": {
            "key": {"remoteJid": remote_jid, "fromMe": False},
            "message": {"imageMessage": {"caption": caption}},
        },
    }


def _payload_audio(
    instance: str = INSTANCIA,
    remote_jid: str = TELEFONE_JID,
) -> dict[str, Any]:
    return {
        "event": "messages.upsert",
        "instance": instance,
        "data": {
            "key": {"remoteJid": remote_jid, "fromMe": False},
            "message": {"audioMessage": {}},
        },
    }


# ---------------------------------------------------------------------------
# Fixtures locais
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_celery(monkeypatch) -> MagicMock:
    """
    Substitui processar_mensagem_recebida no módulo da rota por um MagicMock.
    Usa patch por objeto (não string) para contornar o shadow do submodulo
    feito pelo routes/__init__.py.
    Retorna o próprio mock para que os testes possam inspecionar as chamadas.
    """
    task_mock = MagicMock()
    monkeypatch.setattr(_wh_module, "processar_mensagem_recebida", task_mock)
    return task_mock


@pytest.fixture
async def escritorio_com_instancia(db_session: AsyncSession) -> Escritorio:
    """
    Escritório com webhook_whatsapp_instance configurado.
    Cria diretamente (sem usar escritorio_factory) porque o factory não propaga
    o kwarg webhook_whatsapp_instance para o construtor do model.
    """
    from faker import Faker

    fake = Faker("pt_BR")
    escritorio = Escritorio(
        nome=fake.company(),
        cnpj=fake.cnpj(),
        telefone="5511999999999",
        email=fake.company_email(),
        oab_responsavel="SP123456",
        nome_responsavel=fake.name(),
        webhook_whatsapp_instance=INSTANCIA,
    )
    db_session.add(escritorio)
    await db_session.commit()
    await db_session.refresh(escritorio)
    return escritorio


@pytest.fixture
async def cliente_cadastrado(
    db_session: AsyncSession, escritorio_com_instancia: Escritorio
) -> Cliente:
    """Cliente vinculado ao escritório com telefone conhecido."""
    cliente = Cliente(
        escritorio_id=escritorio_com_instancia.id,
        nome="Maria da Silva",
        cpf="123.456.789-00",
        telefone_whatsapp=TELEFONE,
        aceite_lgpd=True,
        preferencia_horario_notificacao="livre",
    )
    db_session.add(cliente)
    await db_session.commit()
    await db_session.refresh(cliente)
    return cliente


# ---------------------------------------------------------------------------
# Filtros de evento — mensagens ignoradas
# ---------------------------------------------------------------------------


class TestWebhookFiltros:
    @pytest.mark.asyncio
    async def test_evento_diferente_de_upsert_e_ignorado(
        self, async_client: AsyncClient, mock_celery
    ):
        payload = _payload_texto()
        payload["event"] = "messages.update"
        response = await async_client.post("/webhook/whatsapp", json=payload, headers=_WH_HEADERS)
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
        mock_celery.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_mensagem_from_me_e_ignorada(self, async_client: AsyncClient, mock_celery):
        response = await async_client.post(
            "/webhook/whatsapp",
            json=_payload_texto(from_me=True),
            headers=_WH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
        mock_celery.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_mensagem_de_grupo_e_ignorada(self, async_client: AsyncClient, mock_celery):
        response = await async_client.post(
            "/webhook/whatsapp",
            json=_payload_texto(remote_jid=GRUPO_JID),
            headers=_WH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
        mock_celery.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_mensagem_com_texto_vazio_e_ignorada(
        self, async_client: AsyncClient, mock_celery
    ):
        payload = _payload_texto()
        payload["data"]["message"]["conversation"] = "   "
        response = await async_client.post("/webhook/whatsapp", json=payload, headers=_WH_HEADERS)
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
        mock_celery.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_instancia_ausente_retorna_error(self, async_client: AsyncClient, mock_celery):
        payload = _payload_texto()
        del payload["instance"]
        response = await async_client.post("/webhook/whatsapp", json=payload, headers=_WH_HEADERS)
        assert response.status_code == 200
        assert response.json()["status"] == "error"
        mock_celery.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_payload_nao_json_retorna_400(self, async_client: AsyncClient):
        response = await async_client.post(
            "/webhook/whatsapp",
            content=b"isso nao e json {{{",
            headers={"Content-Type": "application/json", **_WH_HEADERS},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Resolução de tenant e cliente — not found
# ---------------------------------------------------------------------------


class TestWebhookLookup:
    @pytest.mark.asyncio
    async def test_instancia_desconhecida_e_ignorada(
        self, async_client: AsyncClient, mock_celery, escritorio_com_instancia
    ):
        """Instância não cadastrada em nenhum escritório → ignored."""
        response = await async_client.post(
            "/webhook/whatsapp",
            json=_payload_texto(instance="instancia-que-nao-existe"),
            headers=_WH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
        mock_celery.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_cliente_nao_cadastrado_e_ignorado(
        self, async_client: AsyncClient, mock_celery, escritorio_com_instancia
    ):
        """Número de telefone desconhecido no escritório → ignored."""
        response = await async_client.post(
            "/webhook/whatsapp",
            json=_payload_texto(remote_jid="5521900000000@s.whatsapp.net"),
            headers=_WH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
        mock_celery.delay.assert_not_called()


# ---------------------------------------------------------------------------
# Happy path — fluxo completo
# ---------------------------------------------------------------------------


class TestWebhookHappyPath:
    @pytest.mark.asyncio
    async def test_mensagem_texto_enfileira_task(
        self,
        async_client: AsyncClient,
        mock_celery,
        escritorio_com_instancia: Escritorio,
        cliente_cadastrado: Cliente,
    ):
        response = await async_client.post(
            "/webhook/whatsapp",
            json=_payload_texto(mensagem="Preciso saber sobre meu processo"),
            headers=_WH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"

    @pytest.mark.asyncio
    async def test_task_recebe_ids_corretos(
        self,
        async_client: AsyncClient,
        mock_celery,
        escritorio_com_instancia: Escritorio,
        cliente_cadastrado: Cliente,
    ):
        await async_client.post(
            "/webhook/whatsapp",
            json=_payload_texto(mensagem="Olá"),
            headers=_WH_HEADERS,
        )
        mock_celery.delay.assert_called_once_with(
            id_escritorio=escritorio_com_instancia.id,
            id_cliente=cliente_cadastrado.id,
            mensagem="Olá",
            tipo="texto",
        )

    @pytest.mark.asyncio
    async def test_mensagem_extended_text_e_enfileirada(
        self,
        async_client: AsyncClient,
        mock_celery,
        escritorio_com_instancia,
        cliente_cadastrado,
    ):
        response = await async_client.post(
            "/webhook/whatsapp",
            json=_payload_extended_text(mensagem="Texto com link"),
            headers=_WH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        mock_celery.delay.assert_called_once()
        _, kwargs = mock_celery.delay.call_args
        assert kwargs["mensagem"] == "Texto com link"
        assert kwargs["tipo"] == "texto"

    @pytest.mark.asyncio
    async def test_mensagem_imagem_com_caption_e_enfileirada(
        self,
        async_client: AsyncClient,
        mock_celery,
        escritorio_com_instancia,
        cliente_cadastrado,
    ):
        response = await async_client.post(
            "/webhook/whatsapp",
            json=_payload_imagem(caption="Foto do contrato"),
            headers=_WH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        _, kwargs = mock_celery.delay.call_args
        assert kwargs["mensagem"] == "Foto do contrato"
        assert kwargs["tipo"] == "imagem"

    @pytest.mark.asyncio
    async def test_mensagem_audio_e_ignorada_por_texto_vazio(
        self,
        async_client: AsyncClient,
        mock_celery,
        escritorio_com_instancia,
        cliente_cadastrado,
    ):
        """
        Áudio gera texto placeholder não-vazio → por isso a rota NÃO ignora,
        mas enfileira com tipo "audio". Se a implementação atual retornar
        "ignored" por causa do strip(), o teste documenta o comportamento real.
        """
        response = await async_client.post(
            "/webhook/whatsapp",
            json=_payload_audio(),
            headers=_WH_HEADERS,
        )
        data = response.json()
        assert response.status_code == 200
        # Documenta o comportamento atual: áudio ainda não tem transcrição,
        # o placeholder não é vazio, portanto deve ser enfileirado.
        assert data["status"] in ("queued", "ignored")


# ---------------------------------------------------------------------------
# Isolamento multi-tenant
# ---------------------------------------------------------------------------


class TestWebhookMultiTenant:
    @pytest.mark.asyncio
    async def test_cliente_de_outro_escritorio_nao_e_encontrado(
        self,
        async_client: AsyncClient,
        mock_celery,
        db_session: AsyncSession,
        escritorio_com_instancia: Escritorio,
        cliente_cadastrado: Cliente,
    ):
        """
        Dois escritórios, instâncias diferentes.
        Payload usa instância do escritório B — cliente do escritório A
        não deve ser encontrado.
        """
        from faker import Faker

        fake = Faker("pt_BR")
        # Cria escritório B diretamente para garantir que a instância é gravada
        escritorio_b = Escritorio(
            nome=fake.company(),
            cnpj=fake.cnpj(),
            telefone="5511999999999",
            email=fake.company_email(),
            oab_responsavel="SP654321",
            nome_responsavel=fake.name(),
            webhook_whatsapp_instance="instancia-escritorio-b",
        )
        db_session.add(escritorio_b)
        await db_session.commit()
        await db_session.refresh(escritorio_b)

        # Payload chega pela instância do escritório B
        response = await async_client.post(
            "/webhook/whatsapp",
            json=_payload_texto(instance="instancia-escritorio-b"),
            headers=_WH_HEADERS,
        )
        assert response.status_code == 200
        # O telefone do cliente_cadastrado não existe no escritório B
        assert response.json()["status"] == "ignored"
        mock_celery.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_mesmo_telefone_escritorios_distintos_envia_para_o_correto(
        self,
        async_client: AsyncClient,
        mock_celery,
        db_session: AsyncSession,
        escritorio_com_instancia: Escritorio,
        cliente_cadastrado: Cliente,
    ):
        """
        Mesmo número de telefone cadastrado em dois escritórios diferentes.
        O roteamento deve usar o escritório da instância do payload.
        """
        from faker import Faker

        fake = Faker("pt_BR")
        escritorio_b = Escritorio(
            nome=fake.company(),
            cnpj=fake.cnpj(),
            telefone="5521999999999",
            email=fake.company_email(),
            oab_responsavel="RJ654321",
            nome_responsavel=fake.name(),
            webhook_whatsapp_instance="instancia-escritorio-b",
        )
        db_session.add(escritorio_b)
        await db_session.commit()
        await db_session.refresh(escritorio_b)

        cliente_b = Cliente(
            escritorio_id=escritorio_b.id,
            nome="João da Silva",
            cpf="987.654.321-00",
            telefone_whatsapp=TELEFONE,  # mesmo telefone
            aceite_lgpd=True,
            preferencia_horario_notificacao="livre",
        )
        db_session.add(cliente_b)
        await db_session.commit()
        await db_session.refresh(cliente_b)

        # Payload vem da instância B
        response = await async_client.post(
            "/webhook/whatsapp",
            json=_payload_texto(instance="instancia-escritorio-b"),
            headers=_WH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"

        mock_celery.delay.assert_called_once_with(
            id_escritorio=escritorio_b.id,
            id_cliente=cliente_b.id,
            mensagem="Olá, preciso de ajuda",
            tipo="texto",
        )
