"""PostgreSQL-native graph store backed by canonical graph tables."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.db import engine
from app.graph_models import CanonicalEntity, RelationAssertion, ReviewState
from app.graph_models import GraphEvidence as GraphEvidenceModel
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
    ) -> list[GraphEvidence]:
        """Traverse the graph from seed chunks/entities and return evidence."""
        factory = async_sessionmaker(engine, expire_on_commit=False)
        if max_depth not in {1, 2}:
            raise ValueError("graph depth must be 1 or 2")
        if fanout < 1 or seed_limit < 1:
            return []

        async with factory() as db:
            # Resolve initial nodes from names and chunk evidence.  All subsequent
            # queries remain project/dataset scoped; PostgreSQL is authoritative.
            seed_entity_ids: set[str] = set()
            if seed_entity_names:
                entities = list(
                    await db.scalars(
                        select(CanonicalEntity).where(
                            CanonicalEntity.project_id == project_id,
                            CanonicalEntity.dataset_id == dataset_id,
                            CanonicalEntity.canonical_name.in_(seed_entity_names),
                            CanonicalEntity.valid_until.is_(None),
                            CanonicalEntity.superseded_by.is_(None),
                            supported_entity_subject(),
                        )
                    )
                )
                seed_entity_ids.update(entity.id for entity in entities)

            seed_evidence: list[GraphEvidenceModel] = []
            if seed_chunk_ids:
                seed_evidence.extend(
                    await db.scalars(
                        select(GraphEvidenceModel).where(
                            GraphEvidenceModel.project_id == project_id,
                            GraphEvidenceModel.dataset_id == dataset_id,
                            GraphEvidenceModel.chunk_id.in_(seed_chunk_ids),
                            current_evidence_subject(project_id, dataset_id),
                        )
                    )
                )
                seed_entity_ids.update(item.entity_id for item in seed_evidence if item.entity_id)
                seed_relation_ids = {
                    item.relation_id for item in seed_evidence if item.relation_id
                }
                if seed_relation_ids:
                    relations = list(
                        await db.scalars(
                            select(RelationAssertion).where(
                                RelationAssertion.id.in_(seed_relation_ids),
                                RelationAssertion.project_id == project_id,
                                RelationAssertion.dataset_id == dataset_id,
                                RelationAssertion.valid_until.is_(None),
                                RelationAssertion.superseded_by.is_(None),
                                supported_relation_subject(),
                            )
                        )
                    )
                    for relation in relations:
                        seed_entity_ids.update(
                            (relation.source_entity_id, relation.target_entity_id)
                        )

            seed_entity_ids = await supported_entity_ids(
                db, project_id, dataset_id, seed_entity_ids
            )
            paths: dict[str, tuple[str, ...]] = {
                entity_id: (entity_id,) for entity_id in seed_entity_ids
            }
            frontier = set(seed_entity_ids)
            relation_ids: set[str] = set()
            for _depth in range(max_depth):
                if not frontier:
                    break
                relations = list(
                    await db.scalars(
                        select(RelationAssertion)
                        .where(
                            RelationAssertion.project_id == project_id,
                            RelationAssertion.dataset_id == dataset_id,
                            RelationAssertion.valid_until.is_(None),
                            RelationAssertion.superseded_by.is_(None),
                            supported_relation_subject(),
                            or_(
                                RelationAssertion.source_entity_id.in_(frontier),
                                RelationAssertion.target_entity_id.in_(frontier),
                            ),
                        )
                        .order_by(RelationAssertion.confidence.desc(), RelationAssertion.id)
                        .limit(len(frontier) * fanout)
                    )
                )
                endpoint_ids = {
                    endpoint
                    for relation in relations
                    for endpoint in (relation.source_entity_id, relation.target_entity_id)
                }
                supported_endpoints = await supported_entity_ids(
                    db, project_id, dataset_id, endpoint_ids
                )
                next_frontier: set[str] = set()
                for relation in relations:
                    # A relation can match any member of a multi-node frontier.
                    # Preserve the actual matched endpoint rather than assigning an
                    # arbitrary frontier node as the provenance parent.
                    matched_id = (
                        relation.source_entity_id
                        if relation.source_entity_id in frontier
                        else relation.target_entity_id
                    )
                    entity_id = (
                        relation.target_entity_id
                        if matched_id == relation.source_entity_id
                        else relation.source_entity_id
                    )
                    if entity_id not in supported_endpoints:
                        continue
                    relation_ids.add(relation.id)
                    if entity_id not in paths:
                        paths[entity_id] = paths[matched_id] + (relation.id, entity_id)
                        next_frontier.add(entity_id)
                frontier = next_frontier
            entity_ids = set(paths)
            statement = (
                select(GraphEvidenceModel)
                .where(
                    GraphEvidenceModel.project_id == project_id,
                    GraphEvidenceModel.dataset_id == dataset_id,
                    current_evidence_subject(project_id, dataset_id),
                    or_(
                        GraphEvidenceModel.chunk_id.in_(seed_chunk_ids or ["__none__"]),
                        GraphEvidenceModel.entity_id.in_(entity_ids or ["__none__"]),
                        GraphEvidenceModel.relation_id.in_(relation_ids or ["__none__"]),
                    ),
                )
                .order_by(GraphEvidenceModel.confidence.desc(), GraphEvidenceModel.id)
                .limit(seed_limit)
            )
            rows = list(await db.scalars(statement))
            return [
                GraphEvidence(
                    chunk_id=item.chunk_id,
                    score=item.confidence,
                    path=paths.get(item.entity_id or "", (item.chunk_id,)),
                    entity_ids=(item.entity_id,) if item.entity_id else (),
                    relation_ids=(item.relation_id,) if item.relation_id else (),
                    evidence_chunk_ids=(item.chunk_id,),
                )
                for item in rows
            ]


def supported_relation_subject() -> ColumnElement[bool]:
    """Require relation evidence and exclude reviewer-rejected relations."""
    return (RelationAssertion.review_state != ReviewState.REJECTED) & exists().where(
        GraphEvidenceModel.relation_id == RelationAssertion.id
    )


def supported_entity_subject() -> ColumnElement[bool]:
    """Require direct entity evidence or an endpoint of a cited relation."""
    cited_endpoint = exists().where(
        GraphEvidenceModel.relation_id == RelationAssertion.id,
        RelationAssertion.review_state != ReviewState.REJECTED,
        or_(
            RelationAssertion.source_entity_id == CanonicalEntity.id,
            RelationAssertion.target_entity_id == CanonicalEntity.id,
        ),
    )
    return or_(
        exists().where(GraphEvidenceModel.entity_id == CanonicalEntity.id), cited_endpoint
    )


async def supported_entity_ids(
    db: AsyncSession,
    project_id: str,
    dataset_id: str,
    entity_ids: set[str],
) -> set[str]:
    """Return only current, scoped, supported entity IDs for traversal frontier use."""
    if not entity_ids:
        return set()
    rows = await db.scalars(
        select(CanonicalEntity.id).where(
            CanonicalEntity.id.in_(entity_ids),
            CanonicalEntity.project_id == project_id,
            CanonicalEntity.dataset_id == dataset_id,
            CanonicalEntity.valid_until.is_(None),
            CanonicalEntity.superseded_by.is_(None),
            supported_entity_subject(),
        )
    )
    return set(rows)


def current_evidence_subject(project_id: str, dataset_id: str) -> ColumnElement[bool]:
    """Restrict evidence to a current, non-superseded scoped graph subject."""
    return or_(
        and_(
            GraphEvidenceModel.entity_id.is_not(None),
            exists().where(
                CanonicalEntity.id == GraphEvidenceModel.entity_id,
                CanonicalEntity.project_id == project_id,
                CanonicalEntity.dataset_id == dataset_id,
                CanonicalEntity.valid_until.is_(None),
                CanonicalEntity.superseded_by.is_(None),
            ),
        ),
        and_(
            GraphEvidenceModel.relation_id.is_not(None),
            exists().where(
                RelationAssertion.id == GraphEvidenceModel.relation_id,
                RelationAssertion.project_id == project_id,
                RelationAssertion.dataset_id == dataset_id,
                RelationAssertion.valid_until.is_(None),
                RelationAssertion.superseded_by.is_(None),
            ),
        ),
    )
