# feature_1_ia_personalizada/workers/hub_advogado.py
"""
Task Celery — Hub do Advogado.

Processa mensagens enviadas pelo advogado via WhatsApp para o Hub,
classificando a intenção e despachando para o handler correto.

Fila dedicada: hub_advogado
"""

from __future__ import annotations

import asyncio
from datetime import date, timezone
from decimal import Decimal
from typing import Any

import structlog
from celery import shared_task
from sqlalchemy import select

from feature_1_ia_personalizada.services.ai.escalation_client import (
    EscalacaoClient,
    EscalacaoIndisponivelError,
)
from feature_1_ia_personalizada.services.ai.hub_advogado_classifier import (
    ClassificacaoAdvogado,
    HubAdvogadoClassificador,
    IntencaoAdvogado,
)
from feature_1_ia_personalizada.services.ai.prompts import (
    SYSTEM_PROMPT_HUB_ADVOGADO_BASE,
    SYSTEM_PROMPT_HUB_ANALISE_PETICAO,
    SYSTEM_PROMPT_HUB_INSIGHT_CLIENTE,
    SYSTEM_PROMPT_HUB_PESQUISA_JURISPRUDENCIA,
)
from feature_1_ia_personalizada.services.messaging.evolution_client import EvolutionClient
from feature_1_ia_personalizada.services.messaging.whatsapp import (
    SQLWhatsAppRepository,
    WhatsAppService,
)
from feature_1_ia_personalizada.workers.celery_app import DLQTask
from shared.config.settings import settings
from shared.models.escritorio import Escritorio
from shared.models.sessao_advogado import SessaoAdvogado
from shared.models.usuario import Usuario

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_whatsapp_service() -> WhatsAppService:
    client = EvolutionClient(settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY)
    repo = SQLWhatsAppRepository()
    return WhatsAppService(evolution_client=client, repositorio=repo)


def _hoje() -> str:
    return date.today().strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# Task principal
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="processar_mensagem_advogado",
    base=DLQTask,
    queue="hub_advogado",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    soft_time_limit=120,
    time_limit=150,
)
def processar_mensagem_advogado(self, payload: dict[str, Any], usuario_id: int) -> dict:
    """
    Processa uma mensagem do advogado no Hub.

    Fluxo:
      1. Valida usuário (ativo + role advogado/admin)
      2. Verifica feature flag do escritório
      3. Classifica intenção
      4. Despacha para handler
      5. Formata e envia resposta via WhatsApp
      6. Salva SessaoAdvogado
    """
    asyncio.run(_processar(payload, usuario_id))
    return {"status": "ok"}


