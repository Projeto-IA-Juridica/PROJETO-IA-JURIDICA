"""
Handoff: passa o lead quente para um sócio (etapa 5 → 6 do playbook).

Quando lead_scoring diz "quente", isto acontece, nesta ordem:

  1. escolhe o sócio (round-robin, com exceção: indicação do pai → Gabriel)
  2. monta o BRIEFING (quem é, o que testou, qualificação, gatilho) — o sócio
     nunca chega na call perguntando o que o lead já respondeu
  3. notifica o sócio no WhatsApp na hora (mesmo mecanismo de escalação do produto)
  4. marca o AlvoVendas como "quente" e registra o responsável

O agendamento da call em si reusa o Agendamento Inteligente: o sócio é um
"advogado" no tenant de vendas, com disponibilidade configurada; a Clara oferece
os horários livres dele e confirma. Nada novo — é o motor de reuniões do produto
apontado para a agenda dos sócios.

SLA: a notificação sai imediatamente; a meta de primeiro contato humano (<15min)
é operacional, medida no painel.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from feature_vendas.services.lead_scoring import GATILHO_LABEL, Qualificacao

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Socio:
    nome: str
    whatsapp: str
    usuario_id: int  # id no tenant de vendas (para o Agendamento usar a agenda dele)


def escolher_socio(socios: list[Socio], origem: str, contador_rr: int) -> Socio:
    """
    Round-robin simples, com a exceção do playbook: indicação do pai → Gabriel
    (o primeiro sócio da lista, por convenção). Para os demais, alterna.
    """
    if not socios:
        raise ValueError("nenhum sócio configurado para handoff")
    if origem == "indicacao":
        return socios[0]
    return socios[contador_rr % len(socios)]


def montar_briefing(
    *,
    nome_escritorio: str,
    nome_contato: str | None,
    cidade: str | None,
    gatilho: str,
    qualificacao: Qualificacao,
    trilhas_testadas: list[str],
    resumo_conversa: str | None = None,
) -> str:
    """O texto que o sócio recebe. Curto, escaneável — ele vai ler no celular."""
    linhas = [
        "🔥 LEAD QUENTE",
        f"{nome_escritorio}" + (f" — {nome_contato}" if nome_contato else ""),
    ]
    if cidade:
        linhas.append(f"📍 {cidade}")

    linhas.append(f"Por quê: {GATILHO_LABEL.get(gatilho, gatilho)}")

    quali = []
    if qualificacao.num_advogados is not None:
        quali.append(f"{qualificacao.num_advogados} advogado(s)")
    if qualificacao.area:
        quali.append(qualificacao.area)
    if qualificacao.quem_responde:
        quali.append(f"atende hoje: {qualificacao.quem_responde}")
    if quali:
        linhas.append("Perfil: " + ", ".join(quali))

    if trilhas_testadas:
        linhas.append("Testou: " + ", ".join(trilhas_testadas))
    if resumo_conversa:
        linhas.append(f"\nResumo: {resumo_conversa}")

    linhas.append("\nA Clara já vai oferecer seus horários pra call. Assuma quando puder.")
    return "\n".join(linhas)


class HandoffService:
    def __init__(self, evolution, instancia_vitrine: str) -> None:  # noqa: ANN001
        self._evo = evolution
        self._instancia = instancia_vitrine

    async def notificar_socio(self, socio: Socio, briefing: str) -> bool:
        """Manda o briefing pro WhatsApp do sócio. Best-effort — nunca quebra o fluxo."""
        try:
            await self._evo.enviar_texto(self._instancia, socio.whatsapp, briefing)
            logger.info("handoff_socio_notificado", socio=socio.nome)
            return True
        except Exception as exc:
            logger.error("handoff_notificacao_falhou", socio=socio.nome, erro=str(exc))
            return False
