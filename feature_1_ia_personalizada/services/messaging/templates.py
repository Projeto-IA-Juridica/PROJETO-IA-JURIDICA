"""
feature_1_ia_personalizada/services/messaging/templates.py
===========================================================
Templates de mensagens formatáveis usando .format(**kwargs).

Uso em runtime:
    from feature_1_ia_personalizada.services.messaging.templates import carregar_templates
    tmpl = await carregar_templates(escritorio_id, redis_client, db)
    msg = tmpl["boas_vindas"].format(nome_cliente="João")
"""
from __future__ import annotations

# -----------------------------------------------------------
# BOAS-VINDAS
# -----------------------------------------------------------

TEMPLATE_BOAS_VINDAS = (
    "Olá! 👋 Eu sou o assistente virtual do escritório {escritorio}.\n\n"
    "📌 Posso ajudar com:\n"
    "• Status e andamento do seu processo\n"
    "• Explicação de termos jurídicos em linguagem simples\n"
    "• Informações sobre agendamentos\n\n"
    "⚖️ Aviso importante (OAB): não forneço parecer jurídico "
    "e não substituo seu advogado(a). Minhas respostas são informativas "
    "com base nos dados disponíveis.\n\n"
    "Como posso ajudar você hoje?"
)

# -----------------------------------------------------------
# PROCESSO
# -----------------------------------------------------------

TEMPLATE_NOVO_ANDAMENTO = "📄 Atualização no seu processo {numero}!\n\n{resumo_traduzido}"

TEMPLATE_SEM_MOVIMENTACAO = (
    "Olá! Sobre o processo {numero}, até o momento não identifiquei "
    "novas movimentações recentes.\n\n"
    "Se desejar, posso avisar assim que houver atualização."
)

TEMPLATE_CLIENTE_SEM_PROCESSO = (
    "Olá! Não encontrei processos vinculados ao seu cadastro. "
    "Entre em contato com o escritório para verificar."
)

TEMPLATE_CLIENTE_NAO_ENCONTRADO = (
    "Olá! Não encontrei seu cadastro com os dados disponíveis. "
    "Por favor, entre em contato com o escritório para atualização."
)

# -----------------------------------------------------------
# AGENDAMENTO
# -----------------------------------------------------------

TEMPLATE_AGENDAMENTO_CONFIRMADO = (
    "✅ Consulta confirmada!\n\n"
    "👩‍⚖️ Dr(a). {nome}\n"
    "📅 Data: {data}\n"
    "⏰ Horário: {horario}\n\n"
    "Se precisar reagendar, é só avisar."
)

# -----------------------------------------------------------
# PESQUISA / RELACIONAMENTO
# -----------------------------------------------------------

TEMPLATE_PESQUISA_NPS = (
    "Olá, {nome_cliente}! 😊\n\n"
    "Como avalia o atendimento do {nome_escritorio} até agora?\n"
    "Responda com um número de *1 a 5*:\n"
    "1 = Muito insatisfeito  |  5 = Muito satisfeito"
)

TEMPLATE_MENSAGEM_TRIMESTRAL = (
    "Olá, {nome}! 👋\n\n"
    "Faz {dias} dias desde nosso último contato. "
    "Se quiser uma atualização do seu processo, é só me chamar."
)

# -----------------------------------------------------------
# DATAS COMEMORATIVAS
# -----------------------------------------------------------

TEMPLATE_ANIVERSARIO = (
    "🎉 Feliz Aniversário, {nome}! A equipe do escritório {escritorio} deseja um excelente dia!"
)

TEMPLATE_DIA_BANCARIO = (
    "💼 Feliz Dia do Bancário! "
    "Atualizando: seu processo {numero} está com status: {status_processo}."
)

TEMPLATE_DIA_PROFESSOR = (
    "📚 Feliz Dia do Professor! A equipe do escritório {escritorio} deseja um ótimo dia!"
)

# -----------------------------------------------------------
# ERRO / FALLBACK
# -----------------------------------------------------------

TEMPLATE_ERRO_GENERICO = (
    "Desculpe, estou com uma dificuldade técnica no momento. "
    "Encaminhei sua mensagem para o escritório e retornaremos em breve."
)

# -----------------------------------------------------------
# DEFAULTS — usados como fallback quando escritório não customizou
# -----------------------------------------------------------

_DEFAULT_BOAS_VINDAS = TEMPLATE_BOAS_VINDAS
_DEFAULT_ATUALIZACAO = TEMPLATE_NOVO_ANDAMENTO
_DEFAULT_SEM_NOVIDADE = TEMPLATE_SEM_MOVIMENTACAO


# -----------------------------------------------------------
# carregar_templates — ponto de acesso unificado
# -----------------------------------------------------------


async def carregar_templates(
    escritorio_id: int,
    redis_client: "Any | None" = None,
    db: "Any | None" = None,
) -> dict[str, str]:
    """
    Retorna os templates ativos do escritório.

    Prioridade:
        1. Redis cache (TTL 1h)
        2. Banco de dados (campos template_* do Escritorio)
        3. Defaults globais do arquivo

    Args:
        escritorio_id: ID do escritório (tenant).
        redis_client:  Cliente Redis async (opcional — sem cache se None).
        db:            AsyncSession SQLAlchemy (opcional — sem DB lookup se None).

    Returns:
        dict com chaves: "boas_vindas", "atualizacao", "sem_novidade"
    """
    import json

    cache_key = f"escritorio_templates:{escritorio_id}"

    # 1. Tenta cache Redis
    if redis_client is not None:
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass  # Redis indisponível — segue

    # 2. Tenta banco de dados
    templates: dict[str, str] = {
        "boas_vindas": _DEFAULT_BOAS_VINDAS,
        "atualizacao": _DEFAULT_ATUALIZACAO,
        "sem_novidade": _DEFAULT_SEM_NOVIDADE,
    }

    if db is not None:
        try:
            from sqlalchemy import select
            from shared.models.escritorio import Escritorio

            result = await db.execute(
                select(
                    Escritorio.template_boas_vindas,
                    Escritorio.template_atualizacao,
                    Escritorio.template_sem_novidade,
                ).where(Escritorio.id == escritorio_id)
            )
            row = result.one_or_none()
            if row:
                if row.template_boas_vindas:
                    templates["boas_vindas"] = row.template_boas_vindas
                if row.template_atualizacao:
                    templates["atualizacao"] = row.template_atualizacao
                if row.template_sem_novidade:
                    templates["sem_novidade"] = row.template_sem_novidade
        except Exception:
            pass  # DB falhou — usa defaults

    # 3. Cacheia resultado no Redis por 1h
    if redis_client is not None:
        try:
            await redis_client.set(cache_key, json.dumps(templates), ex=3600)
        except Exception:
            pass

    return templates


# Anotação de tipo para evitar import circular
from typing import Any  # noqa: E402