async def _processar(payload: dict[str, Any], usuario_id: int) -> None:
    from shared.database.connection import async_session_factory

    log = logger.bind(usuario_id=usuario_id)

    async with async_session_factory() as session:
        # 1. Buscar e validar usuário
        usuario = await session.get(Usuario, usuario_id)
        if not usuario or not usuario.ativo or usuario.role not in ("advogado", "admin"):
            log.warning("hub_usuario_invalido")
            return

        escritorio = await session.get(Escritorio, usuario.escritorio_id)
        if not escritorio:
            log.warning("hub_escritorio_nao_encontrado")
            return

        # 2. Verificar feature flag
        if not escritorio.escalacao_habilitada:
            await _enviar_whatsapp(
                escritorio,
                usuario,
                "⚠️ O Hub do Advogado não está ativo para este escritório.",
            )
            return

        # 3. Extrair texto e tipo de mídia do payload
        mensagem, tipo_media, message_id = _extrair_conteudo(payload)

        log.info("hub_mensagem_recebida", intencao_pendente=True, tipo=tipo_media)

        # 4. Classificar intenção
        classificador = HubAdvogadoClassificador()
        classificacao = await classificador.classificar(mensagem, tipo_media)

        log.info("hub_intencao_classificada", intencao=classificacao.intencao.value)

        # 5. Despachar para handler — EscalacaoClient instanciado uma vez aqui
        escalacao_client = EscalacaoClient()
        resposta, modelo_ia, tokens_in, tokens_out, custo, ref_cliente_id, ref_processo_id = (
            await _despachar(
                classificacao=classificacao,
                mensagem=mensagem,
                tipo_media=tipo_media,
                message_id=message_id,
                usuario=usuario,
                escritorio=escritorio,
                payload=payload,
                session=session,
                escalacao_client=escalacao_client,
            )
        )

        # 6. Enviar resposta via WhatsApp
        await _enviar_whatsapp(escritorio, usuario, resposta)

        # 7. Salvar sessão
        custo_decimal = Decimal(str(custo)) if not isinstance(custo, Decimal) else custo
        sessao = SessaoAdvogado(
            escritorio_id=escritorio.id,
            usuario_id=usuario_id,
            mensagem_advogado=mensagem or f"[{tipo_media}]",
            resposta_hub=resposta,
            intencao=classificacao.intencao.value,
            modelo_ia=modelo_ia,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            custo_estimado=custo_decimal,
            cliente_referenciado_id=ref_cliente_id,
            processo_referenciado_id=ref_processo_id,
            metadata_json={"entidades": classificacao.entidades},
        )
        session.add(sessao)

        # Incrementar consumo de tokens de escalação do escritório
        if tokens_in + tokens_out > 0:
            escritorio.escalacao_tokens_usados_mes = (
                escritorio.escalacao_tokens_usados_mes + tokens_in + tokens_out
            )

        await session.commit()

        log.info(
            "hub_sessao_salva",
            intencao=classificacao.intencao.value,
            modelo_ia=modelo_ia,
            tokens=tokens_in + tokens_out,
        )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


async def _despachar(
    classificacao: ClassificacaoAdvogado,
    mensagem: str,
    tipo_media: str,
    message_id: str | None,
    usuario: Usuario,
    escritorio: Escritorio,
    payload: dict[str, Any],
    session: Any,
    escalacao_client: EscalacaoClient,
) -> tuple[str, str, int, int, Decimal, int | None, int | None]:
    """
    Retorna: (resposta, modelo_ia, tokens_in, tokens_out, custo, cliente_id, processo_id)
    """
    intencao = classificacao.intencao

    if intencao == IntencaoAdvogado.STATUS_ESCRITORIO:
        resposta = await _handler_status_escritorio(usuario, escritorio, session)
        return resposta, "claude", 0, 0, Decimal("0"), None, None

    if intencao == IntencaoAdvogado.ANALISE_PETICAO:
        return await _handler_analise_peticao(
            payload, message_id, usuario, escritorio, session, escalacao_client
        )

    if intencao == IntencaoAdvogado.INSIGHT_CLIENTE:
        return await _handler_insight_cliente(
            mensagem, classificacao, usuario, escritorio, session, escalacao_client
        )

    if intencao == IntencaoAdvogado.PESQUISA_JURISPRUDENCIA:
        return await _handler_pesquisa_jurisprudencia(
            mensagem, classificacao, usuario, escritorio, escalacao_client
        )

    if intencao == IntencaoAdvogado.RESUMO_PROCESSO:
        return await _handler_resumo_processo(
            mensagem, classificacao, usuario, escritorio, session, escalacao_client
        )

    if intencao == IntencaoAdvogado.RASCUNHO_MENSAGEM:
        return await _handler_rascunho_mensagem(
            mensagem, classificacao, usuario, escritorio, session, escalacao_client
        )

    # Default: duvida_juridica
    return await _handler_duvida_juridica(mensagem, usuario, escritorio, session, escalacao_client)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _handler_duvida_juridica(
    mensagem: str,
    usuario: Usuario,
    escritorio: Escritorio,
    session: Any,
    escalacao_client: EscalacaoClient,
) -> tuple[str, str, int, int, Decimal, int | None, int | None]:
    """Responde dúvida jurídica geral usando Claude Opus."""
    system_prompt = SYSTEM_PROMPT_HUB_ADVOGADO_BASE.format(
        nome_usuario=usuario.nome,
        nome_escritorio=escritorio.nome,
        data_hoje=_hoje(),
    )

    # Contexto conversacional: últimas 5 sessões do advogado
    historico = await _buscar_historico_advogado(session, usuario.id, limite=5)
    contexto_historico = ""
    if historico:
        linhas = "\n".join(
            f"Advogado: {s.mensagem_advogado}\nHub: {s.resposta_hub}"
            for s in historico
        )
        contexto_historico = f"\n\n<historico_recente>\n{linhas}\n</historico_recente>"

    system_prompt += contexto_historico

    try:
        resultado = await asyncio.wait_for(
            escalacao_client.gerar_resposta(
                system_prompt=system_prompt,
                mensagem_usuario=mensagem,
                escritorio_id=escritorio.id,
            ),
            timeout=50.0,
        )
        return (
            resultado.conteudo,
            "claude_opus",
            resultado.tokens_input,
            resultado.tokens_output,
            resultado.custo_estimado,
            None,
            None,
        )
    except (EscalacaoIndisponivelError, TimeoutError) as exc:
        logger.warning("hub_escalacao_indisponivel_fallback", erro=str(exc))
        resposta_fallback = (
            "⚠️ _Modelo de escalação temporariamente indisponível._\n\n"
            "Sua dúvida foi registrada. Tente novamente em instantes."
        )
        return resposta_fallback, "claude_opus_fallback", 0, 0, Decimal("0"), None, None


