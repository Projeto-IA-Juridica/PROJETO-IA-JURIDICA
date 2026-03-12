"""create initial tables

Revision ID: 001_create_initial_tables
Revises:
Create Date: 2026-02-21

Cria as 5 tabelas do schema inicial:
  escritorios → usuarios, clientes → processos → interacoes
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "001_create_initial_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. escritorios — tabela raiz (tenant)
    # =========================================================================
    op.create_table(
        "escritorios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("cnpj", sa.String(18), nullable=False),
        sa.Column("email", sa.String(200), nullable=False),
        sa.Column("telefone", sa.String(20), nullable=True),
        sa.Column("endereco", sa.String(500), nullable=True),
        sa.Column("oab_responsavel", sa.String(20), nullable=False),
        sa.Column("nome_responsavel", sa.String(200), nullable=False),
        sa.Column("plano", sa.String(50), nullable=False, server_default="basico"),
        sa.Column("max_processos", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("max_clientes", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("webhook_whatsapp_instance", sa.String(100), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cnpj", name="uq_escritorios_cnpj"),
    )

    # =========================================================================
    # 2. usuarios — usuários internos do escritório
    # =========================================================================
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("escritorio_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200), nullable=False),
        sa.Column("senha_hash", sa.String(300), nullable=False),
        sa.Column("role", sa.String(30), nullable=False, server_default="advogado"),
        sa.Column("oab", sa.String(20), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ultimo_login", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["escritorio_id"],
            ["escritorios.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_usuarios_email"),
    )
    op.create_index("ix_usuarios_escritorio_id", "usuarios", ["escritorio_id"])

    # =========================================================================
    # 3. clientes — clientes finais do escritório (whatsapp)
    # =========================================================================
    op.create_table(
        "clientes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("escritorio_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("cpf", sa.String(100), nullable=False),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("telefone_whatsapp", sa.String(20), nullable=False),
        sa.Column("data_nascimento", sa.Date(), nullable=True),
        sa.Column("profissao", sa.String(100), nullable=True),
        sa.Column("empresa_atual", sa.String(200), nullable=True),
        sa.Column("cargo", sa.String(100), nullable=True),
        sa.Column("aceite_lgpd", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("data_aceite_lgpd", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "preferencia_horario_notificacao",
            sa.String(20),
            nullable=False,
            server_default="comercial",
        ),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        sa.ForeignKeyConstraint(
            ["escritorio_id"],
            ["escritorios.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("escritorio_id", "cpf", name="uq_clientes_escritorio_cpf"),
    )
    op.create_index("ix_clientes_escritorio_id", "clientes", ["escritorio_id"])
    op.create_index("ix_clientes_telefone_whatsapp", "clientes", ["telefone_whatsapp"])

    # =========================================================================
    # 4. processos — processos judiciais monitorados
    # =========================================================================
    op.create_table(
        "processos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("escritorio_id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("advogado_responsavel_id", sa.Integer(), nullable=True),
        sa.Column("numero_cnj", sa.String(25), nullable=False),
        sa.Column("tribunal", sa.String(10), nullable=True),
        sa.Column("vara", sa.String(200), nullable=True),
        sa.Column("comarca", sa.String(200), nullable=True),
        sa.Column("tipo_acao", sa.String(200), nullable=True),
        sa.Column("polo_cliente", sa.String(20), nullable=False, server_default="autor"),
        sa.Column("status", sa.String(50), nullable=False, server_default="ativo"),
        sa.Column("ultimo_andamento", sa.Text(), nullable=True),
        sa.Column("data_ultimo_andamento", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_distribuicao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valor_causa", sa.Numeric(15, 2), nullable=True),
        sa.Column("jusbrasil_id", sa.String(100), nullable=True),
        sa.Column(
            "monitoramento_ativo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "frequencia_monitoramento",
            sa.String(20),
            nullable=False,
            server_default="diario",
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
        sa.ForeignKeyConstraint(
            ["escritorio_id"],
            ["escritorios.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cliente_id"],
            ["clientes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["advogado_responsavel_id"],
            ["usuarios.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("escritorio_id", "numero_cnj", name="uq_processos_escritorio_cnj"),
    )
    op.create_index("ix_processos_escritorio_id", "processos", ["escritorio_id"])
    op.create_index("ix_processos_cliente_id", "processos", ["cliente_id"])
    op.create_index(
        "ix_processos_advogado_responsavel_id",
        "processos",
        ["advogado_responsavel_id"],
    )
    op.create_index("ix_processos_status", "processos", ["status"])

    # =========================================================================
    # 5. interacoes — log completo de mensagens (entrada e saída)
    # =========================================================================
    op.create_table(
        "interacoes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("escritorio_id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("processo_id", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("direcao", sa.String(10), nullable=False),
        sa.Column("mensagem_cliente", sa.Text(), nullable=True),
        sa.Column("mensagem_ia", sa.Text(), nullable=True),
        sa.Column("audio_transcricao", sa.Text(), nullable=True),
        sa.Column("tokens_input", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_output", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "custo_estimado",
            sa.Numeric(10, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column("tempo_resposta_ms", sa.Integer(), nullable=True),
        sa.Column("satisfacao", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["escritorio_id"],
            ["escritorios.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cliente_id"],
            ["clientes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["processo_id"],
            ["processos.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interacoes_escritorio_id", "interacoes", ["escritorio_id"])
    op.create_index(
        "ix_interacoes_escritorio_cliente",
        "interacoes",
        ["escritorio_id", "cliente_id"],
    )
    op.create_index("ix_interacoes_cliente_id", "interacoes", ["cliente_id"])
    op.create_index("ix_interacoes_created_at", "interacoes", ["created_at"])

    # =========================================================================
    # Trigger: updated_at automático no PostgreSQL
    #
    # O ORM já cuida disso via onupdate=func.now(), mas garantir no banco
    # protege contra updates diretos via SQL (migrations, seeds, scripts).
    # =========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    for tabela in ["escritorios", "usuarios", "clientes", "processos", "interacoes"]:
        op.execute(f"""
            CREATE TRIGGER trg_{tabela}_updated_at
            BEFORE UPDATE ON {tabela}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
        """)


def downgrade() -> None:
    # Remove triggers antes das tabelas
    for tabela in ["interacoes", "processos", "clientes", "usuarios", "escritorios"]:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tabela}_updated_at ON {tabela};")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at();")

    # Remove na ordem inversa para respeitar as FKs
    op.drop_table("interacoes")
    op.drop_table("processos")
    op.drop_table("clientes")
    op.drop_table("usuarios")
    op.drop_table("escritorios")
