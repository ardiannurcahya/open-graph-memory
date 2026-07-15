# ruff: noqa: E501, E701
"""Add hierarchical community analytics."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable/default-free additions avoid table rewrites. Existing snapshots are level 0.
    op.add_column("graph_analytics_runs", sa.Column("levels", sa.Integer(), nullable=True))
    op.add_column("graph_analytics_runs", sa.Column("algorithm_version", sa.String(100), nullable=True))
    op.add_column("graph_analytics_runs", sa.Column("config", postgresql.JSONB(), nullable=True))
    op.execute("UPDATE graph_analytics_runs SET levels = 1, algorithm_version = 'louvain-v1', config = '{}'::jsonb WHERE levels IS NULL")
    op.alter_column("graph_analytics_runs", "levels", nullable=False)
    op.alter_column("graph_analytics_runs", "algorithm_version", nullable=False)
    op.alter_column("graph_analytics_runs", "config", nullable=False)
    op.add_column("graph_analytics_memberships", sa.Column("level", sa.Integer(), nullable=True))
    op.execute("UPDATE graph_analytics_memberships SET level = 0 WHERE level IS NULL")
    op.alter_column("graph_analytics_memberships", "level", nullable=False)
    op.drop_constraint("graph_analytics_memberships_pkey", "graph_analytics_memberships", type_="primary")
    op.create_primary_key("graph_analytics_memberships_pkey", "graph_analytics_memberships", ["run_id", "entity_id", "level"])
    op.add_column("graph_analytics_communities", sa.Column("level", sa.Integer(), nullable=True))
    op.add_column("graph_analytics_communities", sa.Column("parent_community_id", sa.String(32), nullable=True))
    op.add_column("graph_analytics_communities", sa.Column("internal_edges", sa.Integer(), nullable=True))
    op.add_column("graph_analytics_communities", sa.Column("external_edges", sa.Integer(), nullable=True))
    op.add_column("graph_analytics_communities", sa.Column("density", sa.Float(), nullable=True))
    op.add_column("graph_analytics_communities", sa.Column("importance", sa.Float(), nullable=True))
    op.execute("UPDATE graph_analytics_communities SET level = 0, internal_edges = 0, external_edges = 0, density = 0, importance = 0 WHERE level IS NULL")
    for column in ("level", "internal_edges", "external_edges", "density", "importance"): op.alter_column("graph_analytics_communities", column, nullable=False)
    op.drop_constraint("graph_analytics_communities_pkey", "graph_analytics_communities", type_="primary")
    op.create_primary_key("graph_analytics_communities_pkey", "graph_analytics_communities", ["run_id", "community_id", "level"])
    for table in ("community_report_jobs", "community_reports"):
        op.add_column(table, sa.Column("level", sa.Integer(), nullable=True))
        op.execute(f"UPDATE {table} SET level = 0 WHERE level IS NULL")
        op.alter_column(table, "level", nullable=False)


def downgrade() -> None:
    raise NotImplementedError("hierarchical analytics downgrade is destructive")