async def _handler_status_escritorio(
    usuario: Usuario,
    escritorio: Escritorio,
    session: Any,
) -> str:
    """Gera dashboard textual sem chamar IA — dados estruturados do banco."""
    from sqlalchemy import func
    from datetime import datetime, timedelta

    from shared.models.interacao import Interacao
    from shared.models.processo import Processo

    hoje = datetime.now(timezone.utc).date()
    amanha_7d = hoje + timedelta(days=7)

    # Atendimentos hoje
    stmt_atend = select(func.count()).select_from(Interacao).where(
        Interacao.escritorio_id == escritorio.id,
        func.date(Interacao.created_at) == hoje,
        Interacao.direcao == "saida",
    )
    total_hoje = (await session.execute(stmt_atend)).scalar() or 0

    # Processos com prazo nos próximos 7 dias
    stmt_prazo = select(func.count()).select_from(Processo).where(
        Processo.escritorio_id == escritorio.id,
        Processo.monitoramento_ativo.is_(True),
        Processo.proximo_prazo.between(hoje, amanha_7d),
    )
    processos_prazo = (await session.execute(stmt_prazo)).scalar() or 0

    return (
        f"📊 *Dashboard — {hoje.strftime('%d/%m/%Y')}*\n\n"
        f"💬 Atendimentos hoje: *{total_hoje}*\n"
        f"⏰ Processos com prazo em 7 dias: *{processos_prazo}*\n\n"
        f"_Hub do Advogado — {escritorio.nome}_"
    )


