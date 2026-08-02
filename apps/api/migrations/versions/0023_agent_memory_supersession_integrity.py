"""Add immutable supersession links for experience-memory patterns."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_memory_patterns", sa.Column("superseded_by_key", sa.String(255)))
    op.create_check_constraint(
        "ck_agent_memory_pattern_not_self_superseded",
        "agent_memory_patterns",
        "superseded_by_key IS NULL OR superseded_by_key <> pattern_key",
    )
    op.create_check_constraint(
        "ck_agent_memory_pattern_confidence_bounds",
        "agent_memory_patterns",
        "confidence >= 0 AND confidence <= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_agent_memory_pattern_confidence_bounds", "agent_memory_patterns")
    op.drop_constraint("ck_agent_memory_pattern_not_self_superseded", "agent_memory_patterns")
    op.drop_column("agent_memory_patterns", "superseded_by_key")
