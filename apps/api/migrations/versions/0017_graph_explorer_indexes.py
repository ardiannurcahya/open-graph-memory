"""Add indexes for full graph explorer pagination."""

from collections.abc import Sequence

revision = "0017"
down_revision = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
