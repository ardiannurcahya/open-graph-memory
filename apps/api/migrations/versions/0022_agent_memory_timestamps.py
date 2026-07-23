"""Add timestamps required by agent memory ORM records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_memory_attempts",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "agent_memory_outcomes",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_memory_outcomes", "created_at")
    op.drop_column("agent_memory_attempts", "created_at")
