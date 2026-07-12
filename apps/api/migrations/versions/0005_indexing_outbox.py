"""Add durable indexing dispatch outbox."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "indexing_outbox",
        sa.Column(
            "job_id",
            sa.String(40),
            sa.ForeignKey("indexing_jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.execute(
        "INSERT INTO indexing_outbox (job_id) "
        "SELECT id FROM indexing_jobs WHERE status = 'QUEUED' ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("indexing_outbox")
