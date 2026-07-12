"""Add leased delivery state to the graph cleanup outbox."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "graph_cleanup_outbox",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "graph_cleanup_outbox",
        sa.Column("execution_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "graph_cleanup_outbox",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "graph_cleanup_outbox",
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_graph_cleanup_lease", "graph_cleanup_outbox", ["lease_expires_at"])
    op.create_index(
        "ix_graph_cleanup_execution_lease", "graph_cleanup_outbox", ["execution_lease_expires_at"]
    )
    op.create_index(
        "ix_graph_cleanup_ready",
        "graph_cleanup_outbox",
        ["ready", "completed_at", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_graph_cleanup_lease", table_name="graph_cleanup_outbox")
    op.drop_index("ix_graph_cleanup_execution_lease", table_name="graph_cleanup_outbox")
    op.drop_index("ix_graph_cleanup_ready", table_name="graph_cleanup_outbox")
    op.drop_column("graph_cleanup_outbox", "dead_lettered_at")
    op.drop_column("graph_cleanup_outbox", "next_attempt_at")
    op.drop_column("graph_cleanup_outbox", "execution_lease_expires_at")
    op.drop_column("graph_cleanup_outbox", "lease_expires_at")
