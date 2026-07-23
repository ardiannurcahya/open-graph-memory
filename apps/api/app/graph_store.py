"""PostgreSQL-native graph store (no-op projection, data lives in canonical_entities/relation_assertions/graph_evidence)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import engine

if TYPE_CHECKING:
    from app.retrieval import GraphEvidence


@dataclass(frozen=True)
class GraphProjection:
    project_id: str
    dataset_id: str
    entity_id: str
    canonical_name: str
    entity_type: str
    version: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RelationProjection:
    project_id: str
    dataset_id: str
    relation_id: str
    source_id: str
    target_id: str
    relation_type: str
    extractor_version: str
    confidence: float
    review_state: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ChunkProjection:
    project_id: str
    dataset_id: str
    document_id: str
    chunk_id: str
    pipeline_version: str
    created_at: str


@dataclass(frozen=True)
class EvidenceProjection:
    project_id: str
    dataset_id: str
    evidence_id: str
    document_id: str
    chunk_id: str
    entity_id: str | None
    relation_id: str | None
    run_id: str
    quote: str
    confidence: float
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DocumentProjection:
    project_id: str
    dataset_id: str
    document_id: str
    document_created_at: str
    document_updated_at: str
    chunks: tuple[ChunkProjection, ...]
    entities: tuple[GraphProjection, ...]
    relations: tuple[RelationProjection, ...]
    evidence: tuple[EvidenceProjection, ...]


class GraphStore:
    """PostgreSQL-native graph store.

    Graph data (canonical_entities, relation_assertions, graph_evidence) already
    lives in PostgreSQL. The old Neo4j projection is no longer needed. This
    implementation satisfies the GraphStore protocol with no-op projections and
    PostgreSQL-backed traversal.
    """

    async def bootstrap(self) -> None:
        """No-op: tables are managed by Alembic migrations."""

    async def project_document(self, projection: DocumentProjection) -> None:
        """No-op: data is already in PostgreSQL tables."""

    async def reconcile_dataset(self, project_id: str, dataset_id: str) -> None:
        """No-op: reconciliation handled by graph consolidation pipeline."""

    async def delete_document(self, project_id: str, dataset_id: str, document_id: str) -> None:
        """No-op: cleanup handled by graph_cleanup_outbox."""

    async def traverse(
        self,
        project_id: str,
        dataset_id: str,
        seed_chunk_ids: list[str],
        seed_entity_names: list[str],
        max_depth: int,
        fanout: int,
        seed_limit: int,
    ) -> list["GraphEvidence"]:
        """Traverse the graph from seed chunks/entities and return evidence."""
        from app.graph_models import CanonicalEntity, GraphEvidence as GraphEvidenceModel

        factory = async_sessionmaker(engine, expire_on_commit=False)
        evidence: list[GraphEvidence] = []

        async with factory() as db:
            # Resolve seed entity names to IDs
            seed_entity_ids: list[str] = []
            if seed_entity_names:
                entities = list(
                    await db.scalars(
                        select(CanonicalEntity).where(
                            CanonicalEntity.project_id == project_id,
                            CanonicalEntity.dataset_id == dataset_id,
                            CanonicalEntity.canonical_name.in_(seed_entity_names),
                        )
                    )
                )
                seed_entity_ids = [e.id for e in entities]

            # Collect evidence from seed chunks
            if seed_chunk_ids:
                chunk_evidence = list(
                    await db.scalars(
                        select(GraphEvidenceModel).where(
                            GraphEvidenceModel.project_id == project_id,
                            GraphEvidenceModel.dataset_id == dataset_id,
                            GraphEvidenceModel.chunk_id.in_(seed_chunk_ids),
                        )
                    )
                )
                evidence.extend(chunk_evidence[:seed_limit])

            # Collect evidence from seed entities
            if seed_entity_ids:
                entity_evidence = list(
                    await db.scalars(
                        select(GraphEvidenceModel).where(
                            GraphEvidenceModel.project_id == project_id,
                            GraphEvidenceModel.dataset_id == dataset_id,
                            GraphEvidenceModel.entity_id.in_(seed_entity_ids),
                        )
                    )
                )
                seen = {e.id for e in evidence}
                for ev in entity_evidence:
                    if ev.id not in seen and len(evidence) < seed_limit:
                        evidence.append(ev)
                        seen.add(ev.id)

        return evidence
