"""Bounded traversal, ranking, and view assembly for graph inspection."""

import re
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.auth import ProjectContext
from app.graph.helpers import supported_entity, supported_relation
from app.graph.models import CanonicalEntity, GraphEvidence, RelationAssertion
from app.graph.schemas import Citation, EntityView, RelationView
from app.models import Chunk

MAX_NEIGHBORS = 100


MAX_NODES = 200


MAX_PATH_DEPTH = 4


MAX_PATH_RELATIONS = 200


MAX_SUBGRAPH_DEPTH = 2


MAX_SUBGRAPH_RELATIONS = 400


MAX_EXPLORER_NODES = 3_000


MAX_EXPLORER_RELATIONS = 5_000


MAX_RELATION_CITATIONS = 20


GRAPH_CANDIDATE_LIMIT = 2_000


LOW_SIGNAL_ENTITY_TYPES = {
    "access_date",
    "accepted_date",
    "article_number",
    "contract",
    "doi",
    "iteration_limit",
    "journal_volume",
    "numeric value",
    "publication_date",
    "publication_year",
    "received_date",
    "revised_date",
    "sample size",
    "value",
}


def source_location(metadata: dict[str, object]) -> dict[str, int] | None:
    location = {
        key: value
        for key, value in metadata.items()
        if key in {"page_number", "record_number", "segment_part"} and isinstance(value, int)
    }
    return location or None


def entity_view(item: CanonicalEntity) -> EntityView:
    return EntityView.model_validate(item, from_attributes=True)


def temporal_filter(
    as_of: datetime | None = None,
    include_history: bool = False,
    entity: bool = True,
) -> ColumnElement[bool]:
    """Return a filter clause for temporal queries.

    - as_of=None, include_history=False: only current facts (valid_until IS NULL)
    - as_of=timestamp: facts valid at that point in time
    - include_history=True: all facts regardless of validity
    """
    from sqlalchemy import literal

    if include_history:
        return literal(True)
    if as_of is not None:
        if entity:
            return (CanonicalEntity.valid_from <= as_of) & (
                (CanonicalEntity.valid_until.is_(None)) | (CanonicalEntity.valid_until > as_of)
            )
        return (RelationAssertion.valid_from <= as_of) & (
            (RelationAssertion.valid_until.is_(None)) | (RelationAssertion.valid_until > as_of)
        )
    if entity:
        return CanonicalEntity.valid_until.is_(None) & CanonicalEntity.superseded_by.is_(None)
    return RelationAssertion.valid_until.is_(None) & RelationAssertion.superseded_by.is_(None)


def low_signal_entity(name: str, entity_type: str) -> bool:
    normalized_type = entity_type.strip().lower()
    normalized_name = name.strip().lower()
    if normalized_type in LOW_SIGNAL_ENTITY_TYPES:
        return True
    if normalized_type.endswith("_date") or normalized_type.endswith("_year"):
        return True
    if re.fullmatch(r"[\d\s.,%×x/–\-]+", normalized_name):
        return True
    return False


def rank_graph_entities(
    entities: list[CanonicalEntity], degree: dict[str, int], limit: int
) -> list[CanonicalEntity]:
    useful = [
        item for item in entities if not low_signal_entity(item.canonical_name, item.entity_type)
    ]
    fallback = useful or entities
    return sorted(
        fallback,
        key=lambda item: (
            -(degree.get(item.id, 0)),
            low_signal_entity(item.canonical_name, item.entity_type),
            item.entity_type.lower(),
            item.canonical_name.lower(),
            item.id,
        ),
    )[:limit]


async def citations(db: AsyncSession, relation_id: str) -> list[Citation]:
    rows = await db.execute(
        select(
            GraphEvidence.dataset_id,
            GraphEvidence.document_id,
            GraphEvidence.chunk_id,
            GraphEvidence.quote,
            Chunk.metadata_,
        )
        .join(Chunk, Chunk.id == GraphEvidence.chunk_id)
        .where(GraphEvidence.relation_id == relation_id)
        .order_by(GraphEvidence.id)
        .limit(MAX_RELATION_CITATIONS)
    )
    return [
        Citation(
            dataset_id=r[0],
            document_id=r[1],
            chunk_id=r[2],
            quote=r[3],
            source_location=source_location(r[4]),
        )
        for r in rows
    ]


