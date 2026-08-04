"""Add retention policy and audit trail tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025"
down_revision = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "retention_policies",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("older_than_days", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "resource_type IN ('episode', 'memory')",
            name="ck_retention_policy_resource_type",
        ),
        sa.CheckConstraint(
            "action IN ('archive', 'delete')",
            name="ck_retention_policy_action",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'completed')",
            name="ck_retention_policy_status",
        ),
        sa.CheckConstraint("older_than_days > 0", name="ck_retention_policy_days_positive"),
    )
    op.create_index(
        "ix_retention_policies_project_status",
        "retention_policies",
        ["project_id", "status"],
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(255)),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(40), nullable=False),
        sa.Column("metadata", jsonb(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "actor_type IN ('user', 'api_key', 'system')",
            name="ck_audit_log_actor_type",
        ),
    )
    op.create_index(
        "ix_audit_logs_project_resource",
        "audit_logs",
        ["project_id", "resource_type", "resource_id"],
    )
    op.create_index(
        "ix_audit_logs_project_created",
        "audit_logs",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_audit_logs_project_operation",
        "audit_logs",
        ["project_id", "operation"],
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(40)),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("key", "project_id"),
    )
    op.create_index(
        "ix_idempotency_keys_project_created",
        "idempotency_keys",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_table("audit_logs")
    op.drop_table("retention_policies")
