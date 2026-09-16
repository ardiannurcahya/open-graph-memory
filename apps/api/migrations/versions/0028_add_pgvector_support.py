"""Add pgvector extension and embedding columns with HNSW indexes.

Revision ID: 0028
Revises: 0027
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0028"
down_revision = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enable pgvector extension in PostgreSQL
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Add embedding vector(1536) to chunks table
    op.add_column("chunks", sa.Column("embedding", Vector(1536), nullable=True))

    # 3. Create HNSW index on chunks.embedding
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw "
        "ON chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # 4. Add embedding vector(1536) to agent_memory_episodes table
    op.add_column("agent_memory_episodes", sa.Column("embedding", Vector(1536), nullable=True))

    # 5. Create HNSW index on agent_memory_episodes.embedding
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_episodes_embedding_hnsw "
        "ON agent_memory_episodes USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_memory_episodes_embedding_hnsw")
    op.drop_column("agent_memory_episodes", "embedding")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.drop_column("chunks", "embedding")
