# ruff: noqa: E501
"""Add immutable PostgreSQL graph analytics snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "graph_analytics_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", sa.String(length=40), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("entity_count", sa.Integer(), nullable=False),
        sa.Column("relation_count", sa.Integer(), nullable=False),
        sa.Column("community_count", sa.Integer(), nullable=False),
        sa.Column("resolution", sa.Float(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "dataset_id", "snapshot_hash", name="uq_analytics_snapshot"),
    )
    op.create_index("ix_analytics_runs_latest", "graph_analytics_runs", ["project_id", "dataset_id", "created_at"])
    op.create_table(
        "graph_analytics_memberships",
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("graph_analytics_runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("entity_id", sa.String(length=64), sa.ForeignKey("canonical_entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("community_id", sa.String(length=32), nullable=False),
    )
    op.create_table(
        "graph_analytics_entity_metrics",
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("graph_analytics_runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("entity_id", sa.String(length=64), sa.ForeignKey("canonical_entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("degree", sa.Integer(), nullable=False),
        sa.Column("weighted_degree", sa.Float(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
    )
    op.create_table(
        "graph_analytics_communities",
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("graph_analytics_runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("community_id", sa.String(length=32), primary_key=True),
        sa.Column("entity_count", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("graph_analytics_communities")
    op.drop_table("graph_analytics_entity_metrics")
    op.drop_table("graph_analytics_memberships")
    op.drop_index("ix_analytics_runs_latest", table_name="graph_analytics_runs")
    op.drop_table("graph_analytics_runs")
