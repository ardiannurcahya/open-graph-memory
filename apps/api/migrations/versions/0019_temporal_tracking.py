"""Add temporal tracking to entities and relations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    entity_columns = {
        column["name"] for column in inspector.get_columns("canonical_entities")
    }
    if "valid_from" not in entity_columns:
        op.add_column(
            "canonical_entities",
            sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "valid_until" not in entity_columns:
        op.add_column(
            "canonical_entities",
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        )
    if "superseded_by" not in entity_columns:
        op.add_column(
            "canonical_entities",
            sa.Column("superseded_by", sa.String(length=64), nullable=True),
        )

    relation_columns = {
        column["name"] for column in inspector.get_columns("relation_assertions")
    }
    if "valid_from" not in relation_columns:
        op.add_column(
            "relation_assertions",
            sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "valid_until" not in relation_columns:
        op.add_column(
            "relation_assertions",
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        )
    if "superseded_by" not in relation_columns:
        op.add_column(
            "relation_assertions",
            sa.Column("superseded_by", sa.String(length=64), nullable=True),
        )

    entity_indexes = {
        index["name"] for index in inspector.get_indexes("canonical_entities")
    }
    if "ix_entities_temporal" not in entity_indexes:
        op.create_index(
            "ix_entities_temporal",
            "canonical_entities",
            ["project_id", "dataset_id", "valid_until"],
            postgresql_where=sa.text("valid_until IS NULL"),
        )

    relation_indexes = {
        index["name"] for index in inspector.get_indexes("relation_assertions")
    }
    if "ix_relations_temporal" not in relation_indexes:
        op.create_index(
            "ix_relations_temporal",
            "relation_assertions",
            ["project_id", "dataset_id", "valid_until"],
            postgresql_where=sa.text("valid_until IS NULL"),
        )


def downgrade() -> None:
    op.drop_index("ix_relations_temporal", table_name="relation_assertions")
    op.drop_index("ix_entities_temporal", table_name="canonical_entities")
    op.drop_column("relation_assertions", "superseded_by")
    op.drop_column("relation_assertions", "valid_until")
    op.drop_column("relation_assertions", "valid_from")
    op.drop_column("canonical_entities", "superseded_by")
    op.drop_column("canonical_entities", "valid_until")
    op.drop_column("canonical_entities", "valid_from")