async def _handler_analise_peticao(
    payload: dict[str, Any],
    message_id: str | None,
    usuario: Usuario,
    escritorio: Escritorio,
    session: Any,
    escalacao_client: EscalacaoClient,
) -> tuple[str, str, int, int, Decimal, int | None, int | None]:
    """Baixa PDF do WhatsApp, extrai texto e envia para Claude Opus analisar."""
    instance = escritorio.webhook_whatsapp_instance
    if not instance or not message_id:
        return (
            "⚠️ Não foi possível acessar o documento. Tente reenviar o PDF.",
            "claude_opus_fallback",
            0, 0, Decimal("0"), None, None,
        )

    # Baixar PDF via Evolution API
    evo = EvolutionClient(settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY)
    try:
        conteudo_bytes = await evo.baixar_media(instance, message_id)
    except Exception as exc:
        logger.warning("hub_analise_download_falhou", erro=str(exc))
        return (
            "⚠️ Falha ao baixar o documento. Tente reenviar.",
            "claude_opus_fallback",
            0, 0, Decimal("0"), None, None,
        )
    finally:
        await evo.close()

    # Extrair texto do PDF
    try:
        from feature_1_ia_personalizada.services.rag.ingestion import DocumentoIngester
        texto = DocumentoIngester._extrair_texto_pdf(conteudo_bytes)
    except Exception as exc:
        logger.warning("hub_analise_extracao_falhou", erro=str(exc))
        return (
            "⚠️ Não foi possível extrair o texto do PDF. Verifique se não está protegido.",
            "claude_opus_fallback",
            0, 0, Decimal("0"), None, None,
        )

    if not texto or len(texto.strip()) < 50:
        return (
            "⚠️ O documento parece estar vazio ou apenas com imagens (OCR não suportado).",
            "claude_opus_fallback",
            0, 0, Decimal("0"), None, None,
        )

    system_prompt = SYSTEM_PROMPT_HUB_ANALISE_PETICAO.format(data_hoje=_hoje())

    try:
        resultado = await asyncio.wait_for(
            escalacao_client.gerar_resposta(
                system_prompt=system_prompt,
                mensagem_usuario=f"Analise a seguinte peça jurídica:\n\n{texto[:8000]}",
                escritorio_id=escritorio.id,
            ),
            timeout=60.0,
        )
        return (
            resultado.conteudo,
            "claude_opus",
            resultado.tokens_input,
            resultado.tokens_output,
            resultado.custo_estimado,
            None,
            None,
        )
    except (EscalacaoIndisponivelError, TimeoutError) as exc:
        logger.warning("hub_analise_escalacao_falhou", erro=str(exc))
        return (
            "⚠️ Análise indisponível no momento. Tente novamente.",
            "claude_opus_fallback",
            0, 0, Decimal("0"), None, None,
        )


async def _handler_pesquisa_jurisprudencia(
    mensagem: str,
    classificacao: ClassificacaoAdvogado,
    usuario: Usuario,
    escritorio: Escritorio,
    escalacao_client: EscalacaoClient,
) -> tuple[str, str, int, int, Decimal, int | None, int | None]:
    """Pesquisa jurisprudência usando Claude Opus."""
    query = classificacao.query_juris or mensagem
    system_prompt = SYSTEM_PROMPT_HUB_PESQUISA_JURISPRUDENCIA.format(
        query=query,
        tribunais="STJ, STF, TJs estaduais",
        periodo="últimos 5 anos",
    )

    try:
        resultado = await asyncio.wait_for(
            escalacao_client.gerar_resposta(
                system_prompt=system_prompt,
                mensagem_usuario=f"Pesquise jurisprudência sobre: {query}",
                escritorio_id=escritorio.id,
            ),
            timeout=50.0,
        )
        return (
            resultado.conteudo,
            "claude_opus",
            resultado.tokens_input,
            resultado.tokens_output,
            resultado.custo_estimado,
            None,
            None,
        )
    except (EscalacaoIndisponivelError, TimeoutError) as exc:
        logger.warning("hub_juris_escalacao_falhou", erro=str(exc))
        return (
            "⚠️ Pesquisa de jurisprudência indisponível. Tente novamente.",
            "claude_opus_fallback",
            0, 0, Decimal("0"), None, None,
        )


