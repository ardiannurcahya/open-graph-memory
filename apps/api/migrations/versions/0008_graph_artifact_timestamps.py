"""Require durable creation and update timestamps for graph artifacts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "graph_extraction_runs",
    "canonical_entities",
    "entity_aliases",
    "relation_assertions",
    "graph_evidence",
    "entity_merge_history",
)


def upgrade() -> None:
    # Existing timestamps win; the epoch makes legacy rows deterministic and auditable.
    for table in TABLES:
        columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
        if "created_at" not in columns:
            op.add_column(table, sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        if "updated_at" not in columns:
            op.add_column(table, sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        op.execute(
            sa.text(
                f"UPDATE {table} SET created_at = COALESCE(created_at, updated_at, "
                "TIMESTAMP WITH TIME ZONE '1970-01-01 00:00:00+00'), "
                "updated_at = COALESCE(updated_at, created_at, "
                "TIMESTAMP WITH TIME ZONE '1970-01-01 00:00:00+00') "
                "WHERE created_at IS NULL OR updated_at IS NULL"
            )
        )
        op.alter_column(table, "created_at", nullable=False, server_default=sa.text("now()"))
        op.alter_column(table, "updated_at", nullable=False, server_default=sa.text("now()"))


def downgrade() -> None:
    # Only remove columns introduced by this revision; original creation timestamps remain.
    for table in ("entity_aliases", "relation_assertions", "graph_evidence"):
        op.drop_column(table, "updated_at")
        op.drop_column(table, "created_at")
    for table in ("graph_extraction_runs", "canonical_entities", "entity_merge_history"):
        op.drop_column(table, "updated_at")
