"""Add durable raw extraction, document consolidation, and alias evidence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    graph_run_columns = {
        column["name"] for column in inspector.get_columns("graph_extraction_runs")
    }
    if "raw_extraction" not in graph_run_columns:
        op.add_column(
            "graph_extraction_runs",
            sa.Column("raw_extraction", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    tables = set(inspector.get_table_names())
    if "graph_consolidation_runs" not in tables:
        op.create_table(
            "graph_consolidation_runs",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("project_id", sa.UUID(), nullable=False),
            sa.Column("dataset_id", sa.String(length=40), nullable=False),
            sa.Column("document_id", sa.String(length=40), nullable=False),
            sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
            sa.Column("extractor_version", sa.String(length=100), nullable=False),
            sa.Column("consolidation_version", sa.String(length=100), nullable=False),
            sa.Column("prompt_version", sa.String(length=100), nullable=False),
            sa.Column(
                "status",
                postgresql.ENUM(name="graph_run_status", create_type=False),
                nullable=False,
            ),
            sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "document_id",
                "snapshot_hash",
                "extractor_version",
                "consolidation_version",
                name="uq_graph_consolidation_input",
            ),
        )
    indexes = {index["name"] for index in inspector.get_indexes("graph_consolidation_runs")}
    if "ix_graph_consolidation_scope" not in indexes:
        op.create_index(
            "ix_graph_consolidation_scope",
            "graph_consolidation_runs",
            ["project_id", "dataset_id", "document_id"],
        )
    if "entity_alias_evidence" not in tables:
        op.create_table(
            "entity_alias_evidence",
            sa.Column("alias_id", sa.String(length=64), primary_key=True),
            sa.Column("evidence_id", sa.String(length=64), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["alias_id"], ["entity_aliases.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["evidence_id"], ["graph_evidence.id"], ondelete="CASCADE"),
        )


def downgrade() -> None:
    op.drop_table("entity_alias_evidence")
    op.drop_index("ix_graph_consolidation_scope", table_name="graph_consolidation_runs")
    op.drop_table("graph_consolidation_runs")
    op.drop_column("graph_extraction_runs", "raw_extraction")
