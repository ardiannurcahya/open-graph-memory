"""Add persisted ingestion pipeline."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'QUEUED'")
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'PARSING'")
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'CHUNKING'")
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'EMBEDDING'")
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'PERSISTING'")
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'INDEXED'")
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'FAILED'")
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'CANCELLED'")
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'STALE'")
    job_status = postgresql.ENUM(
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        name="indexing_job_status",
        create_type=False,
    )
    stage = postgresql.ENUM(
        "QUEUED",
        "READING",
        "PARSING",
        "CHUNKING",
        "EMBEDDING",
        "PERSISTING",
        "COMPLETE",
        name="indexing_stage",
        create_type=False,
    )
    job_status.create(op.get_bind(), checkfirst=True)
    stage.create(op.get_bind(), checkfirst=True)

    def scope() -> tuple[sa.Column[object], ...]:
        return (
            sa.Column(
                "project_id",
                sa.Uuid(),
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
                "document_id",
                sa.String(40),
                sa.ForeignKey("documents.id", ondelete="CASCADE"),
                nullable=False,
            ),
        )

    op.create_table(
        "indexing_jobs",
        sa.Column("id", sa.String(40), primary_key=True),
        *scope(),
        sa.Column("status", job_status, nullable=False),
        sa.Column("stage", stage, nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("pipeline_version", sa.String(100), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("trace_id", sa.String(40), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("document_id", "pipeline_version"),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(40), primary_key=True),
        *scope(),
        sa.Column("pipeline_version", sa.String(100), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column(
            "metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("document_id", "pipeline_version", "chunk_index"),
    )
    op.create_index("ix_chunks_scope", "chunks", ["project_id", "dataset_id"])
    op.create_table(
        "indexing_artifacts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(40),
            sa.ForeignKey("indexing_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(40),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column(
            "metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("job_id", "kind", "version", name="uq_artifact_version"),
    )
    op.create_table(
        "indexing_stage_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(40),
            sa.ForeignKey("indexing_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("stage", stage, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("job_id", "attempt", "stage", name="uq_job_attempt_stage"),
    )


def downgrade() -> None:
    op.drop_table("indexing_stage_events")
    op.drop_table("indexing_artifacts")
    op.drop_index("ix_chunks_scope", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("indexing_jobs")
    sa.Enum(name="indexing_stage").drop(op.get_bind())
    sa.Enum(name="indexing_job_status").drop(op.get_bind())
