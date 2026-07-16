"""Remove obsolete embedding states."""

from collections.abc import Sequence

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENT_STATES = (
    "PENDING_UPLOAD",
    "UPLOADED",
    "STORAGE_FAILED",
    "QUEUED",
    "PARSING",
    "CHUNKING",
    "PERSISTING",
    "INDEXED",
    "FAILED",
    "CANCELLED",
    "STALE",
    "DELETING",
    "DELETE_FAILED",
)
INDEXING_STAGES = ("QUEUED", "READING", "PARSING", "CHUNKING", "PERSISTING", "COMPLETE")


def enum_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def replace_enum(
    name: str,
    columns: tuple[tuple[str, str], ...],
    values: tuple[str, ...],
    remap_embedding: bool = False,
) -> None:
    old_name = f"{name}_with_embedding"
    op.execute(f"ALTER TYPE {name} RENAME TO {old_name}")
    op.execute(f"CREATE TYPE {name} AS ENUM ({enum_values(values)})")
    for table, column in columns:
        value = f"{column}::text"
        if remap_embedding:
            value = f"CASE WHEN {value} = 'EMBEDDING' THEN 'PERSISTING' ELSE {value} END"
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {name} "
            f"USING ({value})::{name}"
        )
    op.execute(f"DROP TYPE {old_name}")


def upgrade() -> None:
    op.execute(
        "DELETE FROM indexing_stage_events embedding_event "
        "WHERE embedding_event.stage::text = 'EMBEDDING' AND EXISTS ("
        "SELECT 1 FROM indexing_stage_events persisting_event "
        "WHERE persisting_event.job_id = embedding_event.job_id "
        "AND persisting_event.attempt = embedding_event.attempt "
        "AND persisting_event.stage::text = 'PERSISTING')"
    )
    replace_enum(
        "document_status",
        (("documents", "status"),),
        DOCUMENT_STATES,
        remap_embedding=True,
    )
    replace_enum(
        "indexing_stage",
        (("indexing_jobs", "stage"), ("indexing_stage_events", "stage")),
        INDEXING_STAGES,
        remap_embedding=True,
    )


def downgrade() -> None:
    replace_enum(
        "document_status",
        (("documents", "status"),),
        DOCUMENT_STATES[:6] + ("EMBEDDING",) + DOCUMENT_STATES[6:],
    )
    replace_enum(
        "indexing_stage",
        (("indexing_jobs", "stage"), ("indexing_stage_events", "stage")),
        INDEXING_STAGES[:4] + ("EMBEDDING",) + INDEXING_STAGES[4:],
    )
