"""Add agent memory preview tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

memory_fact_status = postgresql.ENUM(
    "ACTIVE", "SUPERSEDED", "DELETED", name="memory_fact_status", create_type=False
)


def upgrade() -> None:
    memory_fact_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "memory_users",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("project_id", "external_id", name="uq_memory_users_project_external"),
    )
    op.create_table(
        "memory_agents",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_memory_agents_project_name"),
    )
    op.create_table(
        "memory_sessions",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(length=40),
            sa.ForeignKey("memory_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(length=40),
            sa.ForeignKey("memory_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_memory_sessions_scope", "memory_sessions", ["project_id", "user_id", "agent_id"]
    )
    op.create_table(
        "memory_messages",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.String(length=40),
            sa.ForeignKey("memory_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_memory_messages_session_created", "memory_messages", ["session_id", "created_at"]
    )
    op.create_table(
        "memory_facts",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(length=40),
            sa.ForeignKey("memory_users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "agent_id",
            sa.String(length=40),
            sa.ForeignKey("memory_agents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            sa.String(length=40),
            sa.ForeignKey("memory_sessions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("predicate", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("status", memory_fact_status, nullable=False),
        sa.Column(
            "supersedes_id",
            sa.String(length=40),
            sa.ForeignKey("memory_facts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_message_id",
            sa.String(length=40),
            sa.ForeignKey("memory_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "valid_from", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_memory_facts_scope_status", "memory_facts", ["project_id", "scope", "status"]
    )
    op.create_index(
        "ix_memory_facts_subject", "memory_facts", ["project_id", "subject", "predicate"]
    )


def downgrade() -> None:
    op.drop_index("ix_memory_facts_subject", table_name="memory_facts")
    op.drop_index("ix_memory_facts_scope_status", table_name="memory_facts")
    op.drop_table("memory_facts")
    op.drop_index("ix_memory_messages_session_created", table_name="memory_messages")
    op.drop_table("memory_messages")
    op.drop_index("ix_memory_sessions_scope", table_name="memory_sessions")
    op.drop_table("memory_sessions")
    op.drop_table("memory_agents")
    op.drop_table("memory_users")
    memory_fact_status.drop(op.get_bind(), checkfirst=True)