async def _handler_insight_cliente(
    mensagem: str,
    classificacao: ClassificacaoAdvogado,
    usuario: Usuario,
    escritorio: Escritorio,
    session: Any,
    escalacao_client: EscalacaoClient,
) -> tuple[str, str, int, int, Decimal, int | None, int | None]:
    """Gera insight CRM sobre um cliente usando Claude Opus + CRMDataAggregator."""
    from feature_1_ia_personalizada.services.crm.aggregator import CRMDataAggregator
    from shared.models.cliente import Cliente

    cliente_id: int | None = None
    nome_cliente = classificacao.cliente_nome or "cliente mencionado"
    crm_score = "N/D"
    resumo_interacoes = "Sem histórico disponível"
    resumo_processos = "Sem processos cadastrados"
    ultima_acao = "Nenhuma"

    # Tentar encontrar cliente pelo nome e coletar contexto CRM real
    if classificacao.cliente_nome:
        stmt = select(Cliente).where(
            Cliente.escritorio_id == escritorio.id,
            Cliente.nome.ilike(f"%{classificacao.cliente_nome}%"),
        ).limit(1)
        cliente = (await session.execute(stmt)).scalars().first()
        if cliente:
            cliente_id = cliente.id
            nome_cliente = cliente.nome
            try:
                aggregator = CRMDataAggregator(session)
                ctx = await aggregator.coletar_contexto_cliente(cliente_id, escritorio.id)
                crm_score = str(ctx.crm_score_anterior or "N/D")
                ultima_acao = ctx.crm_acao_sugerida_anterior or "Nenhuma"
                # Resumo de interações
                resumo_interacoes = (
                    f"{ctx.total_interacoes_30d} interações nos últimos 30 dias; "
                    f"NPS médio 3m: {ctx.nps_medio_3m or 'N/D'}; "
                    f"último contato há {ctx.dias_desde_ultimo_contato} dias"
                )
                # Resumo de processos
                if ctx.processos_ativos:
                    resumo_processos = "; ".join(
                        f"{p.numero_cnj} ({p.tipo_acao}, {p.fase_processual})"
                        for p in ctx.processos_ativos[:3]
                    )
            except Exception as exc:
                logger.warning("hub_insight_crm_falhou", erro=str(exc), cliente_id=cliente_id)

    system_prompt = SYSTEM_PROMPT_HUB_INSIGHT_CLIENTE.format(
        nome_cliente=nome_cliente,
        crm_score=crm_score,
        resumo_interacoes=resumo_interacoes,
        resumo_processos=resumo_processos,
        ultima_acao_crm=ultima_acao,
    )

    try:
        resultado = await asyncio.wait_for(
            escalacao_client.gerar_resposta(
                system_prompt=system_prompt,
                mensagem_usuario=mensagem,
                escritorio_id=escritorio.id,
            ),
            timeout=50.0,
        )
        return (
            resultado.conteudo,
            "claude_opus",
            resultado.tokens_input,
            resultado.tokens_output,
            resultado.custo_estimado,
            cliente_id,
            None,
        )
    except (EscalacaoIndisponivelError, TimeoutError) as exc:
        logger.warning("hub_insight_escalacao_falhou", erro=str(exc))
        return (
            "⚠️ Insight indisponível no momento. Tente novamente.",
            "claude_opus_fallback",
            0, 0, Decimal("0"), cliente_id, None,
        )


async def _handler_resumo_processo(
    mensagem: str,
    classificacao: ClassificacaoAdvogado,
    usuario: Usuario,
    escritorio: Escritorio,
    session: Any,
    escalacao_client: EscalacaoClient,
) -> tuple[str, str, int, int, Decimal, int | None, int | None]:
    """Busca dados do processo e gera resumo com Claude Opus."""
    from shared.models.processo import Processo

    processo_id: int | None = None
    contexto_processo = ""

    # Tentar localizar processo pelo CNJ mencionado
    if classificacao.processo_cnj:
        stmt = select(Processo).where(
            Processo.escritorio_id == escritorio.id,
            Processo.numero_cnj == classificacao.processo_cnj,
        ).limit(1)
        processo = (await session.execute(stmt)).scalars().first()
        if processo:
            processo_id = processo.id
            contexto_processo = (
                f"Processo: {processo.numero_cnj}\n"
                f"Tribunal: {processo.tribunal or 'N/D'}\n"
                f"Último andamento: {processo.ultimo_andamento or 'N/D'}\n"
            )

    system_prompt = SYSTEM_PROMPT_HUB_ADVOGADO_BASE.format(
        nome_usuario=usuario.nome,
        nome_escritorio=escritorio.nome,
        data_hoje=_hoje(),
    )

    try:
        resultado = await asyncio.wait_for(
            escalacao_client.gerar_resposta(
                system_prompt=system_prompt,
                mensagem_usuario=f"{mensagem}\n\n{contexto_processo}".strip(),
                escritorio_id=escritorio.id,
            ),
            timeout=50.0,
        )
        return (
            resultado.conteudo,
            "claude_opus",
            resultado.tokens_input,
            resultado.tokens_output,
            resultado.custo_estimado,
            None,
            processo_id,
        )
    except (EscalacaoIndisponivelError, TimeoutError) as exc:
        logger.warning("hub_resumo_escalacao_falhou", erro=str(exc))
        return (
            "⚠️ Resumo indisponível no momento. Tente novamente.",
            "claude_opus_fallback",
            0, 0, Decimal("0"), None, processo_id,
        )


