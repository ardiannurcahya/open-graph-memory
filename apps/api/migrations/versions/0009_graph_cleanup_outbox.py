"""Add durable graph projection cleanup outbox."""

from collections.abc import Sequence

from alembic import op
from app.graph_models import GraphCleanupOutbox  # noqa: E402

revision = "0009"
down_revision = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    GraphCleanupOutbox.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    GraphCleanupOutbox.__table__.drop(op.get_bind(), checkfirst=True)
