"""
Testes do Agendamento Inteligente — Fases 3 e 4.

Cobertura:
  - prazos.py: extração de prazos dos andamentos, datas a evitar, conflitos
  - notifier.py: normalização de números, interpretação de respostas (regex),
    escolha de opção pelo cliente, mensagens, fluxo advogado com lock Redis
  - state.py: fallback de keywords para agendar_reuniao
  - nodes/intent.py: threshold de confiança 0.80
  - nodes/agendamento.py: criação de proposta com disponibilidade real (SQLite)
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from feature_1_ia_personalizada.services.agendamento.notifier import (
    AgendamentoNotifier,
    mesmo_numero,
    montar_mensagem_proposta,
    normalizar_numero_whatsapp,
)
from feature_1_ia_personalizada.services.agendamento.prazos import (
    PrazoDetectado,
    datas_a_evitar,
    descrever_conflito,
    extrair_prazos_do_texto,
)
from feature_1_ia_personalizada.services.ai.state import classificar_por_keywords
from shared.models.agendamento import Agendamento
from shared.models.disponibilidade_advogado import DisponibilidadeAdvogado

_HOJE = date(2026, 7, 5)


# ---------------------------------------------------------------------------
# prazos.py
# ---------------------------------------------------------------------------


class TestExtrairPrazos:
    def test_prazo_com_data_sem_ano(self):
        resultado = extrair_prazos_do_texto("Prazo para contestação até 10/07", _HOJE)
        assert len(resultado) == 1
        assert resultado[0][0] == date(2026, 7, 10)

    def test_prazo_com_ano_completo(self):
        resultado = extrair_prazos_do_texto("Intimação com prazo em 15/08/2026", _HOJE)
        assert resultado[0][0] == date(2026, 8, 15)

    def test_data_passada_sem_ano_vai_para_proximo_ano(self):
        # 10/01 já passou há mais de 30 dias em 05/07 → assume ano seguinte
        resultado = extrair_prazos_do_texto("prazo final 10/01", _HOJE)
        assert resultado[0][0] == date(2027, 1, 10)

    def test_texto_sem_mencao_a_prazo_ignora_datas(self):
        assert extrair_prazos_do_texto("Audiência marcada para 10/07", _HOJE) == []

    def test_texto_com_prazo_sem_data_retorna_vazio(self):
        assert extrair_prazos_do_texto("O prazo está correndo normalmente", _HOJE) == []

    def test_data_invalida_descartada(self):
        assert extrair_prazos_do_texto("prazo em 32/13", _HOJE) == []

    def test_datas_a_evitar_inclui_vespera(self):
        prazos = [
            PrazoDetectado(
                data=date(2026, 7, 10),
                descricao="x",
                processo_id=1,
                cliente_id=1,
                numero_cnj=None,
            )
        ]
        evitar = datas_a_evitar(prazos)
        assert date(2026, 7, 10) in evitar
        assert date(2026, 7, 9) in evitar
        assert date(2026, 7, 8) not in evitar

    def test_descrever_conflito(self):
        prazos = [
            PrazoDetectado(
                data=date(2026, 7, 10),
                descricao="Prazo de contestação",
                processo_id=1,
                cliente_id=1,
                numero_cnj="0001234-56.2026.8.26.0100",
            )
        ]
        assert descrever_conflito(date(2026, 7, 10), prazos) is not None
        assert descrever_conflito(date(2026, 7, 9), prazos) is not None  # véspera
        assert descrever_conflito(date(2026, 7, 8), prazos) is None


# ---------------------------------------------------------------------------
# Normalização de números
# ---------------------------------------------------------------------------


class TestNumeros:
    def test_normalizar_adiciona_codigo_pais(self):
        assert normalizar_numero_whatsapp("(11) 99999-8888") == "5511999998888"

    def test_normalizar_mantem_codigo_existente(self):
        assert normalizar_numero_whatsapp("5511999998888") == "5511999998888"

    def test_mesmo_numero_formatos_diferentes(self):
        assert mesmo_numero("5511999998888", "(11) 99999-8888")

    def test_mesmo_numero_tolera_nono_digito(self):
        # WhatsApp às vezes envia sem o nono dígito
        assert mesmo_numero("551199998888", "5511999998888")

    def test_numeros_diferentes(self):
        assert not mesmo_numero("5511999998888", "5511988887777")

    def test_ddd_diferente_nao_casa(self):
        assert not mesmo_numero("5511999998888", "5521999998888")

    def test_vazio_nao_casa(self):
        assert not mesmo_numero("", "5511999998888")
        assert not mesmo_numero(None, None)


# ---------------------------------------------------------------------------
# Interpretação da resposta do advogado (regex)
# ---------------------------------------------------------------------------


class TestInterpretarRespostaAdvogado:
    @pytest.mark.parametrize("texto", ["1", "sim", "Sim, pode confirmar", "ok", "confirmado"])
    def test_confirmacoes(self, texto):
        assert AgendamentoNotifier._interpretar_resposta_advogado_regex(texto) == "confirmar"

    @pytest.mark.parametrize("texto", ["2", "não", "nao", "recusar", "melhor cancelar"])
    def test_recusas(self, texto):
        assert AgendamentoNotifier._interpretar_resposta_advogado_regex(texto) == "recusar"

    @pytest.mark.parametrize("texto", ["não pode ser", "hmm talvez", "quem é?"])
    def test_ambiguos_vao_para_claude(self, texto):
        # "não pode ser" casa CONFIRMAR (pode) e RECUSAR (não) → ambíguo
        assert AgendamentoNotifier._interpretar_resposta_advogado_regex(texto) == "outro"


# ---------------------------------------------------------------------------
# Escolha da opção pelo cliente
# ---------------------------------------------------------------------------

_OPCOES = [
    {
        "inicio": "2026-07-07T13:00:00+00:00",
        "fim": "2026-07-07T14:00:00+00:00",
        "label": "Terça-feira, 07/07 às 10h",
    },
    {
        "inicio": "2026-07-08T17:00:00+00:00",
        "fim": "2026-07-08T18:00:00+00:00",
        "label": "Quarta-feira, 08/07 às 14h",
    },
    {
        "inicio": "2026-07-09T19:00:00+00:00",
        "fim": "2026-07-09T20:00:00+00:00",
        "label": "Quinta-feira, 09/07 às 16h",
    },
]


class TestExtrairEscolha:
    def test_numero_isolado(self):
        assert AgendamentoNotifier._extrair_escolha("2", _OPCOES) == 1

    def test_numero_com_ruido(self):
        assert AgendamentoNotifier._extrair_escolha(" opção 3! ", _OPCOES) == 2

    def test_dia_da_semana(self):
        assert AgendamentoNotifier._extrair_escolha("pode ser na quarta", _OPCOES) == 1

    def test_data_explicita(self):
        assert AgendamentoNotifier._extrair_escolha("prefiro dia 09/07", _OPCOES) == 2

    def test_hora(self):
        assert AgendamentoNotifier._extrair_escolha("às 14h tá ótimo", _OPCOES) == 1

    def test_hora_com_dois_pontos(self):
        assert AgendamentoNotifier._extrair_escolha("pode ser 16:00", _OPCOES) == 2

    def test_negacao_nao_seleciona(self):
        # "não posso às 14h" NÃO deve selecionar a opção das 14h
        assert AgendamentoNotifier._extrair_escolha("não posso às 14h", _OPCOES) is None

    def test_mensagem_nao_relacionada(self):
        assert AgendamentoNotifier._extrair_escolha("qual o status do processo?", _OPCOES) is None

    def test_numero_fora_do_range(self):
        assert AgendamentoNotifier._extrair_escolha("5", _OPCOES) is None

    def test_ambiguidade_entre_opcoes(self):
        # menciona duas opções → ambíguo, não seleciona
        assert AgendamentoNotifier._extrair_escolha("quarta ou quinta", _OPCOES) is None


class TestMontarMensagemProposta:
    def test_contem_tres_opcoes_e_nome(self):
        msg = montar_mensagem_proposta("João da Silva", _OPCOES)
        assert "João" in msg
        assert "1️⃣" in msg and "2️⃣" in msg and "3️⃣" in msg
        assert "Terça-feira, 07/07 às 10h" in msg

    def test_reproposta_menciona_ajuste(self):
        msg = montar_mensagem_proposta("Maria", _OPCOES, reproposta=True)
        assert "ajustar a agenda" in msg


# ---------------------------------------------------------------------------
# Keywords fallback (state.py)
# ---------------------------------------------------------------------------


class TestKeywordsAgendamento:
    @pytest.mark.parametrize(
        "msg",
        [
            "podemos marcar uma reunião?",
            "quero agendar um horário",
            "preciso falar com você urgente",
            "quando você tem horário disponível?",
            "quero conversar com o advogado pessoalmente",
        ],
    )
    def test_frases_de_agendamento(self, msg):
        assert classificar_por_keywords(msg) == "agendar_reuniao"

    @pytest.mark.parametrize(
        "msg, esperado",
        [
            ("qual o status do meu processo?", "status"),
            ("o que significa trânsito em julgado?", "duvida_termo"),
            ("bom dia!", "saudacao"),
        ],
    )
    def test_frases_normais_nao_disparam(self, msg, esperado):
        assert classificar_por_keywords(msg) == esperado


# ---------------------------------------------------------------------------
# Threshold de confiança (nodes/intent.py)
# ---------------------------------------------------------------------------


class TestThresholdAgendamento:
    async def _classificar(self, resposta_claude: str) -> str:
        from feature_1_ia_personalizada.services.ai.nodes.intent import (
            node_classificar_intencao,
        )

        deps = SimpleNamespace(
            claude=SimpleNamespace(classificar_intencao=AsyncMock(return_value=resposta_claude))
        )
        state = {"escritorio_id": 1, "cliente_id": 1, "mensagem_original": "quero reunião"}
        resultado = await node_classificar_intencao(state, deps)  # type: ignore[arg-type]
        return resultado["intencao"]

    @pytest.mark.asyncio
    async def test_confianca_alta_mantem_agendamento(self):
        intencao = await self._classificar('{"intencao": "agendar_reuniao", "confianca": 0.92}')
        assert intencao == "agendar_reuniao"

    @pytest.mark.asyncio
    async def test_confianca_baixa_vira_duvida_geral(self):
        intencao = await self._classificar('{"intencao": "agendar_reuniao", "confianca": 0.55}')
        assert intencao == "duvida_geral"

    @pytest.mark.asyncio
    async def test_sem_confianca_assume_valida(self):
        intencao = await self._classificar('{"intencao": "agendar_reuniao"}')
        assert intencao == "agendar_reuniao"


# ---------------------------------------------------------------------------
# Fluxos com banco (SQLite in-memory) — seleção do cliente e resposta do advogado
# ---------------------------------------------------------------------------


def _evolution_mock() -> SimpleNamespace:
    return SimpleNamespace(enviar_texto=AsyncMock(return_value={}))


async def _preparar_cenario(db_session, escritorio_factory, cliente_factory):
    escritorio = await escritorio_factory()
    escritorio.telefone_advogado = "(11) 98888-7777"
    escritorio.webhook_whatsapp_instance = "instancia-teste"
    escritorio.timezone = "America/Sao_Paulo"
    cliente = await cliente_factory(escritorio.id, nome="João da Silva")
    await db_session.commit()
    return escritorio, cliente


def _opcoes_futuras() -> list[dict]:
    """
    Opções sempre no futuro relativo a agora — datas fixas apodreceriam com o
    relógio real (a validação de slot-no-passado dispararia reproposta indevida).
    Labels dos _OPCOES fixos continuam usados nos testes de parsing puro.
    """
    base = (datetime.now(UTC) + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
    opcoes = []
    for i, rotulo in enumerate(["Opção A", "Opção B", "Opção C"]):
        inicio = base + timedelta(days=i)
        opcoes.append(
            {
                "inicio": inicio.isoformat(),
                "fim": (inicio + timedelta(hours=1)).isoformat(),
                "label": f"{rotulo} — {inicio.strftime('%d/%m às %Hh')}",
            }
        )
    return opcoes


def _nova_proposta(escritorio_id: int, cliente_id: int) -> Agendamento:
    agora = datetime.now(UTC)
    return Agendamento(
        escritorio_id=escritorio_id,
        cliente_id=cliente_id,
        status="aguardando_cliente",
        opcoes_propostas=_opcoes_futuras(),
        motivo_cliente="preciso falar sobre meu processo",
        proposta_enviada_em=agora,
        expira_em=agora + timedelta(hours=48),
        whatsapp_proposta_cliente_enviado=True,
        whatsapp_notificacao_advogado_enviado=False,
        whatsapp_confirmacao_cliente_enviado=False,
        whatsapp_confirmacao_pre_reuniao_enviado=False,
    )


@pytest.mark.asyncio
class TestProcessarRespostaCliente:
    async def test_escolha_valida_transiciona_e_notifica_advogado(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        ag = _nova_proposta(escritorio.id, cliente.id)
        db_session.add(ag)
        await db_session.commit()

        evolution = _evolution_mock()
        notifier = AgendamentoNotifier(db_session, evolution, redis=fake_redis)  # type: ignore[arg-type]

        resposta = await notifier.processar_resposta_cliente(escritorio.id, cliente.id, "2")

        assert resposta is not None
        assert ag.opcoes_propostas[1]["label"] in resposta
        await db_session.refresh(ag)
        assert ag.status == "aguardando_advogado"
        assert ag.opcao_selecionada_pos == 1
        assert ag.data_hora_inicio is not None
        assert ag.whatsapp_notificacao_advogado_enviado is True
        # notificação foi para o número do advogado
        destino = evolution.enviar_texto.call_args[0][1]
        assert destino == "5511988887777"
        corpo = evolution.enviar_texto.call_args[0][2]
        assert "João da Silva" in corpo
        assert "preciso falar sobre meu processo" in corpo

    async def test_mensagem_nao_relacionada_segue_fluxo_normal(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        db_session.add(_nova_proposta(escritorio.id, cliente.id))
        await db_session.commit()

        notifier = AgendamentoNotifier(db_session, _evolution_mock(), redis=fake_redis)  # type: ignore[arg-type]
        resposta = await notifier.processar_resposta_cliente(
            escritorio.id, cliente.id, "qual o status do meu processo?"
        )
        assert resposta is None

    async def test_sem_proposta_pendente_retorna_none(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        notifier = AgendamentoNotifier(db_session, _evolution_mock(), redis=fake_redis)  # type: ignore[arg-type]
        assert await notifier.processar_resposta_cliente(escritorio.id, cliente.id, "1") is None

    async def test_proposta_expirada_ignorada(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        ag = _nova_proposta(escritorio.id, cliente.id)
        ag.expira_em = datetime.now(UTC) - timedelta(hours=1)
        db_session.add(ag)
        await db_session.commit()

        notifier = AgendamentoNotifier(db_session, _evolution_mock(), redis=fake_redis)  # type: ignore[arg-type]
        assert await notifier.processar_resposta_cliente(escritorio.id, cliente.id, "1") is None


def _pendente_aprovacao(escritorio_id: int, cliente_id: int) -> Agendamento:
    ag = _nova_proposta(escritorio_id, cliente_id)
    opcoes = ag.opcoes_propostas or []
    ag.status = "aguardando_advogado"
    ag.opcao_selecionada_pos = 0
    ag.data_hora_inicio = datetime.fromisoformat(opcoes[0]["inicio"])
    ag.data_hora_fim = datetime.fromisoformat(opcoes[0]["fim"])
    ag.resposta_cliente_em = datetime.now(UTC)
    ag.whatsapp_notificacao_advogado_enviado = True
    return ag


@pytest.mark.asyncio
class TestProcessarRespostaAdvogado:
    async def test_confirmar_via_whatsapp(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        ag = _pendente_aprovacao(escritorio.id, cliente.id)
        db_session.add(ag)
        await db_session.commit()

        evolution = _evolution_mock()
        notifier = AgendamentoNotifier(db_session, evolution, redis=fake_redis)  # type: ignore[arg-type]
        resultado = await notifier.processar_resposta_advogado("1", escritorio.id)

        assert resultado["status"] == "confirmado"
        await db_session.refresh(ag)
        assert ag.status == "confirmado"
        assert ag.canal_aprovacao == "whatsapp"
        assert ag.whatsapp_confirmacao_cliente_enviado is True
        # 2 envios: confirmação ao cliente + ack ao advogado
        assert evolution.enviar_texto.await_count == 2

    async def test_recusar_via_whatsapp(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        ag = _pendente_aprovacao(escritorio.id, cliente.id)
        db_session.add(ag)
        await db_session.commit()

        evolution = _evolution_mock()
        notifier = AgendamentoNotifier(db_session, evolution, redis=fake_redis)  # type: ignore[arg-type]
        resultado = await notifier.processar_resposta_advogado("2", escritorio.id)

        assert resultado["status"] == "recusado"
        await db_session.refresh(ag)
        assert ag.status == "cancelado"
        assert ag.motivo_cancelamento == "Recusado pelo advogado via WhatsApp"

    async def test_hub_confirmou_antes_responde_ja_confirmada(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        ag = _pendente_aprovacao(escritorio.id, cliente.id)
        ag.status = "confirmado"
        ag.canal_aprovacao = "hub"
        ag.resposta_advogado_em = datetime.now(UTC)
        db_session.add(ag)
        await db_session.commit()

        evolution = _evolution_mock()
        notifier = AgendamentoNotifier(db_session, evolution, redis=fake_redis)  # type: ignore[arg-type]
        resultado = await notifier.processar_resposta_advogado("1", escritorio.id)

        assert resultado["status"] == "ja_confirmado"
        corpo = evolution.enviar_texto.call_args[0][2]
        assert "já confirmada" in corpo

    async def test_lock_ocupado_nao_processa_duas_vezes(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        ag = _pendente_aprovacao(escritorio.id, cliente.id)
        db_session.add(ag)
        await db_session.commit()

        # Simula lock adquirido pelo Hub (SET NX falha)
        await fake_redis.set(f"agendamento_confirmar:{ag.id}", "hub")

        notifier = AgendamentoNotifier(db_session, _evolution_mock(), redis=fake_redis)  # type: ignore[arg-type]
        resultado = await notifier.processar_resposta_advogado("1", escritorio.id)

        assert resultado["status"] == "lock_ocupado"
        await db_session.refresh(ag)
        assert ag.status == "aguardando_advogado"  # nada mudou

    async def test_texto_ambiguo_sem_claude_pede_1_ou_2(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        db_session.add(_pendente_aprovacao(escritorio.id, cliente.id))
        await db_session.commit()

        evolution = _evolution_mock()
        notifier = AgendamentoNotifier(db_session, evolution, redis=fake_redis)  # type: ignore[arg-type]
        resultado = await notifier.processar_resposta_advogado("quem é?", escritorio.id)

        assert resultado["status"] == "nao_entendido"
        corpo = evolution.enviar_texto.call_args[0][2]
        assert "*1*" in corpo and "*2*" in corpo


# ---------------------------------------------------------------------------
# Nó LangGraph — criação da proposta
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestNodeAgendamento:
    async def _preparar_disponibilidade(self, db_session, escritorio_id: int) -> None:
        for dia in range(6):  # seg–sáb, garante slot em qualquer dia de execução
            db_session.add(
                DisponibilidadeAdvogado(
                    escritorio_id=escritorio_id,
                    dia_semana=dia,
                    hora_inicio=time(9, 0),
                    hora_fim=time(18, 0),
                    ativo=True,
                )
            )
        await db_session.commit()

    def _deps(self, engine, fake_redis):
        from sqlalchemy.ext.asyncio import async_sessionmaker

        return SimpleNamespace(
            session_factory=async_sessionmaker(engine, expire_on_commit=False),
            redis=fake_redis,
        )

    def _state(self, escritorio_id: int, cliente_id: int) -> dict:
        return {
            "escritorio_id": escritorio_id,
            "cliente_id": cliente_id,
            "mensagem_original": "podemos marcar uma reunião?",
            "intencao": "agendar_reuniao",
        }

    async def test_cria_proposta_com_3_opcoes(
        self, db_session, escritorio_factory, cliente_factory, fake_redis, engine
    ):
        from sqlalchemy import select

        from feature_1_ia_personalizada.services.ai.nodes.agendamento import node_agendamento

        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        await self._preparar_disponibilidade(db_session, escritorio.id)

        resultado = await node_agendamento(
            self._state(escritorio.id, cliente.id),  # type: ignore[arg-type]
            self._deps(engine, fake_redis),  # type: ignore[arg-type]
        )

        assert "erro" not in resultado or resultado.get("erro") is None
        assert "1️⃣" in resultado["resposta_verificada"]

        ag = (
            (
                await db_session.execute(
                    select(Agendamento).where(Agendamento.cliente_id == cliente.id)
                )
            )
            .scalars()
            .first()
        )
        assert ag is not None
        assert ag.status == "aguardando_cliente"
        assert len(ag.opcoes_propostas) == 3
        assert ag.motivo_cliente == "podemos marcar uma reunião?"
        assert ag.expira_em is not None

    async def test_pedido_repetido_reapresenta_mesmas_opcoes(
        self, db_session, escritorio_factory, cliente_factory, fake_redis, engine
    ):
        from sqlalchemy import func, select

        from feature_1_ia_personalizada.services.ai.nodes.agendamento import node_agendamento

        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        await self._preparar_disponibilidade(db_session, escritorio.id)
        deps = self._deps(engine, fake_redis)

        await node_agendamento(self._state(escritorio.id, cliente.id), deps)  # type: ignore[arg-type]
        resultado2 = await node_agendamento(self._state(escritorio.id, cliente.id), deps)  # type: ignore[arg-type]

        total = (
            await db_session.execute(
                select(func.count(Agendamento.id)).where(Agendamento.cliente_id == cliente.id)
            )
        ).scalar_one()
        assert total == 1  # não duplica proposta
        assert "1️⃣" in resultado2["resposta_verificada"]

    async def test_sem_disponibilidade_retorna_fallback(
        self, db_session, escritorio_factory, cliente_factory, fake_redis, engine
    ):
        from feature_1_ia_personalizada.services.ai.nodes.agendamento import node_agendamento

        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        resultado = await node_agendamento(
            self._state(escritorio.id, cliente.id),  # type: ignore[arg-type]
            self._deps(engine, fake_redis),  # type: ignore[arg-type]
        )
        assert "não consigo verificar a agenda" in resultado["resposta_verificada"]


# ---------------------------------------------------------------------------
# Robustez de produção — staleness, races e integrações (auditoria)
# ---------------------------------------------------------------------------


async def _criar_disponibilidade(db_session, escritorio_id: int) -> None:
    for dia in range(6):  # seg–sáb, garante slot em qualquer dia de execução
        db_session.add(
            DisponibilidadeAdvogado(
                escritorio_id=escritorio_id,
                dia_semana=dia,
                hora_inicio=time(9, 0),
                hora_fim=time(18, 0),
                ativo=True,
            )
        )
    await db_session.commit()


def _opcao_futura(horas: int, label: str) -> dict:
    inicio = datetime.now(UTC) + timedelta(hours=horas)
    return {
        "inicio": inicio.isoformat(),
        "fim": (inicio + timedelta(hours=1)).isoformat(),
        "label": label,
    }


@pytest.mark.asyncio
class TestSelecaoSlotIndisponivel:
    async def test_slot_no_passado_repropoe_novas_opcoes(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        """Cliente responde perto do fim das 48h e o slot escolhido já passou."""
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        await _criar_disponibilidade(db_session, escritorio.id)

        ag = _nova_proposta(escritorio.id, cliente.id)
        opcao_passada = {
            "inicio": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
            "fim": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "label": "Ontem às 10h",
        }
        ag.opcoes_propostas = [opcao_passada, _opcao_futura(50, "Depois"), _opcao_futura(74, "X")]
        db_session.add(ag)
        await db_session.commit()

        evolution = _evolution_mock()
        notifier = AgendamentoNotifier(db_session, evolution, redis=fake_redis)  # type: ignore[arg-type]
        resposta = await notifier.processar_resposta_cliente(escritorio.id, cliente.id, "1")

        assert resposta is not None
        assert "já passou" in resposta
        assert "1️⃣" in resposta  # novas opções na mesma mensagem
        await db_session.refresh(ag)
        assert ag.status == "aguardando_cliente"
        assert ag.opcao_selecionada_pos is None
        # opções renovadas — todas no futuro
        for op in ag.opcoes_propostas:
            assert datetime.fromisoformat(op["inicio"]) > datetime.now(UTC)
        # advogado NÃO foi notificado de horário inválido
        assert ag.whatsapp_notificacao_advogado_enviado is False

    async def test_slot_ocupado_por_outro_cliente_repropoe(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        """Race: outro cliente confirmou o mesmo horário entre a proposta e a escolha."""
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        outro_cliente = await cliente_factory(escritorio.id, nome="Maria Costa")
        await _criar_disponibilidade(db_session, escritorio.id)

        opcao = _opcao_futura(30, "Amanhã às 10h")
        ag = _nova_proposta(escritorio.id, cliente.id)
        ag.opcoes_propostas = [opcao, _opcao_futura(54, "B"), _opcao_futura(78, "C")]
        # Simula remarcação: flags de um ciclo anterior de confirmação ainda True
        ag.whatsapp_confirmacao_cliente_enviado = True
        ag.whatsapp_confirmacao_pre_reuniao_enviado = True
        db_session.add(ag)

        ocupante = _nova_proposta(escritorio.id, outro_cliente.id)
        ocupante.status = "confirmado"
        ocupante.data_hora_inicio = datetime.fromisoformat(opcao["inicio"])
        ocupante.data_hora_fim = datetime.fromisoformat(opcao["fim"])
        db_session.add(ocupante)
        await db_session.commit()

        notifier = AgendamentoNotifier(db_session, _evolution_mock(), redis=fake_redis)  # type: ignore[arg-type]
        resposta = await notifier.processar_resposta_cliente(escritorio.id, cliente.id, "1")

        assert resposta is not None
        assert "indisponível" in resposta
        await db_session.refresh(ag)
        assert ag.status == "aguardando_cliente"
        # Reproposta zera flags de confirmação — nova confirmação será entregue
        assert ag.whatsapp_confirmacao_cliente_enviado is False
        assert ag.whatsapp_confirmacao_pre_reuniao_enviado is False
        # nenhuma das novas opções colide com o horário ocupado
        for op in ag.opcoes_propostas:
            ini = datetime.fromisoformat(op["inicio"])
            fim = datetime.fromisoformat(op["fim"])
            ini_ocupado = ocupante.data_hora_inicio
            fim_ocupado = ocupante.data_hora_fim
            if ini_ocupado.tzinfo is None:  # SQLite devolve naive
                ini_ocupado = ini_ocupado.replace(tzinfo=UTC)
                fim_ocupado = fim_ocupado.replace(tzinfo=UTC)
            assert not (ini < fim_ocupado and fim > ini_ocupado)

    async def test_sem_alternativas_expira_com_fallback(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        """Slot passou e não há disponibilidade cadastrada → expira com aviso amigável."""
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        ag = _nova_proposta(escritorio.id, cliente.id)
        ag.opcoes_propostas = [
            {
                "inicio": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                "fim": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                "label": "Ontem",
            }
        ]
        db_session.add(ag)
        await db_session.commit()

        notifier = AgendamentoNotifier(db_session, _evolution_mock(), redis=fake_redis)  # type: ignore[arg-type]
        resposta = await notifier.processar_resposta_cliente(escritorio.id, cliente.id, "1")

        assert resposta is not None
        assert "entrar em contato" in resposta
        await db_session.refresh(ag)
        assert ag.status == "expirado"


@pytest.mark.asyncio
class TestPropostaObsoletaNoNode:
    async def test_pedido_com_proposta_expirada_gera_nova(
        self, db_session, escritorio_factory, cliente_factory, fake_redis, engine
    ):
        """Worker de expiração ainda não rodou; novo pedido renova a proposta."""
        from sqlalchemy import func, select

        from feature_1_ia_personalizada.services.ai.nodes.agendamento import node_agendamento

        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        await _criar_disponibilidade(db_session, escritorio.id)

        antiga = _nova_proposta(escritorio.id, cliente.id)
        antiga.expira_em = datetime.now(UTC) - timedelta(hours=1)
        db_session.add(antiga)
        await db_session.commit()

        from sqlalchemy.ext.asyncio import async_sessionmaker

        deps = SimpleNamespace(
            session_factory=async_sessionmaker(engine, expire_on_commit=False),
            redis=fake_redis,
        )
        state = {
            "escritorio_id": escritorio.id,
            "cliente_id": cliente.id,
            "mensagem_original": "quero marcar uma reunião",
            "intencao": "agendar_reuniao",
        }
        resultado = await node_agendamento(state, deps)  # type: ignore[arg-type]

        assert "1️⃣" in resultado["resposta_verificada"]
        await db_session.refresh(antiga)
        assert antiga.status == "expirado"
        total = (
            await db_session.execute(
                select(func.count(Agendamento.id)).where(Agendamento.cliente_id == cliente.id)
            )
        ).scalar_one()
        assert total == 2  # antiga expirada + proposta nova


@pytest.mark.asyncio
class TestFilaDePendenciasAdvogado:
    async def test_ack_menciona_proxima_pendencia(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        escritorio, cliente1 = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        cliente2 = await cliente_factory(escritorio.id, nome="Maria Fila")

        mais_antiga = _pendente_aprovacao(escritorio.id, cliente2.id)
        mais_antiga.resposta_cliente_em = datetime.now(UTC) - timedelta(hours=2)
        db_session.add(mais_antiga)

        mais_recente = _pendente_aprovacao(escritorio.id, cliente1.id)
        db_session.add(mais_recente)
        await db_session.commit()

        evolution = _evolution_mock()
        notifier = AgendamentoNotifier(db_session, evolution, redis=fake_redis)  # type: ignore[arg-type]
        resultado = await notifier.processar_resposta_advogado("1", escritorio.id)

        # Confirma a mais recente (cliente1) e menciona a próxima da fila (Maria)
        assert resultado["status"] == "confirmado"
        assert resultado["agendamento_id"] == mais_recente.id
        ack = evolution.enviar_texto.call_args[0][2]
        assert "Maria Fila" in ack
        assert "aguardando" in ack


@pytest.mark.asyncio
class TestGuardNPSComPropostaPendente:
    async def test_nps_nao_intercepta_escolha_de_horario(
        self, db_session, escritorio_factory, cliente_factory
    ):
        """Cliente com NPS pendente E proposta de horários: '1' é escolha, não nota."""
        from feature_1_ia_personalizada.api.routes.webhook_whatsapp import (
            _processar_resposta_nps,
        )
        from shared.models.interacao import Interacao

        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        db_session.add(
            Interacao(
                escritorio_id=escritorio.id,
                cliente_id=cliente.id,
                tipo="pesquisa_nps",
                direcao="saida",
                metadata_json={"aguardando_nps": True},
            )
        )
        db_session.add(_nova_proposta(escritorio.id, cliente.id))
        await db_session.commit()

        tratado_como_nps = await _processar_resposta_nps("1", cliente, escritorio, db_session)
        assert tratado_como_nps is False  # segue para a IA → seleção de horário


# ---------------------------------------------------------------------------
# Hardening — prazos relativos, eventos em tempo real e factory de worker
# ---------------------------------------------------------------------------


class TestPrazosRelativos:
    def test_prazo_relativo_dias_uteis_por_padrao(self):
        # CPC art. 219: prazos processuais contam em dias úteis.
        # base = sexta 03/07/2026 → 15 dias úteis = 24/07/2026
        from feature_1_ia_personalizada.services.agendamento.prazos import (
            extrair_prazos_relativos,
        )

        base = date(2026, 7, 3)  # sexta-feira
        resultado = extrair_prazos_relativos(
            "Intimação eletrônica. Prazo de 15 dias para contestação.", base, _HOJE
        )
        assert len(resultado) == 1
        assert resultado[0][0] == date(2026, 7, 24)
        assert resultado[0][0].weekday() < 5  # nunca cai em fim de semana

    def test_prazo_relativo_corridos_quando_explicito(self):
        from feature_1_ia_personalizada.services.agendamento.prazos import (
            extrair_prazos_relativos,
        )

        base = date(2026, 7, 3)
        resultado = extrair_prazos_relativos("prazo de 10 dias corridos", base, _HOJE)
        assert resultado[0][0] == date(2026, 7, 13)

    def test_prazo_relativo_com_extenso_entre_parenteses(self):
        from feature_1_ia_personalizada.services.agendamento.prazos import (
            extrair_prazos_relativos,
        )

        resultado = extrair_prazos_relativos(
            "no prazo de 5 (cinco) dias úteis", date(2026, 7, 6), _HOJE
        )
        assert len(resultado) == 1
        assert resultado[0][0] == date(2026, 7, 13)  # seg 06/07 + 5 úteis

    def test_data_passada_no_texto_serve_de_ancora(self):
        # "Intimação em 01/07 — prazo de 15 dias": conta a partir de 01/07,
        # não da data do andamento
        from feature_1_ia_personalizada.services.agendamento.prazos import (
            extrair_prazos_relativos,
        )

        resultado = extrair_prazos_relativos(
            "Intimação em 01/07. Prazo de 15 dias.", date(2026, 6, 20), _HOJE
        )
        assert len(resultado) == 1
        assert resultado[0][0] == date(2026, 7, 22)  # qua 01/07 + 15 úteis

    def test_sem_ancora_nao_arrisca(self):
        from feature_1_ia_personalizada.services.agendamento.prazos import (
            extrair_prazos_relativos,
        )

        assert extrair_prazos_relativos("prazo de 15 dias", None, _HOJE) == []

    def test_dias_absurdos_ignorados(self):
        from feature_1_ia_personalizada.services.agendamento.prazos import (
            extrair_prazos_relativos,
        )

        assert extrair_prazos_relativos("prazo de 500 dias", date(2026, 7, 6), _HOJE) == []

    @pytest.mark.asyncio
    async def test_busca_integra_relativos_com_flag_estimado(
        self, db_session, escritorio_factory, cliente_factory
    ):
        from datetime import datetime as dt

        from feature_1_ia_personalizada.services.agendamento.prazos import (
            buscar_prazos_escritorio,
        )
        from shared.models.processo import Processo

        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        db_session.add(
            Processo(
                escritorio_id=escritorio.id,
                cliente_id=cliente.id,
                numero_cnj="0001234-56.2026.8.26.0100",
                status="ativo",
                ultimo_andamento="Publicada sentença. Prazo de 15 dias para recurso.",
                data_ultimo_andamento=dt(2026, 7, 3, 12, 0),
                estado_atual={
                    "ultimos_andamentos": [
                        "Distribuído por sorteio",  # sem prazo
                        "Publicada sentença. Prazo de 15 dias para recurso.",
                    ]
                },
            )
        )
        await db_session.commit()

        prazos = await buscar_prazos_escritorio(
            db_session, escritorio.id, cliente_id=cliente.id, hoje=_HOJE
        )
        assert len(prazos) == 1
        assert prazos[0].estimado is True
        assert prazos[0].data == date(2026, 7, 24)  # sex 03/07 + 15 úteis

    def test_explicito_continua_sem_flag(self):
        # comportamento antigo preservado: data explícita não é "estimado"
        resultado = extrair_prazos_do_texto("Prazo para contestação até 10/07", _HOJE)
        assert resultado[0][0] == date(2026, 7, 10)


@pytest.mark.asyncio
class TestEventosTempoReal:
    async def test_selecao_do_cliente_publica_evento(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        db_session.add(_nova_proposta(escritorio.id, cliente.id))
        await db_session.commit()

        notifier = AgendamentoNotifier(db_session, _evolution_mock(), redis=fake_redis)  # type: ignore[arg-type]
        resposta = await notifier.processar_resposta_cliente(escritorio.id, cliente.id, "1")

        assert resposta is not None
        publicados = fake_redis._published()
        assert (f"agendamento_ev:{escritorio.id}", "changed") in publicados

    async def test_confirmacao_do_advogado_publica_evento(
        self, db_session, escritorio_factory, cliente_factory, fake_redis
    ):
        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        db_session.add(_pendente_aprovacao(escritorio.id, cliente.id))
        await db_session.commit()

        notifier = AgendamentoNotifier(db_session, _evolution_mock(), redis=fake_redis)  # type: ignore[arg-type]
        resultado = await notifier.processar_resposta_advogado("1", escritorio.id)

        assert resultado["status"] == "confirmado"
        assert (f"agendamento_ev:{escritorio.id}", "changed") in fake_redis._published()

    async def test_publicacao_sem_redis_nao_quebra(self):
        from feature_1_ia_personalizada.services.agendamento.eventos import (
            publicar_evento_agendamento,
        )

        await publicar_evento_agendamento(None, 1)  # não levanta

    async def test_publicacao_com_redis_quebrado_nao_propaga(self):
        from feature_1_ia_personalizada.services.agendamento.eventos import (
            publicar_evento_agendamento,
        )

        class RedisQuebrado:
            async def publish(self, *a):
                raise ConnectionError("down")

        await publicar_evento_agendamento(RedisQuebrado(), 1)  # não levanta


class TestWorkerSessionFactory:
    def test_engine_de_worker_usa_nullpool(self):
        """NullPool = nenhuma conexão sobrevive entre event loops (asyncio.run)."""
        from sqlalchemy.pool import NullPool

        from shared.database.connection import worker_engine

        assert isinstance(worker_engine.pool, NullPool)

    def test_engine_da_api_mantem_pool(self):
        from sqlalchemy.pool import NullPool

        from shared.database.connection import engine

        assert not isinstance(engine.pool, NullPool)

    def test_workers_nao_usam_mais_factory_da_api(self):
        """Nenhum worker/serviço de worker deve importar a factory pooled da API."""
        import pathlib

        alvos = [
            "feature_1_ia_personalizada/workers",
            "feature_1_ia_personalizada/services/messaging/whatsapp.py",
            "feature_1_ia_personalizada/services/ai/processo_state.py",
            "shared/database/worker_queries.py",
        ]
        raiz = pathlib.Path(__file__).resolve().parents[3]
        for alvo in alvos:
            caminho = raiz / alvo
            arquivos = caminho.rglob("*.py") if caminho.is_dir() else [caminho]
            for arq in arquivos:
                conteudo = arq.read_text(encoding="utf-8", errors="replace")
                assert (
                    "import async_session_factory" not in conteudo
                ), f"{arq} ainda usa a factory pooled da API em contexto de worker"


# ---------------------------------------------------------------------------
# Calendário forense — feriados nacionais e recesso (CPC art. 220)
# ---------------------------------------------------------------------------


class TestCalendarioForense:
    def test_pascoa_2026(self):
        from feature_1_ia_personalizada.services.agendamento.prazos import _pascoa

        assert _pascoa(2026) == date(2026, 4, 5)

    def test_feriados_moveis_2026(self):
        from feature_1_ia_personalizada.services.agendamento.prazos import _feriados_nacionais

        feriados = _feriados_nacionais(2026)
        assert date(2026, 2, 17) in feriados  # terça de Carnaval
        assert date(2026, 4, 3) in feriados  # Sexta-feira Santa
        assert date(2026, 6, 4) in feriados  # Corpus Christi
        assert date(2026, 9, 7) in feriados  # Independência
        assert date(2026, 11, 20) in feriados  # Consciência Negra (Lei 14.759)

    def test_contagem_pula_feriado_nacional(self):
        from feature_1_ia_personalizada.services.agendamento.prazos import _somar_dias_uteis

        # sex 04/09/2026 + 2 úteis: seg 07/09 é feriado → ter 08 (1), qua 09 (2)
        assert _somar_dias_uteis(date(2026, 9, 4), 2) == date(2026, 9, 9)

    def test_contagem_pula_recesso_forense(self):
        from feature_1_ia_personalizada.services.agendamento.prazos import _somar_dias_uteis

        # ter 15/12/2026 + 5 úteis: 16,17,18/12 (3) → recesso 20/12–20/01 →
        # qui 21/01 (4), sex 22/01/2027 (5)
        assert _somar_dias_uteis(date(2026, 12, 15), 5) == date(2027, 1, 22)

    def test_recesso_bordas(self):
        from feature_1_ia_personalizada.services.agendamento.prazos import _em_recesso_forense

        assert _em_recesso_forense(date(2026, 12, 20)) is True
        assert _em_recesso_forense(date(2027, 1, 20)) is True
        assert _em_recesso_forense(date(2026, 12, 19)) is False
        assert _em_recesso_forense(date(2027, 1, 21)) is False


# ---------------------------------------------------------------------------
# Google Calendar
# ---------------------------------------------------------------------------


class _FakeHttpResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class _FakeHttp:
    """httpx.AsyncClient fake — grava chamadas e devolve payloads programados."""

    def __init__(self):
        self.chamadas: list[tuple[str, str]] = []
        self.token_calls = 0

    async def post(self, url, json=None, data=None, headers=None):
        self.chamadas.append(("POST", url))
        if "oauth2.googleapis.com/token" in url:
            self.token_calls += 1
            return _FakeHttpResponse(200, {"access_token": "tok-abc", "expires_in": 3600})
        if url.endswith("/events"):
            return _FakeHttpResponse(200, {"id": "evt-123"})
        if url.endswith("/freeBusy"):
            return _FakeHttpResponse(
                200,
                {
                    "calendars": {
                        "primary": {
                            "busy": [
                                {
                                    "start": "2026-07-08T13:00:00Z",
                                    "end": "2026-07-08T14:00:00Z",
                                }
                            ]
                        }
                    }
                },
            )
        return _FakeHttpResponse(404)

    async def delete(self, url, headers=None):
        self.chamadas.append(("DELETE", url))
        return _FakeHttpResponse(204)

    async def aclose(self):
        pass


@pytest.mark.asyncio
class TestGoogleCalendarClient:
    async def test_criar_evento_retorna_id_e_cacheia_token(self, monkeypatch):
        from feature_1_ia_personalizada.services.agendamento import google_calendar as gc

        monkeypatch.setattr(gc.settings, "GOOGLE_CALENDAR_CLIENT_ID", "cid")
        monkeypatch.setattr(gc.settings, "GOOGLE_CALENDAR_CLIENT_SECRET", "sec")

        http = _FakeHttp()
        client = gc.GoogleCalendarClient(refresh_token="rt", http=http)  # type: ignore[arg-type]

        inicio = datetime(2026, 7, 8, 13, 0, tzinfo=UTC)
        eid1 = await client.criar_evento(
            "primary",
            "Reunião — João",
            "d",
            inicio,
            inicio + timedelta(hours=1),
            "America/Sao_Paulo",
        )
        eid2 = await client.criar_evento(
            "primary",
            "Reunião — Maria",
            "d",
            inicio,
            inicio + timedelta(hours=1),
            "America/Sao_Paulo",
        )

        assert eid1 == eid2 == "evt-123"
        assert http.token_calls == 1  # access token cacheado entre chamadas

    async def test_listar_ocupados_parseia_freebusy(self, monkeypatch):
        from feature_1_ia_personalizada.services.agendamento import google_calendar as gc

        monkeypatch.setattr(gc.settings, "GOOGLE_CALENDAR_CLIENT_ID", "cid")
        monkeypatch.setattr(gc.settings, "GOOGLE_CALENDAR_CLIENT_SECRET", "sec")

        client = gc.GoogleCalendarClient(refresh_token="rt", http=_FakeHttp())  # type: ignore[arg-type]
        ocupados = await client.listar_ocupados(
            "primary",
            datetime(2026, 7, 8, tzinfo=UTC),
            datetime(2026, 7, 9, tzinfo=UTC),
        )
        assert ocupados == [
            (
                datetime(2026, 7, 8, 13, 0, tzinfo=UTC),
                datetime(2026, 7, 8, 14, 0, tzinfo=UTC),
            )
        ]


@pytest.mark.asyncio
class TestGoogleCalendarSync:
    async def test_confirmacao_cria_evento_e_persiste_id(
        self, db_session, escritorio_factory, cliente_factory, monkeypatch
    ):
        from feature_1_ia_personalizada.services.agendamento import google_calendar as gc

        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        ag = _pendente_aprovacao(escritorio.id, cliente.id)
        ag.status = "confirmado"
        db_session.add(ag)
        await db_session.commit()

        monkeypatch.setattr(gc.settings, "GOOGLE_CALENDAR_CLIENT_ID", "cid")
        monkeypatch.setattr(gc.settings, "GOOGLE_CALENDAR_CLIENT_SECRET", "sec")
        monkeypatch.setattr(
            gc,
            "_client_do_escritorio",
            lambda e: gc.GoogleCalendarClient(refresh_token="rt", http=_FakeHttp()),  # type: ignore[arg-type]
        )

        ok = await gc.sincronizar_confirmacao(db_session, ag)
        assert ok is True
        await db_session.refresh(ag)
        assert ag.google_event_id == "evt-123"

        # Idempotência: segunda chamada não recria
        assert await gc.sincronizar_confirmacao(db_session, ag) is False

    async def test_remocao_limpa_event_id(
        self, db_session, escritorio_factory, cliente_factory, monkeypatch
    ):
        from feature_1_ia_personalizada.services.agendamento import google_calendar as gc

        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        ag = _pendente_aprovacao(escritorio.id, cliente.id)
        ag.google_event_id = "evt-123"
        db_session.add(ag)
        await db_session.commit()

        monkeypatch.setattr(
            gc,
            "_client_do_escritorio",
            lambda e: gc.GoogleCalendarClient(refresh_token="rt", http=_FakeHttp()),  # type: ignore[arg-type]
        )

        assert await gc.remover_evento_agendamento(db_session, ag) is True
        await db_session.refresh(ag)
        assert ag.google_event_id is None

    async def test_desconectado_e_noop_silencioso(
        self, db_session, escritorio_factory, cliente_factory
    ):
        """Sem credenciais/conexão, sync é no-op — nunca quebra a confirmação."""
        from feature_1_ia_personalizada.services.agendamento import google_calendar as gc

        escritorio, cliente = await _preparar_cenario(
            db_session, escritorio_factory, cliente_factory
        )
        ag = _pendente_aprovacao(escritorio.id, cliente.id)
        ag.status = "confirmado"
        db_session.add(ag)
        await db_session.commit()

        assert await gc.sincronizar_confirmacao(db_session, ag) is False
        assert ag.google_event_id is None

    def test_roundtrip_criptografia_refresh_token(self):
        from feature_1_ia_personalizada.services.agendamento import google_calendar as gc
        from shared.security.encryption import descriptografar

        class _E:
            google_calendar_refresh_token = None
            google_calendar_conectado_em = None

        e = _E()
        gc.salvar_conexao(e, "refresh-secreto")  # type: ignore[arg-type]
        assert e.google_calendar_refresh_token != "refresh-secreto"  # criptografado
        assert descriptografar(e.google_calendar_refresh_token) == "refresh-secreto"
        gc.limpar_conexao(e)  # type: ignore[arg-type]
        assert e.google_calendar_refresh_token is None


@pytest.mark.asyncio
class TestDetectorOcupadosExternos:
    async def test_slot_ocupado_no_google_nao_e_oferecido(
        self, db_session, escritorio_factory, cliente_factory
    ):
        from feature_1_ia_personalizada.services.agendamento.detector import AgendamentoDetector

        escritorio, _ = await _preparar_cenario(db_session, escritorio_factory, cliente_factory)
        await _criar_disponibilidade(db_session, escritorio.id)

        detector = AgendamentoDetector(
            db=db_session, escritorio_id=escritorio.id, timezone_str="America/Sao_Paulo"
        )
        livres = await detector.buscar_slots(num_slots=3)
        assert len(livres) == 3

        # Ocupa exatamente o primeiro slot na agenda externa
        ocupado = [(livres[0].inicio, livres[0].fim)]
        filtrados = await detector.buscar_slots(num_slots=3, ocupados_externos=ocupado)

        assert len(filtrados) == 3
        assert filtrados[0].inicio != livres[0].inicio
        for s in filtrados:
            assert not (livres[0].inicio < s.fim and livres[0].fim > s.inicio)
