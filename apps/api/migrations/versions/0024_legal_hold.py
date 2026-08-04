"""Add legal hold tables for compliance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024"
down_revision = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "legal_holds",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "resource_type IN ('episode', 'memory', 'entity', 'project')",
            name="ck_legal_hold_resource_type",
        ),
        sa.UniqueConstraint(
            "project_id", "resource_type", "resource_id", name="uq_legal_hold_resource"
        ),
    )
    op.create_index(
        "ix_legal_holds_project_resource",
        "legal_holds",
        ["project_id", "resource_type", "resource_id"],
    )
    op.create_index(
        "ix_legal_holds_project_created",
        "legal_holds",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("legal_holds")