async def relation_view(db: AsyncSession, item: RelationAssertion) -> RelationView:
    return RelationView(
        id=item.id,
        dataset_id=item.dataset_id,
        source_entity_id=item.source_entity_id,
        target_entity_id=item.target_entity_id,
        relation_type=item.relation_type,
        confidence=item.confidence,
        extractor_version=item.extractor_version,
        review_state=item.review_state,
        valid_from=item.valid_from,
        valid_until=item.valid_until,
        superseded_by=item.superseded_by,
        citations=await citations(db, item.id),
    )


async def scoped_entity(
    db: AsyncSession, project: ProjectContext, entity_id: str
) -> CanonicalEntity:
    item = await db.scalar(
        select(CanonicalEntity).where(
            CanonicalEntity.id == entity_id,
            CanonicalEntity.project_id == project.project_id,
            supported_entity(),
        )
    )
    if item is None:
        raise HTTPException(404, "entity not found")
    return item


async def scoped_dataset_entity(
    db: AsyncSession, project: ProjectContext, dataset_id: str, entity_id: str
) -> CanonicalEntity:
    item = await db.scalar(
        select(CanonicalEntity).where(
            CanonicalEntity.id == entity_id,
            CanonicalEntity.project_id == project.project_id,
            CanonicalEntity.dataset_id == dataset_id,
            supported_entity(),
        )
    )
    if item is None:
        raise HTTPException(404, "entity not found")
    return item


async def bounded_walk(
    db: AsyncSession,
    project_id: UUID,
    dataset_id: str,
    root: CanonicalEntity,
    depth: int,
    node_limit: int,
    relation_limit: int,
    target_id: str | None = None,
) -> tuple[dict[str, CanonicalEntity], dict[str, RelationAssertion], dict[str, tuple[str, str]]]:
    entities = {root.id: root}
    relations: dict[str, RelationAssertion] = {}
    parents: dict[str, tuple[str, str]] = {}
    frontier = {root.id}
    for _ in range(depth):
        if not frontier or len(entities) >= node_limit or len(relations) >= relation_limit:
            break
        filters = [
            RelationAssertion.project_id == project_id,
            RelationAssertion.dataset_id == dataset_id,
            or_(
                RelationAssertion.source_entity_id.in_(frontier),
                RelationAssertion.target_entity_id.in_(frontier),
            ),
            supported_relation(),
            temporal_filter(entity=False),
        ]
        if relations:
            filters.append(RelationAssertion.id.not_in(relations))
        rows = list(
            await db.scalars(
                select(RelationAssertion)
                .where(*filters)
                .order_by(RelationAssertion.id)
                .limit(relation_limit - len(relations))
            )
        )
        candidate_ids = {
            endpoint
            for relation in rows
            for endpoint in (relation.source_entity_id, relation.target_entity_id)
            if endpoint not in entities
        }
        candidates = {
            item.id: item
            for item in await db.scalars(
                select(CanonicalEntity).where(
                    CanonicalEntity.id.in_(candidate_ids),
                    CanonicalEntity.project_id == project_id,
                    CanonicalEntity.dataset_id == dataset_id,
                    supported_entity(),
                    temporal_filter(entity=True),
                )
            )
        }
        next_frontier: set[str] = set()
        for relation in rows:
            source_id = relation.source_entity_id
            target_entity_id = relation.target_entity_id
            if source_id not in entities and source_id not in candidates:
                continue
            if target_entity_id not in entities and target_entity_id not in candidates:
                continue
            new_id = target_entity_id if source_id in frontier else source_id
            previous_id = source_id if source_id in frontier else target_entity_id
            if new_id not in entities:
                if len(entities) >= node_limit:
                    continue
                entities[new_id] = candidates[new_id]
                parents[new_id] = (previous_id, relation.id)
                next_frontier.add(new_id)
            relations[relation.id] = relation
            if new_id == target_id:
                return entities, relations, parents
        frontier = next_frontier
    return entities, relations, parents


def path_ids(
    source_id: str, target_id: str, parents: dict[str, tuple[str, str]]
) -> tuple[list[str], list[str]]:
    if source_id == target_id:
        return [source_id], []
    if target_id not in parents:
        return [], []
    entities = [target_id]
    relations = []
    current = target_id
    while current != source_id:
        current, relation_id = parents[current]
        entities.append(current)
        relations.append(relation_id)
    entities.reverse()
    relations.reverse()
    return entities, relations
