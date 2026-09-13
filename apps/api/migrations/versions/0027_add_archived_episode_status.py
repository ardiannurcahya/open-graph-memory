"""Add archived status to ck_agent_memory_episode_status.

Revision ID: 0027
Revises: 0026
"""

from collections.abc import Sequence

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_agent_memory_episode_status", "agent_memory_episodes", type_="check")
    op.create_check_constraint(
        "ck_agent_memory_episode_status",
        "agent_memory_episodes",
        "status IN ('open', 'active', 'degraded', 'superseded', 'rejected', 'archived')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_agent_memory_episode_status", "agent_memory_episodes", type_="check")
    op.create_check_constraint(
        "ck_agent_memory_episode_status",
        "agent_memory_episodes",
        "status IN ('open', 'active', 'degraded', 'superseded', 'rejected')",
    )
