# feature_1_ia_personalizada/tests/unit/test_whatsapp_service.py
"""
Testes do WhatsAppService: janela comercial, rate limit, envio normal,
agendamento, erros da Evolution API e mensagens prontas.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Helper para monkeypatch de datetime.now — o código de produção faz
# `from datetime import datetime`, então o patch deve ser aplicado no
# namespace do módulo alvo: whatsapp.datetime
# ---------------------------------------------------------------------------


class _Datetime22h:
    """Simula datetime.now() retornando 22h (fora do horário comercial)."""

    @staticmethod
    def now() -> datetime:
        return datetime(2024, 6, 10, 22, 0)


_PATCH_TARGET = "feature_1_ia_personalizada.services.messaging.whatsapp.datetime"

from feature_1_ia_personalizada.services.messaging.evolution_client import (
    EvolutionError,
    EvolutionOfflineError,
)
from feature_1_ia_personalizada.services.messaging.whatsapp import (
    JanelaComercial,
    WhatsAppService,
)

# ---------------------------------------------------------------------------
# Fakes — EvolutionClient
# ---------------------------------------------------------------------------


class _FakeEvolutionClient:
    """Simula envio bem-sucedido via Evolution API."""

    def __init__(self) -> None:
        self.chamadas_texto: list[dict] = []
        self.chamadas_botoes: list[dict] = []
        self._resposta_texto: dict[str, Any] = {"key": {"id": "fake-msg-id"}}
        self._resposta_botoes: dict[str, Any] = {"key": {"id": "fake-btn-id"}}

    async def enviar_texto(
        self, instance: str, numero: str, texto: str
    ) -> dict[str, Any]:
        self.chamadas_texto.append(
            {"instance": instance, "numero": numero, "texto": texto}
        )
        return self._resposta_texto

    async def enviar_botoes(
        self,
        instance: str,
        numero: str,
        texto: str,
        botoes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.chamadas_botoes.append(
            {"instance": instance, "numero": numero, "texto": texto, "botoes": botoes}
        )
        return self._resposta_botoes


class _FakeEvolutionClientOffline(_FakeEvolutionClient):
    """Simula instância offline (EvolutionOfflineError)."""

    async def enviar_texto(
        self, instance: str, numero: str, texto: str
    ) -> dict[str, Any]:
        raise EvolutionOfflineError("Instância offline")

    async def enviar_botoes(
        self, instance: str, numero: str, texto: str, botoes: list
    ) -> dict[str, Any]:
        raise EvolutionOfflineError("Instância offline")


class _FakeEvolutionClientError(_FakeEvolutionClient):
    """Simula erro genérico da Evolution API (EvolutionError)."""

    async def enviar_texto(
        self, instance: str, numero: str, texto: str
    ) -> dict[str, Any]:
        raise EvolutionError("Erro genérico Evolution")

    async def enviar_botoes(
        self, instance: str, numero: str, texto: str, botoes: list
    ) -> dict[str, Any]:
        raise EvolutionError("Erro genérico Evolution")


# ---------------------------------------------------------------------------
# Fakes — RepositorioWhatsApp
# ---------------------------------------------------------------------------


class _FakeRepositorio:
    """
    Implementação em memória do RepositorioWhatsApp.

    Parâmetros configuráveis por teste:
    - instancia: nome da instância a retornar para qualquer escritorio_id
    - numero: número retornado para qualquer cliente_id
    - preferencia: "livre" ou "comercial"
    - mensagens_enviadas_hoje: qtd já enviada (para rate limit)
    """

    def __init__(
        self,
        instancia: str = "instancia-test",
        numero: str = "5511999990001",
        preferencia: str = "livre",
        mensagens_enviadas_hoje: int = 0,
    ) -> None:
        self._instancia = instancia
        self._numero = numero
        self._preferencia = preferencia
        self._mensagens_enviadas_hoje = mensagens_enviadas_hoje

        # Capturas para asserções
        self.interacoes_salvas: list[dict] = []
        self.agendamentos: list[dict] = []

    async def obter_instancia_por_escritorio(self, escritorio_id: int) -> str:
        return self._instancia

    async def obter_numero_cliente(self, cliente_id: int) -> str:
        return self._numero

    async def obter_preferencia_horario_notificacao(self, cliente_id: int) -> str:
        return self._preferencia

    async def contar_mensagens_enviadas_hoje(self, cliente_id: int) -> int:
        return self._mensagens_enviadas_hoje

    async def salvar_interacao(
        self,
        escritorio_id: int,
        cliente_id: int,
        texto: str,
        processo_id: int | None,
        status: str,
        payload_resposta: dict[str, Any] | None = None,
    ) -> None:
        self.interacoes_salvas.append(
            {
                "escritorio_id": escritorio_id,
                "cliente_id": cliente_id,
                "texto": texto,
                "processo_id": processo_id,
                "status": status,
                "payload_resposta": payload_resposta,
            }
        )

    async def agendar_envio_mensagem(
        self,
        escritorio_id: int,
        cliente_id: int,
        texto: str,
        processo_id: int | None,
        enviar_em: datetime,
        motivo: str,
    ) -> None:
        self.agendamentos.append(
            {
                "escritorio_id": escritorio_id,
                "cliente_id": cliente_id,
                "texto": texto,
                "processo_id": processo_id,
                "enviar_em": enviar_em,
                "motivo": motivo,
            }
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def evolution() -> _FakeEvolutionClient:
    return _FakeEvolutionClient()


@pytest.fixture
def repo() -> _FakeRepositorio:
    return _FakeRepositorio()


def _service(
    evolution=None,
    repo=None,
    preferencia: str = "livre",
    mensagens_hoje: int = 0,
    janela: JanelaComercial = JanelaComercial(),
) -> tuple[WhatsAppService, _FakeEvolutionClient, _FakeRepositorio]:
    ev = evolution or _FakeEvolutionClient()
    rp = repo or _FakeRepositorio(
        preferencia=preferencia, mensagens_enviadas_hoje=mensagens_hoje
    )
    svc = WhatsAppService(ev, rp, janela)
    return svc, ev, rp


# ---------------------------------------------------------------------------
# Dados de teste
# ---------------------------------------------------------------------------

ESCRITORIO_ID = 1
CLIENTE_ID = 42
TEXTO = "Olá, temos novidades sobre seu processo."
PROCESSO_ID = 99


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------


class TestConstantes:
    def test_limite_mensagens_dia(self):
        assert WhatsAppService.LIMITE_MENSAGENS_DIA_POR_CLIENTE == 5

    def test_janela_comercial_padrao_inicio(self):
        assert JanelaComercial().inicio == time(8, 0)

    def test_janela_comercial_padrao_fim(self):
        assert JanelaComercial().fim == time(18, 0)


# ---------------------------------------------------------------------------
# Janela comercial — _esta_na_janela_comercial
# ---------------------------------------------------------------------------


class TestJanelaComercial:
    def _svc(self) -> WhatsAppService:
        svc, _, _ = _service()
        return svc

    def test_horario_comercial_dentro(self):
        svc = self._svc()
        assert svc._esta_na_janela_comercial(datetime(2024, 6, 10, 10, 30)) is True

    def test_exatamente_no_inicio(self):
        svc = self._svc()
        assert svc._esta_na_janela_comercial(datetime(2024, 6, 10, 8, 0, 0)) is True

    def test_exatamente_no_fim(self):
        svc = self._svc()
        assert svc._esta_na_janela_comercial(datetime(2024, 6, 10, 18, 0, 0)) is True

    def test_antes_do_horario_comercial(self):
        svc = self._svc()
        assert svc._esta_na_janela_comercial(datetime(2024, 6, 10, 7, 59)) is False

    def test_depois_do_horario_comercial(self):
        svc = self._svc()
        assert svc._esta_na_janela_comercial(datetime(2024, 6, 10, 18, 1)) is False

    def test_meia_noite_fora(self):
        svc = self._svc()
        assert svc._esta_na_janela_comercial(datetime(2024, 6, 10, 0, 0)) is False

    def test_janela_customizada(self):
        svc, _, _ = _service(janela=JanelaComercial(inicio=time(9, 0), fim=time(17, 0)))
        assert svc._esta_na_janela_comercial(datetime(2024, 6, 10, 8, 30)) is False
        assert svc._esta_na_janela_comercial(datetime(2024, 6, 10, 9, 0)) is True


# ---------------------------------------------------------------------------
# Próxima janela — _proxima_janela_comercial
# ---------------------------------------------------------------------------


class TestProximaJanela:
    def _svc(self) -> WhatsAppService:
        svc, _, _ = _service()
        return svc

    def test_antes_das_8h_agenda_mesmo_dia(self):
        svc = self._svc()
        agora = datetime(2024, 6, 10, 6, 30)
        prox = svc._proxima_janela_comercial(agora)
        assert prox == datetime(2024, 6, 10, 8, 0, 0, 0)

    def test_apos_horario_comercial_agenda_proximo_dia(self):
        svc = self._svc()
        agora = datetime(2024, 6, 10, 19, 0)
        prox = svc._proxima_janela_comercial(agora)
        assert prox == datetime(2024, 6, 11, 8, 0, 0, 0)

    def test_meia_noite_agenda_mesmo_dia_8h(self):
        svc = self._svc()
        agora = datetime(2024, 6, 10, 0, 0)
        prox = svc._proxima_janela_comercial(agora)
        assert prox == datetime(2024, 6, 10, 8, 0, 0, 0)

    def test_segundos_zerados_na_proxima_janela(self):
        svc = self._svc()
        agora = datetime(2024, 6, 10, 5, 45, 33)
        prox = svc._proxima_janela_comercial(agora)
        assert prox.second == 0
        assert prox.microsecond == 0


# ---------------------------------------------------------------------------
# Pode enviar agora — _pode_enviar_agora
# ---------------------------------------------------------------------------


class TestPodeEnviarAgora:
    async def test_livre_dentro_limite_pode_enviar(self):
        svc, _, _ = _service(preferencia="livre", mensagens_hoje=0)
        pode, motivo = await svc._pode_enviar_agora(
            CLIENTE_ID, datetime(2024, 6, 10, 9, 0)
        )
        assert pode is True
        assert motivo is None

    async def test_comercial_dentro_horario_e_limite_pode_enviar(self):
        svc, _, _ = _service(preferencia="comercial", mensagens_hoje=2)
        pode, motivo = await svc._pode_enviar_agora(
            CLIENTE_ID, datetime(2024, 6, 10, 9, 0)
        )
        assert pode is True
        assert motivo is None

    async def test_comercial_fora_horario_nao_pode(self):
        svc, _, _ = _service(preferencia="comercial", mensagens_hoje=0)
        pode, motivo = await svc._pode_enviar_agora(
            CLIENTE_ID, datetime(2024, 6, 10, 20, 0)
        )
        assert pode is False
        assert motivo == "fora_horario_comercial"

    async def test_livre_rate_limit_excedido_nao_pode(self):
        svc, _, _ = _service(preferencia="livre", mensagens_hoje=5)
        pode, motivo = await svc._pode_enviar_agora(
            CLIENTE_ID, datetime(2024, 6, 10, 9, 0)
        )
        assert pode is False
        assert motivo == "rate_limit_diario"

    async def test_comercial_fora_horario_e_rate_limit_retorna_horario_primeiro(self):
        # preferência "comercial" + fora do horário: horário é verificado antes do rate limit
        svc, _, _ = _service(preferencia="comercial", mensagens_hoje=5)
        pode, motivo = await svc._pode_enviar_agora(
            CLIENTE_ID, datetime(2024, 6, 10, 20, 0)
        )
        assert pode is False
        assert motivo == "fora_horario_comercial"

    async def test_no_limite_exato_nao_pode(self):
        svc, _, _ = _service(preferencia="livre", mensagens_hoje=5)
        pode, motivo = await svc._pode_enviar_agora(
            CLIENTE_ID, datetime(2024, 6, 10, 9, 0)
        )
        assert pode is False
        assert motivo == "rate_limit_diario"

    async def test_abaixo_do_limite_exato_pode(self):
        svc, _, _ = _service(preferencia="livre", mensagens_hoje=4)
        pode, motivo = await svc._pode_enviar_agora(
            CLIENTE_ID, datetime(2024, 6, 10, 9, 0)
        )
        assert pode is True


# ---------------------------------------------------------------------------
# enviar_mensagem — happy path
# ---------------------------------------------------------------------------


class TestEnviarMensagemHappyPath:
    async def test_retorna_ok_true_sem_agendamento(self):
        svc, ev, rp = _service(preferencia="livre", mensagens_hoje=0)
        resultado = await svc.enviar_mensagem(ESCRITORIO_ID, CLIENTE_ID, TEXTO)
        assert resultado["ok"] is True
        assert resultado["agendado"] is False

    async def test_chama_evolution_com_dados_corretos(self):
        svc, ev, rp = _service(preferencia="livre", mensagens_hoje=0)
        await svc.enviar_mensagem(ESCRITORIO_ID, CLIENTE_ID, TEXTO, PROCESSO_ID)
        assert len(ev.chamadas_texto) == 1
        chamada = ev.chamadas_texto[0]
        assert chamada["instance"] == rp._instancia
        assert chamada["numero"] == rp._numero
        assert chamada["texto"] == TEXTO

    async def test_salva_interacao_com_status_enviado(self):
        svc, ev, rp = _service(preferencia="livre", mensagens_hoje=0)
        await svc.enviar_mensagem(ESCRITORIO_ID, CLIENTE_ID, TEXTO, PROCESSO_ID)
        assert len(rp.interacoes_salvas) == 1
        interacao = rp.interacoes_salvas[0]
        assert interacao["status"] == "enviado"
        assert interacao["escritorio_id"] == ESCRITORIO_ID
        assert interacao["cliente_id"] == CLIENTE_ID
        assert interacao["texto"] == TEXTO
        assert interacao["processo_id"] == PROCESSO_ID

    async def test_resposta_evolution_incluida_no_retorno(self):
        ev = _FakeEvolutionClient()
        ev._resposta_texto = {"key": {"id": "msg-xyz-123"}}
        svc = WhatsAppService(ev, _FakeRepositorio())
        resultado = await svc.enviar_mensagem(ESCRITORIO_ID, CLIENTE_ID, TEXTO)
        assert resultado["resposta"] == {"key": {"id": "msg-xyz-123"}}

    async def test_processo_id_none_por_padrao(self):
        svc, ev, rp = _service(preferencia="livre", mensagens_hoje=0)
        await svc.enviar_mensagem(ESCRITORIO_ID, CLIENTE_ID, TEXTO)
        assert rp.interacoes_salvas[0]["processo_id"] is None


# ---------------------------------------------------------------------------
# enviar_mensagem — rate limit
# ---------------------------------------------------------------------------


class TestEnviarMensagemRateLimit:
    async def test_rate_limit_com_agendamento_ativado_agenda(self):
        svc, ev, rp = _service(preferencia="livre", mensagens_hoje=5)
        resultado = await svc.enviar_mensagem(
            ESCRITORIO_ID, CLIENTE_ID, TEXTO, permitir_agendamento=True
        )
        assert resultado["ok"] is True
        assert resultado["agendado"] is True
        assert resultado["motivo"] == "rate_limit_diario"
        assert len(rp.agendamentos) == 1

    async def test_rate_limit_com_agendamento_salva_interacao_agendado(self):
        svc, ev, rp = _service(preferencia="livre", mensagens_hoje=5)
        await svc.enviar_mensagem(
            ESCRITORIO_ID, CLIENTE_ID, TEXTO, permitir_agendamento=True
        )
        assert rp.interacoes_salvas[0]["status"] == "agendado:rate_limit_diario"

    async def test_rate_limit_sem_agendamento_bloqueia(self):
        svc, ev, rp = _service(preferencia="livre", mensagens_hoje=5)
        resultado = await svc.enviar_mensagem(
            ESCRITORIO_ID, CLIENTE_ID, TEXTO, permitir_agendamento=False
        )
        assert resultado["ok"] is False
        assert resultado["motivo"] == "rate_limit_diario"

    async def test_rate_limit_sem_agendamento_nao_agenda(self):
        svc, ev, rp = _service(preferencia="livre", mensagens_hoje=5)
        await svc.enviar_mensagem(
            ESCRITORIO_ID, CLIENTE_ID, TEXTO, permitir_agendamento=False
        )
        assert len(rp.agendamentos) == 0

    async def test_rate_limit_sem_agendamento_salva_interacao_bloqueado(self):
        svc, ev, rp = _service(preferencia="livre", mensagens_hoje=5)
        await svc.enviar_mensagem(
            ESCRITORIO_ID, CLIENTE_ID, TEXTO, permitir_agendamento=False
        )
        assert rp.interacoes_salvas[0]["status"] == "bloqueado:rate_limit_diario"

    async def test_rate_limit_nao_chama_evolution(self):
        svc, ev, rp = _service(preferencia="livre", mensagens_hoje=5)
        await svc.enviar_mensagem(ESCRITORIO_ID, CLIENTE_ID, TEXTO)
        assert len(ev.chamadas_texto) == 0


# ---------------------------------------------------------------------------
# enviar_mensagem — fora do horário comercial
# ---------------------------------------------------------------------------


class TestEnviarMensagemForaHorario:
    async def test_fora_horario_com_agendamento_agenda(self, monkeypatch):
        rp = _FakeRepositorio(preferencia="comercial", mensagens_enviadas_hoje=0)
        svc = WhatsAppService(_FakeEvolutionClient(), rp)
        monkeypatch.setattr(_PATCH_TARGET, _Datetime22h)
        resultado = await svc.enviar_mensagem(
            ESCRITORIO_ID, CLIENTE_ID, TEXTO, permitir_agendamento=True
        )
        assert resultado["ok"] is True
        assert resultado["agendado"] is True
        assert resultado["motivo"] == "fora_horario_comercial"

    async def test_fora_horario_sem_agendamento_bloqueia(self, monkeypatch):
        rp = _FakeRepositorio(preferencia="comercial", mensagens_enviadas_hoje=0)
        svc = WhatsAppService(_FakeEvolutionClient(), rp)
        monkeypatch.setattr(_PATCH_TARGET, _Datetime22h)
        resultado = await svc.enviar_mensagem(
            ESCRITORIO_ID, CLIENTE_ID, TEXTO, permitir_agendamento=False
        )
        assert resultado["ok"] is False
        assert resultado["motivo"] == "fora_horario_comercial"

    async def test_fora_horario_salva_interacao_bloqueado(self, monkeypatch):
        rp = _FakeRepositorio(preferencia="comercial", mensagens_enviadas_hoje=0)
        svc = WhatsAppService(_FakeEvolutionClient(), rp)
        monkeypatch.setattr(_PATCH_TARGET, _Datetime22h)
        await svc.enviar_mensagem(
            ESCRITORIO_ID, CLIENTE_ID, TEXTO, permitir_agendamento=False
        )
        assert rp.interacoes_salvas[0]["status"] == "bloqueado:fora_horario_comercial"


# ---------------------------------------------------------------------------
# enviar_mensagem — erros da Evolution API
# ---------------------------------------------------------------------------


class TestEnviarMensagemErrosEvolution:
    async def test_evolution_offline_retorna_ok_false(self):
        svc = WhatsAppService(_FakeEvolutionClientOffline(), _FakeRepositorio())
        resultado = await svc.enviar_mensagem(ESCRITORIO_ID, CLIENTE_ID, TEXTO)
        assert resultado["ok"] is False
        assert resultado["erro"] == "instancia_offline"

    async def test_evolution_offline_salva_interacao_falha(self):
        rp = _FakeRepositorio()
        svc = WhatsAppService(_FakeEvolutionClientOffline(), rp)
        await svc.enviar_mensagem(ESCRITORIO_ID, CLIENTE_ID, TEXTO)
        assert rp.interacoes_salvas[0]["status"] == "falha:instancia_offline"

    async def test_evolution_offline_payload_contem_erro(self):
        rp = _FakeRepositorio()
        svc = WhatsAppService(_FakeEvolutionClientOffline(), rp)
        await svc.enviar_mensagem(ESCRITORIO_ID, CLIENTE_ID, TEXTO)
        payload = rp.interacoes_salvas[0]["payload_resposta"]
        assert payload.get("erro")  # truthy: não é None nem string vazia

    async def test_evolution_error_generico_retorna_ok_false(self):
        svc = WhatsAppService(_FakeEvolutionClientError(), _FakeRepositorio())
        resultado = await svc.enviar_mensagem(ESCRITORIO_ID, CLIENTE_ID, TEXTO)
        assert resultado["ok"] is False
        assert resultado["erro"] == "evolution_error"

    async def test_evolution_error_generico_salva_interacao_falha(self):
        rp = _FakeRepositorio()
        svc = WhatsAppService(_FakeEvolutionClientError(), rp)
        await svc.enviar_mensagem(ESCRITORIO_ID, CLIENTE_ID, TEXTO)
        assert rp.interacoes_salvas[0]["status"] == "falha:evolution"

    async def test_evolution_error_generico_payload_contem_erro(self):
        rp = _FakeRepositorio()
        svc = WhatsAppService(_FakeEvolutionClientError(), rp)
        await svc.enviar_mensagem(ESCRITORIO_ID, CLIENTE_ID, TEXTO)
        payload = rp.interacoes_salvas[0]["payload_resposta"]
        assert payload.get("erro")  # truthy: não é None nem string vazia


# ---------------------------------------------------------------------------
# enviar_boas_vindas
# ---------------------------------------------------------------------------


class TestEnviarBoasVindas:
    async def test_retorna_ok_true(self):
        svc, ev, rp = _service()
        resultado = await svc.enviar_boas_vindas(ESCRITORIO_ID, CLIENTE_ID)
        assert resultado["ok"] is True

    async def test_texto_contem_seja_bem_vindo(self):
        svc, ev, rp = _service()
        await svc.enviar_boas_vindas(ESCRITORIO_ID, CLIENTE_ID)
        texto_enviado = ev.chamadas_texto[0]["texto"]
        assert "bem-vindo" in texto_enviado.lower()

    async def test_texto_contem_aviso_juridico(self):
        svc, ev, rp = _service()
        await svc.enviar_boas_vindas(ESCRITORIO_ID, CLIENTE_ID)
        texto_enviado = ev.chamadas_texto[0]["texto"]
        # Alinhado ao template literal: "não substituem orientação jurídica formal"
        assert "não substituem orientação jurídica formal" in texto_enviado

    async def test_processo_id_none(self):
        svc, ev, rp = _service()
        await svc.enviar_boas_vindas(ESCRITORIO_ID, CLIENTE_ID)
        assert rp.interacoes_salvas[0]["processo_id"] is None

    async def test_chama_exatamente_uma_vez_evolution(self):
        svc, ev, rp = _service()
        await svc.enviar_boas_vindas(ESCRITORIO_ID, CLIENTE_ID)
        assert len(ev.chamadas_texto) == 1


# ---------------------------------------------------------------------------
# enviar_pesquisa_satisfacao
# ---------------------------------------------------------------------------


class TestEnviarPesquisaSatisfacao:
    async def test_retorna_ok_true(self):
        svc, ev, rp = _service()
        resultado = await svc.enviar_pesquisa_satisfacao(ESCRITORIO_ID, CLIENTE_ID)
        assert resultado["ok"] is True

    async def test_envia_botoes_nao_texto(self):
        svc, ev, rp = _service()
        await svc.enviar_pesquisa_satisfacao(ESCRITORIO_ID, CLIENTE_ID)
        assert len(ev.chamadas_botoes) == 1
        assert len(ev.chamadas_texto) == 0

    async def test_envia_5_botoes_nps(self):
        svc, ev, rp = _service()
        await svc.enviar_pesquisa_satisfacao(ESCRITORIO_ID, CLIENTE_ID)
        botoes = ev.chamadas_botoes[0]["botoes"]
        assert len(botoes) == 5

    async def test_botoes_tem_ids_nps(self):
        svc, ev, rp = _service()
        await svc.enviar_pesquisa_satisfacao(ESCRITORIO_ID, CLIENTE_ID)
        ids = [b["buttonId"] for b in ev.chamadas_botoes[0]["botoes"]]
        assert set(ids) == {"nps_1", "nps_2", "nps_3", "nps_4", "nps_5"}

    async def test_salva_interacao_com_status_nps(self):
        svc, ev, rp = _service()
        await svc.enviar_pesquisa_satisfacao(ESCRITORIO_ID, CLIENTE_ID)
        assert rp.interacoes_salvas[0]["status"] == "enviado:nps"

    async def test_evolution_error_retorna_ok_false(self):
        svc = WhatsAppService(_FakeEvolutionClientError(), _FakeRepositorio())
        resultado = await svc.enviar_pesquisa_satisfacao(ESCRITORIO_ID, CLIENTE_ID)
        assert resultado["ok"] is False
        assert resultado["erro"] == "falha_envio_nps"

    async def test_evolution_error_salva_interacao_falha_nps(self):
        rp = _FakeRepositorio()
        svc = WhatsAppService(_FakeEvolutionClientError(), rp)
        await svc.enviar_pesquisa_satisfacao(ESCRITORIO_ID, CLIENTE_ID)
        assert rp.interacoes_salvas[0]["status"] == "falha:nps"

    async def test_bypassa_rate_limit(self):
        # enviar_pesquisa_satisfacao chama enviar_botoes diretamente, sem passar por
        # _pode_enviar_agora — NPS é enviado mesmo com o limite diário esgotado.
        # Se esse comportamento for indesejado, o bug é no código de produção.
        svc, ev, rp = _service(preferencia="livre", mensagens_hoje=5)
        resultado = await svc.enviar_pesquisa_satisfacao(ESCRITORIO_ID, CLIENTE_ID)
        assert resultado["ok"] is True
        assert len(ev.chamadas_botoes) == 1

    async def test_bypassa_horario_comercial(self, monkeypatch):
        # Da mesma forma, NPS é enviado fora do horário comercial.
        svc, _, _ = _service(preferencia="comercial", mensagens_hoje=0)
        monkeypatch.setattr(_PATCH_TARGET, _Datetime22h)
        resultado = await svc.enviar_pesquisa_satisfacao(ESCRITORIO_ID, CLIENTE_ID)
        assert resultado["ok"] is True


# ---------------------------------------------------------------------------
# Métodos não implementados
# ---------------------------------------------------------------------------


class TestMetodosNotImplemented:
    async def test_enviar_notificacao_andamento_raises(self):
        svc, _, _ = _service()
        with pytest.raises(NotImplementedError):
            await svc.enviar_notificacao_andamento(PROCESSO_ID, "Audiência marcada")

    async def test_enviar_sem_movimentacao_raises(self):
        svc, _, _ = _service()
        with pytest.raises(NotImplementedError):
            await svc.enviar_sem_movimentacao(PROCESSO_ID)
