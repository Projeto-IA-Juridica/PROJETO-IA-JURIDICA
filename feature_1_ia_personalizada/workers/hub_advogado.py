# feature_1_ia_personalizada/workers/hub_advogado.py
"""
Task Celery — Hub do Advogado.

Processa mensagens enviadas pelo advogado via WhatsApp para o Hub,
classificando a intenção e despachando para o handler correto.

Fila dedicada: hub_advogado
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date
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
    SYSTEM_PROMPT_HUB_INSIGHT_CLIENTE,
    SYSTEM_PROMPT_HUB_PESQUISA_JURISPRUDENCIA,
    SYSTEM_PROMPT_HUB_RESUMO_PROCESSO,
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
            f"Advogado: {s.mensagem_advogado}\nHub: {s.resposta_hub}" for s in historico
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
    from datetime import datetime, timedelta

    from sqlalchemy import func

    from shared.models.interacao import Interacao
    from shared.models.processo import Processo

    hoje = datetime.now(UTC).date()
    amanha_7d = hoje + timedelta(days=7)

    # Atendimentos hoje
    stmt_atend = (
        select(func.count())
        .select_from(Interacao)
        .where(
            Interacao.escritorio_id == escritorio.id,
            func.date(Interacao.created_at) == hoje,
            Interacao.direcao == "saida",
        )
    )
    total_hoje = (await session.execute(stmt_atend)).scalar() or 0

    # Processos com prazo nos próximos 7 dias
    stmt_prazo = (
        select(func.count())
        .select_from(Processo)
        .where(
            Processo.escritorio_id == escritorio.id,
            Processo.monitoramento_ativo.is_(True),
            Processo.proximo_prazo.between(hoje, amanha_7d),
        )
    )
    processos_prazo = (await session.execute(stmt_prazo)).scalar() or 0

    return (
        f"📊 *Dashboard — {hoje.strftime('%d/%m/%Y')}*\n\n"
        f"💬 Atendimentos hoje: *{total_hoje}*\n"
        f"⏰ Processos com prazo em 7 dias: *{processos_prazo}*\n\n"
        f"_Hub do Advogado — {escritorio.nome}_"
    )


_MAX_CHARS_PETICAO = 15_000  # ~5 000 tokens — limite seguro para Claude Opus


async def _handler_analise_peticao(
    payload: dict[str, Any],
    message_id: str | None,
    usuario: Usuario,
    escritorio: Escritorio,
    session: Any,
    escalacao_client: EscalacaoClient,
) -> tuple[str, str, int, int, Decimal, int | None, int | None]:
    """Baixa PDF do WhatsApp, extrai texto e envia para Claude Opus analisar."""
    from feature_1_ia_personalizada.services.ai.escalation_client import TipoAnalise
    from feature_1_ia_personalizada.services.legal_data.data_cleaner import LegalDataCleaner
    from feature_1_ia_personalizada.services.rag.ingestion import _extrair_texto_pdf

    instance = escritorio.webhook_whatsapp_instance
    if not instance or not message_id:
        return (
            "⚠️ Não foi possível acessar o documento. Tente reenviar o PDF.",
            "claude_opus_fallback",
            0,
            0,
            Decimal("0"),
            None,
            None,
        )

    # Confirmação imediata — análise pode levar até 60s
    await _enviar_whatsapp(
        escritorio,
        usuario,
        "📄 Recebi a petição. Analisando com Claude Opus... aguarde até 60 segundos.",
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
            0,
            0,
            Decimal("0"),
            None,
            None,
        )
    finally:
        await evo.close()

    # Extrair texto do PDF
    try:
        texto_bruto = _extrair_texto_pdf(conteudo_bytes)
    except Exception as exc:
        logger.warning("hub_analise_extracao_falhou", erro=str(exc))
        return (
            "⚠️ Não foi possível extrair o texto do PDF. Verifique se não está protegido.",
            "claude_opus_fallback",
            0,
            0,
            Decimal("0"),
            None,
            None,
        )

    texto = LegalDataCleaner.normalizar_espacos(texto_bruto or "")

    if len(texto.strip()) < 50:
        return (
            "⚠️ O documento parece estar vazio ou apenas com imagens (OCR não suportado).",
            "claude_opus_fallback",
            0,
            0,
            Decimal("0"),
            None,
            None,
        )

    truncado = len(texto) > _MAX_CHARS_PETICAO
    conteudo_envio = texto[:_MAX_CHARS_PETICAO]

    try:
        analise = await asyncio.wait_for(
            escalacao_client.analisar_peca(
                conteudo_peca=conteudo_envio,
                tipo_analise=TipoAnalise.ANALISE_COMPLETA,
                contexto_processo="Análise solicitada pelo advogado via WhatsApp.",
            ),
            timeout=60.0,
        )
    except (EscalacaoIndisponivelError, TimeoutError) as exc:
        logger.warning("hub_analise_escalacao_falhou", erro=str(exc))
        return (
            "⚠️ Análise indisponível no momento. Tente novamente em instantes.",
            "claude_opus_fallback",
            0,
            0,
            Decimal("0"),
            None,
            None,
        )

    # Formatar resposta em markdown WhatsApp
    def _lista(itens: list[str]) -> str:
        return "\n".join(f"• {i}" for i in itens) if itens else "• —"

    aviso_truncamento = (
        "\n\n_⚠️ Documento extenso — análise baseada nos primeiros 15 000 caracteres._"
        if truncado
        else ""
    )

    resposta = (
        f"*📋 ANÁLISE DE PEÇA JURÍDICA*\n\n"
        f"*IDENTIFICAÇÃO*\n{analise.tipo_peca}\n\n"
        f"*PONTOS FORTES*\n{_lista(analise.pontos_fortes)}\n\n"
        f"*VULNERABILIDADES*\n{_lista(analise.vulnerabilidades)}\n\n"
        f"*ARGUMENTOS AUSENTES*\n{_lista(analise.argumentos_ausentes)}\n\n"
        f"*JURISPRUDÊNCIA RELEVANTE*\n{_lista(analise.precedentes_relevantes)}\n\n"
        f"*SUGESTÕES*\n{_lista(analise.sugestoes)}\n\n"
        f"*AVALIAÇÃO GERAL: {analise.score_geral}/100*"
        f"{aviso_truncamento}"
    )

    # Tokens são rastreados internamente pelo EscalacaoClient; retornamos 0 pois
    # analisar_peca() não expõe contagem — será corrigido em refactor futuro.
    return (resposta, "claude_opus", 0, 0, Decimal("0"), None, None)


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
            0,
            0,
            Decimal("0"),
            None,
            None,
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
        stmt = (
            select(Cliente)
            .where(
                Cliente.escritorio_id == escritorio.id,
                Cliente.nome.ilike(f"%{classificacao.cliente_nome}%"),
            )
            .limit(1)
        )
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
            0,
            0,
            Decimal("0"),
            cliente_id,
            None,
        )


async def _handler_resumo_processo(
    mensagem: str,
    classificacao: ClassificacaoAdvogado,
    usuario: Usuario,
    escritorio: Escritorio,
    session: Any,
    escalacao_client: EscalacaoClient,
) -> tuple[str, str, int, int, Decimal, int | None, int | None]:
    """
    Busca dados completos do processo e gera briefing executivo com Claude Opus.

    Lookup: CNJ do classificador (prioridade) → nome do cliente → processo mais recente.
    Contexto: todos os campos disponíveis no banco + CRM score via CRMDataAggregator.
    """
    from feature_1_ia_personalizada.services.crm.aggregator import CRMDataAggregator
    from shared.models.cliente import Cliente
    from shared.models.processo import Processo

    processo = None
    cliente_id_ref: int | None = None
    processo_id: int | None = None

    # 1. Buscar por CNJ (prioridade)
    if classificacao.processo_cnj:
        stmt = (
            select(Processo)
            .where(
                Processo.escritorio_id == escritorio.id,
                Processo.numero_cnj == classificacao.processo_cnj,
            )
            .limit(1)
        )
        processo = (await session.execute(stmt)).scalars().first()

    # 2. Fallback: buscar pelo nome do cliente → processo ativo mais recente
    if processo is None and classificacao.cliente_nome:
        stmt_cli = (
            select(Cliente)
            .where(
                Cliente.escritorio_id == escritorio.id,
                Cliente.nome.ilike(f"%{classificacao.cliente_nome}%"),
            )
            .limit(1)
        )
        cliente_encontrado = (await session.execute(stmt_cli)).scalars().first()
        if cliente_encontrado:
            stmt_proc = (
                select(Processo)
                .where(
                    Processo.escritorio_id == escritorio.id,
                    Processo.cliente_id == cliente_encontrado.id,
                    Processo.status == "ativo",
                )
                .order_by(Processo.data_ultimo_andamento.desc().nullslast())
                .limit(1)
            )
            processo = (await session.execute(stmt_proc)).scalars().first()

    if processo is None:
        return (
            "⚠️ Processo não encontrado. Informe o número CNJ completo (ex: 0001234-55.2024.8.26.0001) "
            "ou o nome exato do cliente.",
            "claude_opus_fallback",
            0,
            0,
            Decimal("0"),
            None,
            None,
        )

    processo_id = processo.id

    # 3. Buscar cliente vinculado ao processo
    cliente = await session.get(Cliente, processo.cliente_id)
    nome_cliente = cliente.nome if cliente else "N/D"
    if cliente:
        cliente_id_ref = cliente.id

    # 4. Coletar contexto CRM
    contexto_crm = f"Cliente: {nome_cliente} — dados CRM não disponíveis."
    if cliente:
        try:
            aggregator = CRMDataAggregator(session)
            ctx = await aggregator.coletar_contexto_cliente(cliente.id, escritorio.id)
            crm_score = ctx.crm_score_anterior or "N/D"
            ultima_acao = ctx.crm_acao_sugerida_anterior or "Nenhuma registrada"
            contexto_crm = (
                f"Cliente: {nome_cliente}\n"
                f"CRM Score: {crm_score}/100\n"
                f"Interações (últimos 30d): {ctx.total_interacoes_30d}\n"
                f"NPS médio (3m): {ctx.nps_medio_3m or 'N/D'}\n"
                f"Último contato: há {ctx.dias_desde_ultimo_contato} dias\n"
                f"Última ação CRM sugerida: {ultima_acao}"
            )
        except Exception as exc:
            logger.warning("hub_resumo_crm_falhou", erro=str(exc), processo_id=processo_id)

    # 5. Extrair andamentos e próximo passo do estado_atual (JSONB)
    andamentos_recentes = "Nenhum andamento registrado."
    proximo_passo = "N/D"
    if isinstance(processo.estado_atual, dict):
        ultimos = processo.estado_atual.get("ultimos_andamentos", [])
        if ultimos:
            andamentos_recentes = "\n".join(
                f"• {a}" if isinstance(a, str) else f"• {a.get('descricao', str(a))}"
                for a in ultimos[:5]
            )
        proximo_passo = processo.estado_atual.get("proximo_passo_esperado", "N/D")

    # 6. Montar bloco de dados do processo
    data_ult = (
        processo.data_ultimo_andamento.strftime("%d/%m/%Y")
        if processo.data_ultimo_andamento
        else "N/D"
    )
    valor_causa = f"R$ {processo.valor_causa:,.2f}" if processo.valor_causa else "N/D"
    score_interpretacao = (
        f"\nInterpretação do score: {processo.score_interpretacao}"
        if processo.score_interpretacao
        else ""
    )
    dados_processo = (
        f"CNJ: {processo.numero_cnj}\n"
        f"Tribunal: {processo.tribunal or 'N/D'} | Vara: {processo.vara or 'N/D'}\n"
        f"Tipo de ação: {processo.tipo_acao or 'N/D'}\n"
        f"Polo do cliente ({nome_cliente}): {processo.polo_cliente}\n"
        f"Fase processual: {processo.fase_processual or 'N/D'}\n"
        f"Status: {processo.status}\n"
        f"Valor da causa: {valor_causa}\n"
        f"Último andamento ({data_ult}): {processo.ultimo_andamento or 'Nenhum registrado'}\n"
        f"Próximo passo esperado: {proximo_passo}\n"
        f"Score de risco: {processo.score_risco or 'N/D'}/100 — nível: {processo.score_nivel or 'N/D'}"
        f"{score_interpretacao}"
    )

    system_prompt = SYSTEM_PROMPT_HUB_RESUMO_PROCESSO.format(
        nome_usuario=usuario.nome,
        dados_processo=dados_processo,
        contexto_crm=contexto_crm,
        data_hoje=_hoje(),
    )

    mensagem_usuario = (
        f"{mensagem}\n\n" f"<andamentos_recentes>\n{andamentos_recentes}\n</andamentos_recentes>"
    ).strip()

    try:
        resultado = await asyncio.wait_for(
            escalacao_client.gerar_resposta(
                system_prompt=system_prompt,
                mensagem_usuario=mensagem_usuario,
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
            cliente_id_ref,
            processo_id,
        )
    except (EscalacaoIndisponivelError, TimeoutError) as exc:
        logger.warning("hub_resumo_escalacao_falhou", erro=str(exc))
        return (
            "⚠️ Resumo indisponível no momento. Tente novamente.",
            "claude_opus_fallback",
            0,
            0,
            Decimal("0"),
            cliente_id_ref,
            processo_id,
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
            0,
            0,
            Decimal("0"),
            None,
            None,
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
        caption = msg.get("documentMessage", {}).get("caption") or msg.get(
            "documentWithCaptionMessage", {}
        ).get("message", {}).get("documentMessage", {}).get("caption", "")
        return caption or "", "document", message_id

    # Texto simples
    texto = msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or ""
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
