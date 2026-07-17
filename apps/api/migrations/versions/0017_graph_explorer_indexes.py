"""Add indexes for full graph explorer pagination."""

from collections.abc import Sequence

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_entities_explorer_page",
        "canonical_entities",
        ["project_id", "dataset_id", "id"],
    )
    op.create_index(
        "ix_relations_explorer_page",
        "relation_assertions",
        ["project_id", "dataset_id", "id"],
    )
    op.create_index("ix_graph_evidence_entity", "graph_evidence", ["entity_id"])
    op.create_index("ix_graph_evidence_relation", "graph_evidence", ["relation_id"])


def downgrade() -> None:
    op.drop_index("ix_graph_evidence_relation", table_name="graph_evidence")
    op.drop_index("ix_graph_evidence_entity", table_name="graph_evidence")
    op.drop_index("ix_relations_explorer_page", table_name="relation_assertions")
    op.drop_index("ix_entities_explorer_page", table_name="canonical_entities")
