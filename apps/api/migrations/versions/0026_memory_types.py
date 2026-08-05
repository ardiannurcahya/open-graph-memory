"""Add memory types, content, confidence, and versioning."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026"
down_revision = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "agent_memory_episodes",
        sa.Column("type", sa.String(32), nullable=False, server_default="custom"),
    )
    op.add_column(
        "agent_memory_episodes",
        sa.Column("content", jsonb(), nullable=True),
    )
    op.add_column(
        "agent_memory_episodes",
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
    )
    op.add_column(
        "agent_memory_episodes",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "agent_memory_episodes",
        sa.Column(
            "root_id",
            sa.String(40),
            sa.ForeignKey("agent_memory_episodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_agent_memory_episode_type",
        "agent_memory_episodes",
        (
            "type IN ("
            "'bugfix', 'decision', 'preference', 'procedure', "
            "'research', 'trading', 'learning', 'fact', 'custom'"
            ")"
        ),
    )

    op.create_index(
        "ix_agent_memory_episodes_type",
        "agent_memory_episodes",
        ["project_id", "type"],
    )
    op.create_index(
        "ix_agent_memory_episodes_confidence",
        "agent_memory_episodes",
        ["project_id", "confidence"],
    )

    op.create_table(
        "agent_memory_versions",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "episode_id",
            sa.String(40),
            sa.ForeignKey("agent_memory_episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", jsonb(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "superseded_by",
            sa.String(40),
            sa.ForeignKey("agent_memory_versions.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("episode_id", "version", name="uq_agent_memory_version"),
    )
    op.create_index(
        "ix_agent_memory_versions_episode",
        "agent_memory_versions",
        ["episode_id", "version"],
    )


def downgrade() -> None:
    op.drop_table("agent_memory_versions")
    op.drop_index("ix_agent_memory_episodes_confidence", "agent_memory_episodes")
    op.drop_index("ix_agent_memory_episodes_type", "agent_memory_episodes")
    op.drop_constraint("ck_agent_memory_episode_type", "agent_memory_episodes")
    op.drop_column("agent_memory_episodes", "root_id")
    op.drop_column("agent_memory_episodes", "version")
    op.drop_column("agent_memory_episodes", "confidence")
    op.drop_column("agent_memory_episodes", "content")
    op.drop_column("agent_memory_episodes", "type")
