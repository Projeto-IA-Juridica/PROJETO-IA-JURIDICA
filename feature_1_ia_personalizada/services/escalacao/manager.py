from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
from feature_1_ia_personalizada.services.messaging.evolution_client import EvolutionClient
from shared.models.interacao import Interacao
from shared.models.usuario import Usuario

logger = structlog.get_logger(__name__)


class EscalacaoManager:
    """
    Gerencia o ciclo de vida de uma escalação (Human-in-the-Loop), notificando advogados
    para revisar e aprovar respostas geradas pela IA.
    """

    def __init__(
        self,
        claude_client: ClaudeClient,
        evolution_client: EvolutionClient,
        session_factory: async_sessionmaker[AsyncSession],
    ):
        self._claude = claude_client
        self._evolution = evolution_client
        self._session_factory = session_factory

    async def avaliar_e_notificar_advogados(
        self,
        escritorio_id: int,
        cliente_id: int,
        mensagem_cliente: str,
        motivo: str,
        historico_recente: list[dict[str, str]],
        instancia_whatsapp: str,
    ) -> dict[str, Any]:
        """
        Recebe a mensagem que causou a escalação, gera sugestão de resposta,
        salva na tabela de interações como "pendente" e dispara WhatsApp para advogados.
        """
        log = logger.bind(
            escritorio_id=escritorio_id,
            cliente_id=cliente_id,
            motivo=motivo,
        )

        async with self._session_factory() as session:
            # Busca advogados legíveis
            stmt = select(Usuario).where(
                Usuario.escritorio_id == escritorio_id,
                Usuario.escalacao_ativa.is_(True),
                Usuario.whatsapp_numero.isnot(None),
                Usuario.ativo.is_(True),
            )
            advogados = (await session.execute(stmt)).scalars().all()

            if not advogados:
                log.warning("nenhum_advogado_configurado_para_escalacao")
                return {"enviado": False, "erro": "nenhum_advogado_configurado"}

            # Pede pro Claude gerar uma sugestão baseada no histórico
            sugestao_dados = await self._gerar_sugestao_resposta(
                mensagem_cliente, historico_recente
            )
            sugestao = sugestao_dados["resposta"]

            # Cria a interação "pendente de aprovação"
            metadata = {
                "escalacao": {
                    "status": "pendente",
                    "motivo": motivo,
                    "ts_criacao": datetime.now(UTC).isoformat(),
                    "advogados_notificados": [adv.id for adv in advogados],
                    "sugestao_resposta": sugestao,
                }
            }

            interacao_escalacao = Interacao(
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                processo_id=None,  # Poderíamos extrair do context do LLM se necessário
                tipo="escalacao",
                direcao="saida",
                mensagem_cliente=mensagem_cliente,
                mensagem_ia=sugestao,
                metadata_json=metadata,
                tokens_input=sugestao_dados["tokens_input"],
                tokens_output=sugestao_dados["tokens_output"],
                custo_estimado=sugestao_dados["custo"],
            )
            session.add(interacao_escalacao)
            await session.commit()
            await session.refresh(interacao_escalacao)
            interacao_id = interacao_escalacao.id

            log.info("interacao_escalacao_criada", interacao_id=interacao_id)

            advogados_alertados = 0
            for adv in advogados:
                if not adv.whatsapp_numero:
                    continue

                texto_alerta = (
                    f"🔔 *NOVA SOLICITAÇÃO DE ATENDIMENTO (ESCALAÇÃO)*\n"
                    f"*Motivo:* {motivo}\n\n"
                    f"*Mensagem do Cliente:*\n💬 _{mensagem_cliente}_\n\n"
                    f"*Sugestão da IA (Rascunho):*\n🤖 {sugestao}\n\n"
                    f"---\n"
                    f"Para *APROVAR* a sugestão ou enviar sua própria resposta, resgate "
                    f"essa interação (ID #{interacao_id}) em nosso painel ou cite "
                    f"essa mensagem com a sua resposta final."
                )

                try:
                    await self._evolution.enviar_texto(
                        instance=instancia_whatsapp,
                        numero=adv.whatsapp_numero,
                        texto=texto_alerta,
                    )
                    log.info("whatsapp_escalacao_enviado", advogado_id=adv.id)
                    advogados_alertados += 1
                except Exception as exc:
                    log.error("whatsapp_escalacao_falha", advogado_id=adv.id, erro=str(exc))

            return {
                "enviado": advogados_alertados > 0,
                "interacao_id": interacao_id,
                "notificados_count": advogados_alertados,
            }

    async def _gerar_sugestao_resposta(
        self, mensagem: str, historico: list[dict[str, str]]
    ) -> dict[str, Any]:
        """
        Solicita ao Claude que elabore uma resposta amigável e correta como rascunho
        para o advogado. Retorna um dicionário com `resposta`, e os tokens usados.
        """
        system_prompt = (
            "Você é um assistente de minuta para advogados. "
            "Abaixo você receberá uma dúvida jurídica complexa ou estratégica de um cliente. "
            "Sua tarefa é elaborar um RASCUNHO EXCELENTE, em tom acolhedor e seguro, "
            "para que o advogado possa apenas aprovar ou editar levemente antes de enviar para o cliente. "
            "Não adicione introduções ou explicações no seu texto, responda apenas o texto que deve "
            "ser lido pelo cliente. Se faltarem detalhes factuais para responder, sugira que o escritório "
            "entrará em contato profundo amanhã ou peça mais informações ao cliente."
        )

        try:
            return await self._claude.enviar_mensagem(
                system_prompt=system_prompt,
                mensagens_historico=historico,
                mensagem_usuario=mensagem,
                intencao="parecer_juridico",
            )
        except Exception as exc:
            logger.error("geracao_sugestao_falha", erro=str(exc))
            # Fallback limpo: 1 token representativo
            return {
                "resposta": "Olá! Verificamos a complexidade de sua dúvida e um de nossos recortes de caso o orientará em seguida.",
                "tokens_input": 0,
                "tokens_output": 0,
                "custo": Decimal("0"),
            }
