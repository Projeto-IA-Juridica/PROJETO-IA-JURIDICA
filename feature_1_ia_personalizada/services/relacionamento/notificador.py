"""
feature_1_ia_personalizada/services/relacionamento/notificador.py
==================================================================
Envio de mensagens para o ADVOGADO (não para o cliente).

Existe separado do `WhatsAppService` porque as regras são outras: o cliente
tem horário comercial, rate limit e proibição de emoji; o advogado é um
usuário interno, recebe formatação e pode ser avisado de algo urgente fora do
horário. O que ele precisa é do oposto — **não ser bombardeado**.

Daí a trava por chave: cada aviso declara uma chave e uma janela; enquanto a
janela não expira, o mesmo aviso não é reenviado. É o que impede que uma
reanálise de CRM a cada poucas horas vire uma enxurrada de alertas sobre o
mesmo cliente.

A trava usa Redis quando disponível. Sem Redis, o envio acontece — perder um
alerta é pior do que repetir um.
"""

from __future__ import annotations

from typing import Any

import structlog

from shared.config.settings import settings
from shared.models.usuario import Usuario

logger = structlog.get_logger(__name__)

# Prefixo das chaves de trava, para não colidir com outros usos do Redis.
_PREFIXO_TRAVA = "notif_advogado"


def _chave(escopo: str, *partes: Any) -> str:
    return ":".join([_PREFIXO_TRAVA, escopo, *(str(p) for p in partes)])


async def _ja_avisado(redis: Any, chave: str, janela_segundos: int) -> bool:
    """
    Marca a chave e diz se ela JÁ existia.

    `SET NX EX` é atômico: dois workers processando o mesmo cliente ao mesmo
    tempo não conseguem ambos enviar.
    """
    if redis is None:
        return False
    try:
        adquiriu = await redis.set(chave, "1", ex=janela_segundos, nx=True)
        return not adquiriu
    except Exception as exc:  # Redis fora não pode impedir um alerta
        logger.warning("notificador.trava_indisponivel", erro=str(exc), chave=chave)
        return False


async def notificar_advogado(
    advogado: Usuario,
    escritorio_instance: str | None,
    texto: str,
    *,
    redis: Any = None,
    chave_trava: str | None = None,
    janela_segundos: int = 86_400,
) -> bool:
    """
    Envia `texto` ao WhatsApp do advogado.

    Args:
        advogado: destinatário — precisa ter `whatsapp_numero`.
        escritorio_instance: instância da Evolution do escritório.
        texto: mensagem já formatada.
        redis: cliente Redis para a trava anti-spam (opcional).
        chave_trava: identificador do aviso. Quando informado, o mesmo aviso não
            se repete dentro da janela.
        janela_segundos: duração da trava (padrão: 24 h).

    Returns:
        True se a mensagem foi enviada; False se foi suprimida ou não pôde ser
        entregue. Nunca levanta — notificação é acessório, não pode derrubar o
        fluxo que a disparou.
    """
    if not advogado.whatsapp_numero:
        logger.info("notificador.advogado_sem_whatsapp", advogado_id=advogado.id)
        return False

    if not escritorio_instance:
        logger.warning(
            "notificador.instancia_nao_configurada",
            escritorio_id=advogado.escritorio_id,
        )
        return False

    if chave_trava and await _ja_avisado(redis, chave_trava, janela_segundos):
        logger.info("notificador.suprimido_por_trava", chave=chave_trava)
        return False

    if not (settings.EVOLUTION_API_URL and settings.EVOLUTION_API_KEY):
        logger.warning("notificador.evolution_nao_configurada")
        return False

    from feature_1_ia_personalizada.services.messaging.evolution_client import (
        EvolutionClient,
    )

    client = EvolutionClient(
        base_url=settings.EVOLUTION_API_URL,
        api_key=settings.EVOLUTION_API_KEY,
    )
    try:
        await client.enviar_texto(escritorio_instance, advogado.whatsapp_numero, texto)
        logger.info(
            "notificador.enviado",
            advogado_id=advogado.id,
            chars=len(texto),
            com_trava=bool(chave_trava),
        )
        return True
    except Exception as exc:
        logger.warning("notificador.falha_no_envio", advogado_id=advogado.id, erro=str(exc))
        return False
    finally:
        await client.close()


def chave_alerta_risco(cliente_id: int, nivel: str) -> str:
    """Trava do alerta de risco: um aviso por cliente **por nível**.

    Incluir o nível faz uma piora (em_risco → critico) furar a trava e alertar
    de novo, enquanto a permanência no mesmo nível fica silenciosa.
    """
    return _chave("risco", cliente_id, nivel)


def chave_agenda_diaria(advogado_id: int, dia: str) -> str:
    """Trava da agenda diária: uma mensagem por advogado por dia."""
    return _chave("agenda", advogado_id, dia)
