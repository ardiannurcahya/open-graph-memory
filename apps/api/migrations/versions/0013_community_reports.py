"""Add community report lifecycle tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status_type = postgresql.ENUM(
        "queued",
        "running",
        "succeeded",
        "failed",
        name="community_report_status",
    )
    status_type.create(op.get_bind(), checkfirst=True)
    status = postgresql.ENUM(name="community_report_status", create_type=False)
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
        sa.Column("status", status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("report_version", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "analytics_run_id", "community_id", "input_hash", name="uq_community_report_job_input"
        ),
    )
    op.create_index(
        "ix_community_report_jobs_scope",
        "community_report_jobs",
        ["project_id", "dataset_id", "analytics_run_id"],
    )
    op.create_index(
        "ix_community_report_jobs_dispatch", "community_report_jobs", ["status", "next_attempt_at"]
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
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
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
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
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


def downgrade() -> None:
    op.drop_table("community_report_evidence")
    op.drop_index("ix_community_reports_scope", table_name="community_reports")
    op.drop_table("community_reports")
    op.drop_table("community_report_outbox")
    op.drop_index("ix_community_report_jobs_dispatch", table_name="community_report_jobs")
    op.drop_index("ix_community_report_jobs_scope", table_name="community_report_jobs")
    op.drop_table("community_report_jobs")
    sa.Enum(name="community_report_status").drop(op.get_bind(), checkfirst=True)
