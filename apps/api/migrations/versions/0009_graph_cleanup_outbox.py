"""Add durable graph projection cleanup outbox."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def cleanup_outbox() -> sa.Table:
    # Keep this historical schema frozen: later delivery-state columns belong to 0010.
    return sa.Table(
        "graph_cleanup_outbox",
        sa.MetaData(),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", sa.String(length=40), nullable=False),
        sa.Column("document_id", sa.String(length=40)),
        sa.Column("target", sa.Enum("DOCUMENT", "DATASET", name="graph_cleanup_target")),
        sa.Column("ready", sa.Boolean(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Index("ix_graph_cleanup_dispatch", "ready", "published_at"),
    )


def upgrade() -> None:
    cleanup_outbox().create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    cleanup_outbox().drop(op.get_bind(), checkfirst=True)
