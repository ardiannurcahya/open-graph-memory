"""Persist query traces."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "query_logs",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("trace_id", sa.String(40), nullable=False, unique=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id",
            sa.String(40),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("provider_version", sa.String(100), nullable=False),
        sa.Column("retrieval_trace", postgresql.JSONB(), nullable=False),
        sa.Column("usage", postgresql.JSONB(), nullable=False),
        sa.Column("latency_ms", sa.BigInteger(), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_query_logs_scope_created", "query_logs", ["project_id", "dataset_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_query_logs_scope_created", table_name="query_logs")
    op.drop_table("query_logs")
