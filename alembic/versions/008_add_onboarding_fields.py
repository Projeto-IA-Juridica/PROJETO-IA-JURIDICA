"""add_onboarding_fields

Revision ID: 008_add_onboarding_fields
Revises: 008_add_analytics_indexes
Create Date: 2026-03-19

Feature 4 — Módulo de Onboarding Automatizado do Escritório.
Adiciona campos de persona e controle de onboarding na tabela escritorios.
"""

import sqlalchemy as sa

from alembic import op

revision = "008_add_onboarding_fields"
down_revision = "008_add_analytics_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "escritorios",
        sa.Column(
            "persona_nome",
            sa.String(100),
            nullable=True,
            server_default="Assistente Jurídico",
            comment="Nome da IA exibido aos clientes",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "persona_tom",
            sa.String(50),
            nullable=True,
            server_default="formal",
            comment="Tom da IA: formal | amigavel | neutro",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "horario_inicio",
            sa.Time(),
            nullable=True,
            server_default="08:00",
            comment="Início do horário de atendimento (HH:MM)",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "horario_fim",
            sa.Time(),
            nullable=True,
            server_default="18:00",
            comment="Fim do horário de atendimento (HH:MM)",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "onboarding_etapa",
            sa.SmallInteger(),
            nullable=True,
            server_default="0",
            comment="Etapa atual do onboarding (0-5)",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "onboarding_completo",
            sa.Boolean(),
            nullable=True,
            server_default="false",
            comment="Indica se o onboarding foi concluído",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "onboarding_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Timestamp de conclusão do onboarding",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "template_boas_vindas",
            sa.Text(),
            nullable=True,
            comment="Template personalizado de boas-vindas (deve conter {nome_cliente})",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "template_atualizacao",
            sa.Text(),
            nullable=True,
            comment="Template personalizado de atualização processual",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "template_sem_novidade",
            sa.Text(),
            nullable=True,
            comment="Template personalizado para quando não há novidades",
        ),
    )

    # =========================================================================
    # CHECK constraints — validação a nível de banco
    # =========================================================================

    # Obs 1: persona_tom só aceita os 3 valores suportados
    op.create_check_constraint(
        "check_persona_tom",
        "escritorios",
        "persona_tom IN ('formal', 'amigavel', 'neutro') OR persona_tom IS NULL",
    )

    # Obs 2: onboarding_etapa deve estar entre 0 e 5
    op.create_check_constraint(
        "check_onboarding_etapa",
        "escritorios",
        "onboarding_etapa BETWEEN 0 AND 5 OR onboarding_etapa IS NULL",
    )

    # Obs 3: horario_inicio deve ser anterior a horario_fim (sem suporte overnight)
    op.create_check_constraint(
        "check_horario_valido",
        "escritorios",
        "horario_inicio < horario_fim OR horario_inicio IS NULL OR horario_fim IS NULL",
    )


def downgrade() -> None:
    # Remove constraints antes das colunas
    op.drop_constraint("check_horario_valido", "escritorios", type_="check")
    op.drop_constraint("check_onboarding_etapa", "escritorios", type_="check")
    op.drop_constraint("check_persona_tom", "escritorios", type_="check")

    for col in [
        "template_sem_novidade",
        "template_atualizacao",
        "template_boas_vindas",
        "onboarding_at",
        "onboarding_completo",
        "onboarding_etapa",
        "horario_fim",
        "horario_inicio",
        "persona_tom",
        "persona_nome",
    ]:
        op.drop_column("escritorios", col)
