"""add agendamento tables

Revision ID: 20260630_1000
Revises: 20260628_2000
Create Date: 2026-06-30 10:00:00.000000

Cria:
- tabela agendamentos
- tabela disponibilidade_advogado

Altera escritorios:
- ADD COLUMN telefone_advogado (WhatsApp do advogado para agendamento)
- ADD COLUMN timezone (fuso IANA; default America/Sao_Paulo)
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20260630_1000"
down_revision = "20260628_2000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # agendamentos
    # ------------------------------------------------------------------
    op.create_table(
        "agendamentos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("escritorio_id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("interacao_id", sa.Integer(), nullable=True),
        sa.Column("processo_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="aguardando_cliente",
        ),
        sa.Column("data_hora_inicio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_hora_fim", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opcoes_propostas", JSONB(), nullable=True),
        sa.Column("opcao_selecionada_pos", sa.SmallInteger(), nullable=True),
        sa.Column("canal_aprovacao", sa.String(length=20), nullable=True),
        sa.Column("motivo_cliente", sa.Text(), nullable=True),
        sa.Column(
            "whatsapp_proposta_cliente_enviado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "whatsapp_notificacao_advogado_enviado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "whatsapp_confirmacao_cliente_enviado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "whatsapp_confirmacao_pre_reuniao_enviado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("proposta_enviada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resposta_cliente_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resposta_advogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nota_advogado", sa.Text(), nullable=True),
        sa.Column("motivo_cancelamento", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["escritorio_id"], ["escritorios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["interacao_id"], ["interacoes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["processo_id"], ["processos.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # ix_agendamentos_escritorio_id é tecnicamente coberto pelo leftmost prefix do
    # composite ix_agendamentos_escritorio_status, mas TenantMixin.index=True o gera
    # em todos os models — mantemos aqui para que create_all (testes) e Alembic
    # (produção) produzam esquemas idênticos.
    op.create_index(
        "ix_agendamentos_escritorio_id",
        "agendamentos",
        ["escritorio_id"],
    )
    op.create_index(
        "ix_agendamentos_cliente_id",
        "agendamentos",
        ["cliente_id"],
    )
    op.create_index(
        "ix_agendamentos_interacao_id",
        "agendamentos",
        ["interacao_id"],
    )
    op.create_index(
        "ix_agendamentos_processo_id",
        "agendamentos",
        ["processo_id"],
    )
    op.create_index(
        "ix_agendamentos_status",
        "agendamentos",
        ["status"],
    )
    op.create_index(
        "ix_agendamentos_escritorio_status",
        "agendamentos",
        ["escritorio_id", "status"],
    )
    op.create_index(
        "ix_agendamentos_expira_em",
        "agendamentos",
        ["expira_em"],
    )

    # ------------------------------------------------------------------
    # disponibilidade_advogado
    # ------------------------------------------------------------------
    op.create_table(
        "disponibilidade_advogado",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("escritorio_id", sa.Integer(), nullable=False),
        sa.Column(
            "dia_semana",
            sa.SmallInteger(),
            nullable=False,
            comment="0=segunda, 1=terça, 2=quarta, 3=quinta, 4=sexta, 5=sábado",
        ),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fim", sa.Time(), nullable=False),
        sa.Column(
            "ativo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["escritorio_id"], ["escritorios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # UniqueConstraint já cria índice B-tree implícito no PostgreSQL.
        sa.UniqueConstraint(
            "escritorio_id",
            "dia_semana",
            name="uq_disponibilidade_escritorio_dia",
        ),
        sa.CheckConstraint(
            "dia_semana BETWEEN 0 AND 5",
            name="ck_disponibilidade_dia_semana",
        ),
        sa.CheckConstraint(
            "hora_fim > hora_inicio",
            name="ck_disponibilidade_horario",
        ),
    )
    # TenantMixin.index=True gera ix_disponibilidade_advogado_escritorio_id em
    # create_all (testes); declaramos explicitamente para paridade com produção.
    op.create_index(
        "ix_disponibilidade_advogado_escritorio_id",
        "disponibilidade_advogado",
        ["escritorio_id"],
    )

    # ------------------------------------------------------------------
    # escritorios — novos campos
    # ------------------------------------------------------------------
    op.add_column(
        "escritorios",
        sa.Column(
            "telefone_advogado",
            sa.String(length=20),
            nullable=True,
            comment="WhatsApp do advogado para notificações de agendamento",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "timezone",
            sa.String(length=50),
            nullable=False,
            server_default="America/Sao_Paulo",
            comment="Fuso IANA (ex: America/Sao_Paulo, America/Manaus, America/Rio_Branco)",
        ),
    )


def downgrade() -> None:
    op.drop_column("escritorios", "timezone")
    op.drop_column("escritorios", "telefone_advogado")

    op.drop_index(
        "ix_disponibilidade_advogado_escritorio_id", table_name="disponibilidade_advogado"
    )
    op.drop_table("disponibilidade_advogado")

    op.drop_index("ix_agendamentos_expira_em", table_name="agendamentos")
    op.drop_index("ix_agendamentos_escritorio_status", table_name="agendamentos")
    op.drop_index("ix_agendamentos_status", table_name="agendamentos")
    op.drop_index("ix_agendamentos_processo_id", table_name="agendamentos")
    op.drop_index("ix_agendamentos_interacao_id", table_name="agendamentos")
    op.drop_index("ix_agendamentos_cliente_id", table_name="agendamentos")
    op.drop_index("ix_agendamentos_escritorio_id", table_name="agendamentos")
    op.drop_table("agendamentos")
