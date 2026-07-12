"""Add durable graph extraction jobs and outbox."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.graph_models import GraphExtractionJob, GraphExtractionOutbox  # noqa: E402

revision = "0007"
down_revision = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    GraphExtractionJob.__table__.create(bind, checkfirst=True)
    GraphExtractionOutbox.__table__.create(bind, checkfirst=True)
    op.add_column("documents", sa.Column("graph_stage", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "graph_stage")
    bind = op.get_bind()
    GraphExtractionOutbox.__table__.drop(bind, checkfirst=True)
    GraphExtractionJob.__table__.drop(bind, checkfirst=True)
