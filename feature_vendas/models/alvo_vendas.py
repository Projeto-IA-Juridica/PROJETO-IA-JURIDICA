"""
shared/models/alvo_vendas.py
=============================
Alvo da máquina de vendas: um escritório de advocacia a ser prospectado.

Diferente de `lead_prospeccao` (F3 — leads DOS advogados, os clientes deles),
este model é a nossa própria pipeline de vendas: os advogados que queremos como
clientes. Vive fora do multi-tenant de clientes; pertence ao tenant interno de
vendas (SALES_TENANT_ID).

Ciclo de vida (campo `status`), espelha o roteiro da máquina:

  novo          → recém-importado da planilha
  enriquecendo  → worker buscando processo público + gerando mensagem-espelho
  fila_envio    → mensagem validada (confiança alta) → pronta para disparar
  fila_excecao  → validação com baixa confiança → humano revisa antes
  abordado      → toque 1 enviado
  em_cadencia   → sem resposta; toques 2/3 agendados
  respondeu     → engajou; a Clara assumiu a conversa (sai da cadência)
  quente        → critério de handoff batido; call oferecida/agendada
  descartado    → opt-out, número inválido, desqualificado ou fim da cadência
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.models.base import Base, TenantMixin, TimestampMixin

STATUS_ALVO = frozenset(
    {
        "novo",
        "enriquecendo",
        "fila_envio",
        "fila_excecao",
        "abordado",
        "em_cadencia",
        "respondeu",
        "quente",
        "descartado",
    }
)


class AlvoVendas(Base, TenantMixin, TimestampMixin):
    __tablename__ = "alvos_vendas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Identificação (da planilha) ---
    nome_escritorio: Mapped[str] = mapped_column(String(200), nullable=False)
    nome_contato: Mapped[str | None] = mapped_column(String(120), nullable=True)
    oab: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    cnpj: Mapped[str | None] = mapped_column(String(18), nullable=True, index=True)
    whatsapp: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    cidade: Mapped[str | None] = mapped_column(String(120), nullable=True)
    area: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # --- Filtragem (ICP score, etapa 2 do playbook) ---
    score_icp: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    classe_icp: Mapped[str | None] = mapped_column(String(1), nullable=True, comment="A | B | C")
    origem: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        server_default="planilha",
        comment="planilha | vaga | anuncio | indicacao | inbound",
    )

    # --- Enriquecimento (etapa 2/3) ---
    processo_cnj: Mapped[str | None] = mapped_column(String(30), nullable=True)
    movimentacao_bruta: Mapped[str | None] = mapped_column(Text, nullable=True)
    mensagem_espelho: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Toque 1 gerado; revisado pelo humano só se fila_excecao"
    )
    template_usado: Mapped[str | None] = mapped_column(
        String(1), nullable=True, comment="A = espelho com processo | B = genérico"
    )
    confianca_validacao: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="0-100 do fact-checker"
    )

    # --- Estado ---
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="novo",
        index=True,
    )
    cliente_conversa_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Id do 'cliente' criado no tenant de vendas quando o lead responde e a Clara assume",
    )

    # --- Cadência (etapa 5) ---
    toques_enviados: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    ultimo_toque_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proximo_toque_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    respondeu_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Auditoria de decisões (por que descartou, por que virou exceção etc.) ---
    metadados: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AlvoVendas id={self.id} {self.nome_escritorio!r} "
            f"status={self.status!r} classe={self.classe_icp!r}>"
        )
