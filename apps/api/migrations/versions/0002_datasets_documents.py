"""Add dataset and uploaded document metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status = postgresql.ENUM(
        "PENDING_UPLOAD",
        "UPLOADED",
        "STORAGE_FAILED",
        "DELETING",
        "DELETE_FAILED",
        name="document_status",
        create_type=False,
    )
    status.create(op.get_bind())
    dataset_status = postgresql.ENUM(
        "ACTIVE", "DELETING", "DELETE_FAILED", name="dataset_status", create_type=False
    )
    dataset_status.create(op.get_bind())
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", dataset_status, server_default="ACTIVE", nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_datasets_project_name"),
    )
    op.create_index("ix_datasets_project_id", "datasets", ["project_id"])
    op.create_table(
        "documents",
        sa.Column("id", sa.String(40), primary_key=True),
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
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), server_default="upload", nullable=False),
        sa.Column("object_key", sa.String(255), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "project_id",
            "dataset_id",
            "content_hash",
            name="uq_documents_project_dataset_hash",
        ),
    )
    op.create_index("ix_documents_project_dataset", "documents", ["project_id", "dataset_id"])


def downgrade() -> None:
    op.drop_table("documents")
    op.drop_table("datasets")
    sa.Enum(name="document_status").drop(op.get_bind())
    sa.Enum(name="dataset_status").drop(op.get_bind())
