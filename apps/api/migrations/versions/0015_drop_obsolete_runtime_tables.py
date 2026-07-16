"""Drop obsolete generated-runtime tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "query_logs",
    "memory_users",
    "memory_agents",
    "memory_sessions",
    "memory_messages",
    "memory_facts",
    "community_report_jobs",
    "community_report_outbox",
    "community_reports",
    "community_report_evidence",
)

memory_fact_status = postgresql.ENUM(
    "ACTIVE", "SUPERSEDED", "DELETED", name="memory_fact_status", create_type=False
)
community_report_status = postgresql.ENUM(
    "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", name="community_report_status", create_type=False
)


def upgrade() -> None:
    op.drop_table("community_report_evidence")
    op.drop_table("community_reports")
    op.drop_table("community_report_outbox")
    op.drop_table("community_report_jobs")
    op.drop_table("memory_facts")
    op.drop_table("memory_messages")
    op.drop_table("memory_sessions")
    op.drop_table("memory_agents")
    op.drop_table("memory_users")
    op.drop_table("query_logs")


def downgrade() -> None:
    op.create_table(
        "query_logs",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("trace_id", sa.String(40), nullable=False, unique=True),
        sa.Column(
            "project_id",
            sa.UUID(),
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
    op.create_table(
        "memory_users",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255)),
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
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
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
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(40),
            sa.ForeignKey("memory_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(40),
            sa.ForeignKey("memory_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255)),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
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
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.String(40),
            sa.ForeignKey("memory_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(32), nullable=False),
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
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(40), sa.ForeignKey("memory_users.id", ondelete="CASCADE")),
        sa.Column(
            "agent_id", sa.String(40), sa.ForeignKey("memory_agents.id", ondelete="CASCADE")
        ),
        sa.Column(
            "session_id", sa.String(40), sa.ForeignKey("memory_sessions.id", ondelete="CASCADE")
        ),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("predicate", sa.String(100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("status", memory_fact_status, nullable=False),
        sa.Column(
            "supersedes_id",
            sa.String(40),
            sa.ForeignKey("memory_facts.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "source_message_id",
            sa.String(40),
            sa.ForeignKey("memory_messages.id", ondelete="SET NULL"),
        ),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "valid_from", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
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
    op.create_table(
        "community_report_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id",
            sa.String(40),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "analytics_run_id",
            sa.String(64),
            sa.ForeignKey("graph_analytics_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("community_id", sa.String(32), nullable=False),
        sa.Column("status", community_report_status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("report_version", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.CheckConstraint("level BETWEEN 0 AND 2", name="ck_community_report_jobs_level"),
        sa.UniqueConstraint(
            "analytics_run_id",
            "community_id",
            "level",
            "input_hash",
            name="uq_community_report_job_input",
        ),
    )
    op.create_index(
        "ix_community_report_jobs_scope",
        "community_report_jobs",
        ["project_id", "dataset_id", "analytics_run_id"],
    )
    op.create_index(
        "ix_community_report_jobs_dispatch",
        "community_report_jobs",
        ["status", "next_attempt_at"],
    )
    op.create_table(
        "community_report_outbox",
        sa.Column(
            "job_id",
            sa.String(64),
            sa.ForeignKey("community_report_jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "community_reports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(64),
            sa.ForeignKey("community_report_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id",
            sa.String(40),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "analytics_run_id",
            sa.String(64),
            sa.ForeignKey("graph_analytics_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("community_id", sa.String(32), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_points", postgresql.JSONB(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.CheckConstraint("level BETWEEN 0 AND 2", name="ck_community_reports_level"),
        sa.UniqueConstraint("job_id", name="uq_community_report_job"),
    )
    op.create_index(
        "ix_community_reports_scope",
        "community_reports",
        ["project_id", "dataset_id", "analytics_run_id", "community_id"],
    )
    op.create_table(
        "community_report_evidence",
        sa.Column(
            "report_id",
            sa.String(64),
            sa.ForeignKey("community_reports.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "chunk_id",
            sa.String(40),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.UniqueConstraint("report_id", "chunk_id", name="uq_community_report_evidence"),
    )
