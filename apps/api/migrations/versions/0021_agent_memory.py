"""Add native PostgreSQL experience memory tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "agent_memory_episodes",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("problem_signature", sa.String(512), nullable=False),
        sa.Column("scope", jsonb(), nullable=False, server_default="{}"),
        sa.Column("tags", jsonb(), nullable=False, server_default="[]"),
        sa.Column("metadata", jsonb(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("feedback_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "superseded_by_id",
            sa.String(40),
            sa.ForeignKey("agent_memory_episodes.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', title || ' ' || goal || ' ' || problem_signature)",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "domain IN ('engineering', 'trading', 'research', 'operations', 'custom')",
            name="ck_agent_memory_episode_domain",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'active', 'degraded', 'superseded', 'rejected')",
            name="ck_agent_memory_episode_status",
        ),
    )
    op.create_index(
        "ix_agent_memory_episodes_scope_created",
        "agent_memory_episodes",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_agent_memory_episodes_signature",
        "agent_memory_episodes",
        ["project_id", "problem_signature"],
    )
    op.create_index(
        "ix_agent_memory_episodes_search",
        "agent_memory_episodes",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_agent_memory_episodes_scope", "agent_memory_episodes", ["scope"], postgresql_using="gin"
    )
    op.create_table(
        "agent_memory_attempts",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "episode_id",
            sa.String(40),
            sa.ForeignKey("agent_memory_episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("actions", jsonb(), nullable=False, server_default="[]"),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("metadata", jsonb(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("episode_id", "sequence", name="uq_agent_memory_attempt_sequence"),
        sa.CheckConstraint(
            "result IN ('success', 'failed', 'partial')", name="ck_agent_memory_attempt_result"
        ),
    )
    op.create_table(
        "agent_memory_outcomes",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "episode_id",
            sa.String(40),
            sa.ForeignKey("agent_memory_episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("lesson", sa.Text()),
        sa.Column("metrics", jsonb(), nullable=False, server_default="{}"),
        sa.Column("metadata", jsonb(), nullable=False, server_default="{}"),
        sa.Column("pattern_key", sa.String(255), nullable=False),
        sa.UniqueConstraint("episode_id", name="uq_agent_memory_final_outcome_episode"),
        sa.CheckConstraint(
            "status IN ('success', 'failed', 'partial', 'cancelled')",
            name="ck_agent_memory_outcome_status",
        ),
    )
    op.create_table(
        "agent_memory_verifiers",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "outcome_id",
            sa.String(40),
            sa.ForeignKey("agent_memory_outcomes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("command", sa.Text()),
        sa.Column("artifact_uri", sa.Text()),
        sa.Column("metrics", jsonb(), nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "kind IN ('ci', 'runtime', 'test', 'build', 'self_report', 'custom')",
            name="ck_agent_memory_verifier_kind",
        ),
    )
    op.create_table(
        "agent_memory_evidence",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "episode_id",
            sa.String(40),
            sa.ForeignKey("agent_memory_episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("metadata", jsonb(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "agent_memory_patterns",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pattern_key", sa.String(255), nullable=False),
        sa.Column("verified_outcomes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("weighted_successes", sa.Float(), nullable=False, server_default="0"),
        sa.Column("weighted_total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("promoted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("project_id", "pattern_key", name="uq_agent_memory_pattern_key"),
    )
    op.create_index(
        "ix_agent_memory_patterns_search",
        "agent_memory_patterns",
        ["project_id", "promoted", "confidence"],
    )
    op.create_table(
        "agent_memory_pattern_members",
        sa.Column(
            "pattern_id",
            sa.String(40),
            sa.ForeignKey("agent_memory_patterns.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "outcome_id",
            sa.String(40),
            sa.ForeignKey("agent_memory_outcomes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "agent_memory_retrieval_audit",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("results", jsonb(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_agent_memory_retrieval_audit_project_created",
        "agent_memory_retrieval_audit",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("agent_memory_retrieval_audit")
    op.drop_table("agent_memory_pattern_members")
    op.drop_table("agent_memory_patterns")
    op.drop_table("agent_memory_evidence")
    op.drop_table("agent_memory_verifiers")
    op.drop_table("agent_memory_outcomes")
    op.drop_table("agent_memory_attempts")
    op.drop_table("agent_memory_episodes")