async def _handler_rascunho_mensagem(
    mensagem: str,
    classificacao: ClassificacaoAdvogado,
    usuario: Usuario,
    escritorio: Escritorio,
    session: Any,
    escalacao_client: EscalacaoClient,
) -> tuple[str, str, int, int, Decimal, int | None, int | None]:
    """Gera rascunho de mensagem para o advogado enviar ao cliente."""
    system_prompt = (
        f"Você é um assistente do advogado Dr(a). {usuario.nome} "
        f"do escritório {escritorio.nome}.\n\n"
        "Gere um rascunho de mensagem profissional e empática para enviar ao cliente. "
        "A mensagem deve ser em português, adequada para WhatsApp, "
        "sem termos jurídicos excessivos. "
        "Prefixe o rascunho com '*RASCUNHO — revisar antes de enviar:*'"
    )

    try:
        resultado = await asyncio.wait_for(
            escalacao_client.gerar_resposta(
                system_prompt=system_prompt,
                mensagem_usuario=mensagem,
                escritorio_id=escritorio.id,
            ),
            timeout=50.0,
        )
        return (
            resultado.conteudo,
            "claude_opus",
            resultado.tokens_input,
            resultado.tokens_output,
            resultado.custo_estimado,
            None,
            None,
        )
    except (EscalacaoIndisponivelError, TimeoutError) as exc:
        logger.warning("hub_rascunho_escalacao_falhou", erro=str(exc))
        return (
            "⚠️ Geração de rascunho indisponível. Tente novamente.",
            "claude_opus_fallback",
            0, 0, Decimal("0"), None, None,
        )


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _extrair_conteudo(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    """
    Extrai (texto, tipo_media, message_id) do payload Evolution API.
    Retorna tipo_media: "texto" | "document" | "audio_transcrito" | "image"
    """
    data = payload.get("data", {})
    msg = data.get("message", {})
    message_id: str | None = data.get("key", {}).get("id")

    # Documento PDF
    if "documentMessage" in msg or "documentWithCaptionMessage" in msg:
        caption = (
            msg.get("documentMessage", {}).get("caption")
            or msg.get("documentWithCaptionMessage", {})
            .get("message", {})
            .get("documentMessage", {})
            .get("caption", "")
        )
        return caption or "", "document", message_id

    # Texto simples
    texto = (
        msg.get("conversation")
        or msg.get("extendedTextMessage", {}).get("text")
        or ""
    )
    return texto, "texto", message_id


async def _enviar_whatsapp(
    escritorio: Escritorio,
    usuario: Usuario,
    resposta: str,
) -> None:
    """Envia resposta ao número WhatsApp do advogado."""
    numero = getattr(usuario, "whatsapp_numero", None)
    instance = getattr(escritorio, "webhook_whatsapp_instance", None)
    if not numero or not instance:
        logger.warning("hub_envio_sem_numero", usuario_id=usuario.id)
        return
    evo = EvolutionClient(settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY)
    try:
        await evo.enviar_texto(instance, numero, resposta)
    except Exception as exc:
        logger.warning("hub_envio_whatsapp_falhou", erro=str(exc))
    finally:
        await evo.close()


async def _buscar_historico_advogado(
    session: Any,
    usuario_id: int,
    limite: int = 5,
) -> list[SessaoAdvogado]:
    """Busca as últimas N sessões do advogado para contexto conversacional."""
    stmt = (
        select(SessaoAdvogado)
        .where(SessaoAdvogado.usuario_id == usuario_id)
        .order_by(SessaoAdvogado.created_at.desc())
        .limit(limite)
    )
    resultado = await session.execute(stmt)
    # Retorna em ordem cronológica (mais antiga primeiro)
    return list(reversed(resultado.scalars().all()))
