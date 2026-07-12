"""Add authoritative graph extraction persistence."""

from collections.abc import Sequence

from alembic import op
from app.graph_models import (  # noqa: E402
    CanonicalEntity,
    EntityAlias,
    EntityMergeHistory,
    GraphEvidence,
    GraphExtractionRun,
    RelationAssertion,
)

revision = "0006"
down_revision = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    GraphExtractionRun.__table__,
    CanonicalEntity.__table__,
    EntityAlias.__table__,
    RelationAssertion.__table__,
    GraphEvidence.__table__,
    EntityMergeHistory.__table__,
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        table.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(TABLES):
        table.drop(bind, checkfirst=True)
