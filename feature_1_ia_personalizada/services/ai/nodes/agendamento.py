"""
Nó de agendamento: quando a intenção é `agendar_reuniao`, gera 3 opções de
horário (AgendamentoDetector), cria o Agendamento em `aguardando_cliente` e
devolve a proposta como resposta — sem passar pelo RAG (propor horários não
precisa de contexto jurídico).

O envio da mensagem, a persistência da Interacao e a memória de conversa
seguem pelo nó `enviar_resposta` (caminho único de entrega do grafo).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select

from feature_1_ia_personalizada.services.agendamento.detector import AgendamentoDetector
from feature_1_ia_personalizada.services.agendamento.notifier import (
    _aware,
    montar_mensagem_proposta,
)
from feature_1_ia_personalizada.services.agendamento.prazos import (
    buscar_prazos_escritorio,
    datas_a_evitar,
)
from feature_1_ia_personalizada.services.ai.nodes._helpers import (
    listar_processos_ativos,
    obter_escritorio_cliente,
)
from feature_1_ia_personalizada.services.ai.state import ConversationState, NodeDeps, erros_total
from shared.models.agendamento import Agendamento

logger = structlog.get_logger(__name__)

_PROPOSTA_TTL_H = 48
_DEBOUNCE_TTL_S = 60
_MAX_MOTIVO_CHARS = 500

_MSG_JA_COM_ADVOGADO = (
    "Sua solicitação de reunião já está com o advogado para confirmação. 😊\n\n"
    "Assim que ele confirmar o horário, te aviso por aqui!"
)
_MSG_SEM_DISPONIBILIDADE = (
    "Que bom que você quer conversar! 😊\n\n"
    "No momento não consigo verificar a agenda automaticamente, "
    "mas já registrei seu interesse e o escritório entrará em contato "
    "para combinar o melhor horário."
)
_MSG_PROCESSANDO = "Um instante — já estou verificando os horários disponíveis! 😊"


def _proposta_ainda_valida(ag: Agendamento) -> bool:
    """Proposta serve para reapresentação se não expirou e nenhum slot passou."""
    agora = datetime.now(UTC)
    expira = _aware(ag.expira_em)
    if expira is not None and expira <= agora:
        return False
    try:
        for opcao in ag.opcoes_propostas or []:
            if datetime.fromisoformat(opcao["inicio"]) <= agora:
                return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


async def node_agendamento(state: ConversationState, deps: NodeDeps) -> dict[str, Any]:
    log = logger.bind(escritorio_id=state["escritorio_id"], cliente_id=state["cliente_id"])
    escritorio_id = state["escritorio_id"]
    cliente_id = state["cliente_id"]

    try:
        async with deps.session_factory() as session:
            escritorio, cliente = await obter_escritorio_cliente(session, escritorio_id, cliente_id)
            if not escritorio or not cliente:
                return {"erro": "agendamento:entidade_nao_encontrada"}

            # Proposta já em andamento? (idempotência de conversa)
            pendente = (
                await session.execute(
                    select(Agendamento)
                    .where(
                        Agendamento.escritorio_id == escritorio_id,
                        Agendamento.cliente_id == cliente_id,
                        Agendamento.status.in_(["aguardando_cliente", "aguardando_advogado"]),
                    )
                    .order_by(Agendamento.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            if pendente is not None:
                if pendente.status == "aguardando_advogado":
                    return {
                        "resposta_verificada": _MSG_JA_COM_ADVOGADO,
                        "precisa_regenerar": False,
                    }
                if pendente.opcoes_propostas and _proposta_ainda_valida(pendente):
                    # Reapresenta as mesmas opções — cobre reenvio e falha anterior de entrega
                    texto = montar_mensagem_proposta(cliente.nome, pendente.opcoes_propostas)
                    return {"resposta_verificada": texto, "precisa_regenerar": False}
                # Proposta obsoleta (expirada ou com slot no passado) que o worker
                # horário ainda não varreu — expira aqui e gera opções novas abaixo
                pendente.status = "expirado"
                await session.commit()
                log.info("agendamento_proposta_obsoleta_renovada", agendamento_id=pendente.id)

            # Debounce: evita propostas duplicadas em mensagens quase simultâneas
            try:
                debounce_key = f"agendamento_debounce:{escritorio_id}:{cliente_id}"
                adquirido = await deps.redis.set(debounce_key, "1", ex=_DEBOUNCE_TTL_S, nx=True)
                if not adquirido:
                    return {"resposta_verificada": _MSG_PROCESSANDO, "precisa_regenerar": False}
            except Exception:
                pass  # Redis indisponível não bloqueia o fluxo

            # Prazos processuais do cliente → dias a evitar na proposta
            prazos = await buscar_prazos_escritorio(session, escritorio_id, cliente_id=cliente_id)
            evitar = datas_a_evitar(prazos)

            detector = AgendamentoDetector(
                db=session,
                escritorio_id=escritorio_id,
                timezone_str=escritorio.timezone or "America/Sao_Paulo",
            )
            slots = await detector.buscar_slots(num_slots=3, datas_evitar=evitar)

            if not slots:
                log.warning("agendamento_sem_slots")
                return {
                    "resposta_verificada": _MSG_SEM_DISPONIBILIDADE,
                    "precisa_regenerar": False,
                }

            processos = await listar_processos_ativos(session, escritorio_id, cliente_id)
            processo_id = processos[0].id if processos else None

            opcoes = [
                {
                    "inicio": s.inicio.isoformat(),
                    "fim": s.fim.isoformat(),
                    "label": s.label,
                    "conflito_prazo": s.conflito_prazo,
                }
                for s in slots
            ]

            agora = datetime.now(UTC)
            agendamento = Agendamento(
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                processo_id=processo_id,
                status="aguardando_cliente",
                opcoes_propostas=opcoes,
                motivo_cliente=state["mensagem_original"][:_MAX_MOTIVO_CHARS],
                proposta_enviada_em=agora,
                expira_em=agora + timedelta(hours=_PROPOSTA_TTL_H),
                # O nó enviar_resposta entrega a proposta na sequência do grafo
                whatsapp_proposta_cliente_enviado=True,
            )
            session.add(agendamento)
            await session.commit()

            from feature_1_ia_personalizada.services.agendamento.eventos import (
                publicar_evento_agendamento,
            )

            await publicar_evento_agendamento(deps.redis, escritorio_id)

            try:
                from feature_1_ia_personalizada.api.routes.metrics import (
                    agendamentos_criados_total,
                )

                agendamentos_criados_total.labels(escritorio_id=str(escritorio_id)).inc()
                if any(op["conflito_prazo"] for op in opcoes):
                    from feature_1_ia_personalizada.api.routes.metrics import (
                        agendamentos_conflito_prazo_total,
                    )

                    agendamentos_conflito_prazo_total.labels(escritorio_id=str(escritorio_id)).inc()
            except Exception:
                pass

            texto = montar_mensagem_proposta(cliente.nome, opcoes)
            log.info("agendamento_proposta_criada", agendamento_id=agendamento.id)
            return {"resposta_verificada": texto, "precisa_regenerar": False}

    except Exception as exc:
        erros_total.labels(no="agendamento").inc()
        log.error("agendamento_node_erro", erro=str(exc))
        return {"erro": f"agendamento:{exc}"}
