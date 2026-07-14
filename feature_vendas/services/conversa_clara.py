"""
O fio que conecta tudo: a conversa da Clara no número-vitrine.

webhook → buffer → Claude (prompt da Clara) → entrega humanizada → lead scoring → handoff

Handler AUTOCONTIDO de propósito. NÃO passa pelo orquestrador do produto: aquele
grafo é feito para o cliente do advogado (RAG do escritório, fact-check contra o
banco de processos, escalação para advogado). Nada disso se aplica a uma conversa
de vendas — e forçar a Clara por lá exigiria ramificar o produto com "se for
vendas...", exatamente a contaminação que queremos evitar.

Reuso aqui é só de ferramentas de baixo nível, read-only e sem estado de cliente:
  - ClaudeClient.enviar_mensagem  (wrapper do Claude, com prompt caching)
  - ConversationMemory            (histórico por conversa no Redis)
Ambas são utilitários compartilhados; usá-las não acopla vendas ao produto.
"""

from __future__ import annotations

import re

import structlog

from feature_vendas.services.humanizacao.buffer import BufferMensagens
from feature_vendas.services.humanizacao.cadencia import EntregaHumanizada
from feature_vendas.services.humanizacao.estilo import system_prompt_clara
from feature_vendas.services.lead_scoring import Qualificacao, avaliar_lead

logger = structlog.get_logger(__name__)

# Extração best-effort da qualificação a partir da conversa (sem gastar token).
# Alimenta só o gatilho "escritório grande"; os gatilhos fortes (preço/trial/
# reunião) vêm da última mensagem e não dependem disso.
_RE_NUM_ADV = re.compile(r"\b(?:somos|s[aã]o|temos)\s+(\d{1,3})\b|\b(\d{1,3})\s*advogad", re.I)
_RE_SECRETARIA = re.compile(r"\bsecret[aá]ri", re.I)
_RE_EU_MESMO = re.compile(r"\b(eu mesmo|n[oó]s mesmos|eu que|a gente responde|sou eu)\b", re.I)
_AREAS = (
    "trabalhista",
    "cível",
    "civel",
    "previdenci",
    "família",
    "familia",
    "tributári",
    "penal",
    "consumidor",
)


def _extrair_qualificacao(historico_texto: str) -> Qualificacao:
    num = None
    m = _RE_NUM_ADV.search(historico_texto)
    if m:
        try:
            num = int(m.group(1) or m.group(2))
        except (TypeError, ValueError):
            num = None
    area = next((a for a in _AREAS if a in historico_texto.lower()), None)
    quem = None
    if _RE_SECRETARIA.search(historico_texto):
        quem = "secretaria"
    elif _RE_EU_MESMO.search(historico_texto):
        quem = "eles"
    return Qualificacao(num_advogados=num, area=area, quem_responde=quem)


class ConversaClara:
    """
    Orquestra UMA mensagem recebida no vitrine. Instanciado por task de worker.

    on_quente: callback assíncrono chamado quando o lead esquenta — quem liga
    isso decide o handoff (notificar sócio, marcar AlvoVendas). Mantém este
    módulo sem dependência do banco de alvos.
    """

    def __init__(
        self,
        *,
        redis,  # noqa: ANN001
        claude,  # noqa: ANN001 — ClaudeClient
        memory,  # noqa: ANN001 — ConversationMemory
        evolution,  # noqa: ANN001 — EvolutionHumano
        instancia: str,
        tenant_id: int,
    ) -> None:
        self._buffer = BufferMensagens(redis)
        self._claude = claude
        self._memory = memory
        self._entrega = EntregaHumanizada(evolution, instancia)
        self._tenant = tenant_id

    async def processar(
        self,
        *,
        lead_ref: int,
        numero: str,
        texto: str,
        message_id: str | None = None,
        eh_audio: bool = False,
    ) -> dict | None:
        """
        Ponto de entrada. Devolve um dict de resultado (para o worker registrar
        no AlvoVendas), ou None quando outra invocação assumiu a rajada.
        """
        log = logger.bind(tenant=self._tenant, lead_ref=lead_ref)

        # 1. Buffer: espera a pessoa terminar de escrever e concatena.
        consolidado = await self._buffer.aguardar_e_consolidar(
            self._tenant, lead_ref, texto, eh_audio=eh_audio
        )
        if consolidado is None:
            return None  # a última mensagem da rajada responde por todas

        # 2. Histórico da conversa (Redis, isolado por tenant+lead).
        historico = await self._memory.buscar_historico(self._tenant, lead_ref, limite=20)

        # 3. Claude com o prompt da Clara (prompt caching no wrapper).
        resultado = await self._claude.enviar_mensagem(
            system_prompt=system_prompt_clara(),
            mensagens_historico=historico,
            mensagem_usuario=consolidado,
            intencao="vendas",
        )
        resposta = resultado["resposta"]

        # 4. Persiste antes de enviar (at-least-once).
        await self._memory.salvar_mensagem(self._tenant, lead_ref, "user", consolidado)
        await self._memory.salvar_mensagem(self._tenant, lead_ref, "assistant", resposta)

        # 5. Entrega humanizada (digitando + quebra + delays).
        balões = await self._entrega.responder(numero, consolidado, resposta, message_id)

        # 6. Lead scoring: essa conversa esquentou?
        texto_conversa = "\n".join(m["content"] for m in historico) + "\n" + consolidado
        qualificacao = _extrair_qualificacao(texto_conversa)
        # +2: contamos a mensagem atual e a resposta da Clara (ainda não no histórico).
        total_interacoes = len(historico) // 2 + 1
        lead = avaliar_lead(
            ultima_mensagem=consolidado,
            total_interacoes=total_interacoes,
            qualificacao=qualificacao,
        )

        log.info(
            "conversa_clara_respondida",
            balões=len(balões),
            quente=lead.quente,
            gatilho=lead.gatilho or None,
        )

        return {
            "resposta": resposta,
            "quente": lead.quente,
            "gatilho": lead.gatilho,
            "qualificacao": {
                "num_advogados": qualificacao.num_advogados,
                "area": qualificacao.area,
                "quem_responde": qualificacao.quem_responde,
            },
        }
