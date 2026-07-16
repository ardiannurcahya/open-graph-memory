"""Bounded, PostgreSQL-authoritative graph inspection and review API."""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.auth import ProjectContext, require_project
from app.datasets import owned
from app.dependencies import get_session
from app.graph_analytics import refresh_dataset_analytics, snapshot_hash
from app.graph_models import (
    CanonicalEntity,
    EntityAlias,
    GraphEvidence,
    GraphExtractionJob,
    GraphExtractionRun,
    RelationAssertion,
    ReviewState,
)
from app.models import (
    Chunk,
    GraphAnalyticsCommunity,
    GraphAnalyticsEntityMetric,
    GraphAnalyticsMembership,
    GraphAnalyticsRun,
)

router = APIRouter(prefix="/v1", tags=["graph"])
Project = Annotated[ProjectContext, Depends(require_project)]
Db = Annotated[AsyncSession, Depends(get_session)]
MAX_NEIGHBORS = 100
MAX_NODES = 200
MAX_PATH_DEPTH = 4
MAX_PATH_RELATIONS = 200
MAX_SUBGRAPH_DEPTH = 2
MAX_SUBGRAPH_RELATIONS = 400
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


class Citation(BaseModel):
    dataset_id: str
    document_id: str
    chunk_id: str
    quote: str
    source_location: dict[str, int] | None = None


def source_location(metadata: dict[str, object]) -> dict[str, int] | None:
    location = {
        key: value
        for key, value in metadata.items()
        if key in {"page_number", "record_number", "segment_part"} and isinstance(value, int)
    }
    return location or None


class EntityView(BaseModel):
    id: str
    dataset_id: str
    canonical_name: str
    entity_type: str
    confidence: float
    version: int
    review_state: ReviewState


class RelationView(BaseModel):
    id: str
    dataset_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    confidence: float
    extractor_version: str
    review_state: ReviewState
    citations: list[Citation] = Field(default_factory=list)


class NeighborView(BaseModel):
    relation: RelationView
    entity: EntityView


class GraphSummary(BaseModel):
    dataset_id: str
    entity_count: int
    relation_count: int
    nodes: list[EntityView]
    relations: list[RelationView]


class PathView(BaseModel):
    dataset_id: str
    source_entity_id: str
    target_entity_id: str
    found: bool
    hops: int
    nodes: list[EntityView]
    relations: list[RelationView]


class SubgraphView(BaseModel):
    dataset_id: str
    root_entity_id: str
    depth: int
    nodes: list[EntityView]
    relations: list[RelationView]


class EvidenceView(Citation):
    id: str
    run_id: str
    entity_id: str | None
    relation_id: str | None
    confidence: float
    start_offset: int | None
    end_offset: int | None


class RunView(BaseModel):
    id: str
    dataset_id: str
    document_id: str
    chunk_id: str
    status: str
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    ontology_version: str | None
    error_message: str | None
    created_at: datetime | None
    completed_at: datetime | None


class JobView(BaseModel):
    id: str
    dataset_id: str
    document_id: str
    status: str
    attempt: int
    max_attempts: int
    error_message: str | None
    provider: str
    model: str
    extractor_version: str
    created_at: datetime | None
    updated_at: datetime | None


class ReviewInput(BaseModel):
    review_state: ReviewState


class AnalyticsRunView(BaseModel):
    id: str
    dataset_id: str
    snapshot_hash: str
    entity_count: int
    relation_count: int
    community_count: int
    levels: int
    algorithm_version: str


class ExplorerAnalyticsView(AnalyticsRunView):
    created_at: datetime | None
    stale: bool


class ExplorerStats(BaseModel):
    entity_count: int
    relation_count: int
    density: float


class ExplorerNode(BaseModel):
    id: str
    canonical_name: str
    entity_type: str
    community_id: str | None
    degree: int
    weighted_degree: float
    importance: float


class ExplorerRelation(BaseModel):
    id: str
    source: str
    target: str
    type: str
    weight: float
    confidence: float


class ExplorerCommunity(BaseModel):
    id: str
    entity_count: int
    parent_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)
    internal_edges: int = 0
    external_edges: int = 0
    density: float = 0.0
    importance: float = 0.0


class ExplorerView(BaseModel):
    dataset_id: str
    community_level: int = 0
    available_levels: list[int] = Field(default_factory=list)
    analytics: ExplorerAnalyticsView | None
    refresh_required: bool
    stats: ExplorerStats
    nodes: list[ExplorerNode]
    relations: list[ExplorerRelation]
    communities: list[ExplorerCommunity]


def entity_view(item: CanonicalEntity) -> EntityView:
    return EntityView.model_validate(item, from_attributes=True)


def supported_relation() -> ColumnElement[bool]:
    """Relation needs authoritative citation and must not be rejected."""
    return (RelationAssertion.review_state != ReviewState.REJECTED) & exists().where(
        GraphEvidence.relation_id == RelationAssertion.id
    )


def supported_entity() -> ColumnElement[bool]:
    """Entity needs direct evidence or endpoint of cited relation."""
    cited_endpoint = exists().where(
        GraphEvidence.relation_id == RelationAssertion.id,
        RelationAssertion.review_state != ReviewState.REJECTED,
        or_(
            RelationAssertion.source_entity_id == CanonicalEntity.id,
            RelationAssertion.target_entity_id == CanonicalEntity.id,
        ),
    )
    return or_(exists().where(GraphEvidence.entity_id == CanonicalEntity.id), cited_endpoint)


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


@router.get("/entities/{entity_id}", response_model=EntityView)
async def get_entity(
    entity_id: str,
    project: Project,
    db: Db,
) -> EntityView:
    return entity_view(await scoped_entity(db, project, entity_id))


@router.get("/datasets/{dataset_id}/entities/search", response_model=list[EntityView])
async def search_entities(
    dataset_id: str,
    project: Project,
    db: Db,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    entity_type: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_NEIGHBORS)] = 25,
) -> list[EntityView]:
    await owned(db, project, dataset_id)
    term = q.strip()
    if not term:
        raise HTTPException(422, "search query must not be blank")
    alias_match = exists().where(
        EntityAlias.entity_id == CanonicalEntity.id,
        EntityAlias.project_id == project.project_id,
        EntityAlias.dataset_id == dataset_id,
        func.lower(EntityAlias.alias).contains(term.lower(), autoescape=True),
    )
    filters = [
        CanonicalEntity.project_id == project.project_id,
        CanonicalEntity.dataset_id == dataset_id,
        or_(
            func.lower(CanonicalEntity.canonical_name).contains(term.lower(), autoescape=True),
            alias_match,
        ),
        supported_entity(),
    ]
    if entity_type is not None:
        filters.append(func.lower(CanonicalEntity.entity_type) == entity_type.strip().lower())
    rows = list(
        await db.scalars(
            select(CanonicalEntity)
            .where(*filters)
            .order_by(
                (func.lower(CanonicalEntity.canonical_name) == term.lower()).desc(),
                CanonicalEntity.confidence.desc(),
                CanonicalEntity.canonical_name,
                CanonicalEntity.id,
            )
            .limit(limit)
        )
    )
    return [entity_view(item) for item in rows]


@router.get("/datasets/{dataset_id}/graph/path", response_model=PathView)
async def path(
    dataset_id: str,
    project: Project,
    db: Db,
    source_entity_id: str,
    target_entity_id: str,
    max_depth: Annotated[int, Query(ge=1, le=MAX_PATH_DEPTH)] = 3,
    relation_limit: Annotated[int, Query(ge=1, le=MAX_PATH_RELATIONS)] = 100,
) -> PathView:
    await owned(db, project, dataset_id)
    source = await scoped_dataset_entity(db, project, dataset_id, source_entity_id)
    await scoped_dataset_entity(db, project, dataset_id, target_entity_id)
    entities, relations, parents = await bounded_walk(
        db,
        project.project_id,
        dataset_id,
        source,
        max_depth,
        MAX_NODES,
        relation_limit,
        target_entity_id,
    )
    entity_ids, relation_ids = path_ids(source_entity_id, target_entity_id, parents)
    return PathView(
        dataset_id=dataset_id,
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        found=bool(entity_ids),
        hops=len(relation_ids),
        nodes=[entity_view(entities[item_id]) for item_id in entity_ids],
        relations=[await relation_view(db, relations[item_id]) for item_id in relation_ids],
    )


@router.get("/datasets/{dataset_id}/graph/subgraph", response_model=SubgraphView)
async def subgraph(
    dataset_id: str,
    project: Project,
    db: Db,
    entity_id: str,
    depth: Annotated[int, Query(ge=0, le=MAX_SUBGRAPH_DEPTH)] = 1,
    node_limit: Annotated[int, Query(ge=1, le=MAX_NODES)] = 100,
    relation_limit: Annotated[int, Query(ge=1, le=MAX_SUBGRAPH_RELATIONS)] = 200,
) -> SubgraphView:
    await owned(db, project, dataset_id)
    root = await scoped_dataset_entity(db, project, dataset_id, entity_id)
    entities, relations, _ = await bounded_walk(
        db,
        project.project_id,
        dataset_id,
        root,
        depth,
        node_limit,
        relation_limit,
    )
    included = set(entities)
    relation_rows = [
        item
        for item in relations.values()
        if item.source_entity_id in included and item.target_entity_id in included
    ]
    return SubgraphView(
        dataset_id=dataset_id,
        root_entity_id=entity_id,
        depth=depth,
        nodes=[entity_view(item) for item in entities.values()],
        relations=[await relation_view(db, item) for item in relation_rows],
    )


@router.get("/entities/{entity_id}/neighbors", response_model=list[NeighborView])
async def neighbors(
    entity_id: str,
    project: Project,
    db: Db,
    limit: int = Query(25, ge=1, le=MAX_NEIGHBORS),
) -> list[NeighborView]:
    entity = await scoped_entity(db, project, entity_id)
    rows = list(
        await db.scalars(
            select(RelationAssertion)
            .where(
                RelationAssertion.project_id == project.project_id,
                RelationAssertion.dataset_id == entity.dataset_id,
                (RelationAssertion.source_entity_id == entity_id)
                | (RelationAssertion.target_entity_id == entity_id),
                supported_relation(),
            )
            .order_by(RelationAssertion.id)
            .limit(limit)
        )
    )
    result = []
    for relation in rows:
        other_id = (
            relation.target_entity_id
            if relation.source_entity_id == entity_id
            else relation.source_entity_id
        )
        other = await db.scalar(
            select(CanonicalEntity).where(
                CanonicalEntity.id == other_id,
                CanonicalEntity.project_id == project.project_id,
                supported_entity(),
            )
        )
        if other is not None:
            result.append(
                NeighborView(relation=await relation_view(db, relation), entity=entity_view(other))
            )
    return result


@router.post("/datasets/{dataset_id}/analytics/refresh", response_model=AnalyticsRunView)
async def refresh_analytics(dataset_id: str, project: Project, db: Db) -> AnalyticsRunView:
    await owned(db, project, dataset_id)
    try:
        run = await refresh_dataset_analytics(db, project.project_id, dataset_id)
        await db.commit()
    except ValueError as error:
        await db.rollback()
        raise HTTPException(422, str(error)) from error
    return AnalyticsRunView.model_validate(run, from_attributes=True)


@router.get("/datasets/{dataset_id}/graph", response_model=GraphSummary)
async def graph(
    dataset_id: str,
    project: Project,
    db: Db,
    limit: int = Query(100, ge=1, le=MAX_NODES),
    depth: int = Query(1, ge=0, le=1),
) -> GraphSummary:
    await owned(db, project, dataset_id)
    candidate_entities = list(
        await db.scalars(
            select(CanonicalEntity)
            .where(
                CanonicalEntity.project_id == project.project_id,
                CanonicalEntity.dataset_id == dataset_id,
                supported_entity(),
            )
            .order_by(CanonicalEntity.canonical_name)
            .limit(GRAPH_CANDIDATE_LIMIT)
        )
    )
    degree_rows = await db.execute(
        select(RelationAssertion.source_entity_id, func.count())
        .where(
            RelationAssertion.project_id == project.project_id,
            RelationAssertion.dataset_id == dataset_id,
            supported_relation(),
        )
        .group_by(RelationAssertion.source_entity_id)
    )
    degree = {str(entity_id): int(count) for entity_id, count in degree_rows}
    target_degree_rows = await db.execute(
        select(RelationAssertion.target_entity_id, func.count())
        .where(
            RelationAssertion.project_id == project.project_id,
            RelationAssertion.dataset_id == dataset_id,
            supported_relation(),
        )
        .group_by(RelationAssertion.target_entity_id)
    )
    for entity_id, count in target_degree_rows:
        degree[str(entity_id)] = degree.get(str(entity_id), 0) + int(count)
    entities = rank_graph_entities(candidate_entities, degree, limit)
    entity_ids = [item.id for item in entities]
    relations = (
        []
        if depth == 0 or not entity_ids
        else list(
            await db.scalars(
                select(RelationAssertion)
                .where(
                    RelationAssertion.project_id == project.project_id,
                    RelationAssertion.dataset_id == dataset_id,
                    RelationAssertion.source_entity_id.in_(entity_ids),
                    RelationAssertion.target_entity_id.in_(entity_ids),
                    supported_relation(),
                )
                .order_by(RelationAssertion.id)
                .limit(limit)
            )
        )
    )
    entity_count = (
        await db.scalar(
            select(func.count())
            .select_from(CanonicalEntity)
            .where(
                CanonicalEntity.project_id == project.project_id,
                CanonicalEntity.dataset_id == dataset_id,
                supported_entity(),
            )
        )
        or 0
    )
    relation_count = (
        await db.scalar(
            select(func.count())
            .select_from(RelationAssertion)
            .where(
                RelationAssertion.project_id == project.project_id,
                RelationAssertion.dataset_id == dataset_id,
                supported_relation(),
            )
        )
        or 0
    )
    return GraphSummary(
        dataset_id=dataset_id,
        entity_count=entity_count,
        relation_count=relation_count,
        nodes=[entity_view(item) for item in entities],
        relations=[await relation_view(db, item) for item in relations],
    )


@router.get("/datasets/{dataset_id}/graph/explorer", response_model=ExplorerView)
async def explorer(
    dataset_id: str,
    project: Project,
    db: Db,
    node_limit: int = Query(100, ge=1, le=MAX_NODES),
    relation_limit: int = Query(200, ge=1, le=MAX_NODES),
    community_level: int = Query(0, ge=0, le=2),
) -> ExplorerView:
    """Bounded Postgres graph view. Analytics enriches but never gates nodes."""
    await owned(db, project, dataset_id)
    base_entities = (
        CanonicalEntity.project_id == project.project_id,
        CanonicalEntity.dataset_id == dataset_id,
        supported_entity(),
    )
    base_relations = (
        RelationAssertion.project_id == project.project_id,
        RelationAssertion.dataset_id == dataset_id,
        supported_relation(),
    )
    latest = await db.scalar(
        select(GraphAnalyticsRun)
        .where(
            GraphAnalyticsRun.project_id == project.project_id,
            GraphAnalyticsRun.dataset_id == dataset_id,
        )
        .order_by(GraphAnalyticsRun.created_at.desc(), GraphAnalyticsRun.id.desc())
        .limit(1)
    )
    entity_count = int(
        await db.scalar(select(func.count()).select_from(CanonicalEntity).where(*base_entities))
        or 0
    )
    relation_count = int(
        await db.scalar(select(func.count()).select_from(RelationAssertion).where(*base_relations))
        or 0
    )
    source_ids = list(
        await db.scalars(
            select(CanonicalEntity.id).where(*base_entities).order_by(CanonicalEntity.id)
        )
    )
    source_relations = list(
        await db.execute(
            select(
                RelationAssertion.source_entity_id,
                RelationAssertion.target_entity_id,
                RelationAssertion.confidence,
            )
            .where(*base_relations)
            .order_by(RelationAssertion.id)
        )
    )
    current_hash = snapshot_hash(
        source_ids,
        [(source, target, float(confidence)) for source, target, confidence in source_relations],
    )
    stale = latest is None or latest.snapshot_hash != current_hash
    if latest is None:
        node_rows = list(
            await db.scalars(
                select(CanonicalEntity)
                .where(*base_entities)
                .order_by(CanonicalEntity.canonical_name, CanonicalEntity.id)
                .limit(node_limit)
            )
        )
        nodes = [
            ExplorerNode(
                id=item.id,
                canonical_name=item.canonical_name,
                entity_type=item.entity_type,
                community_id=None,
                degree=0,
                weighted_degree=0.0,
                importance=0.0,
            )
            for item in node_rows
        ]
        communities: list[ExplorerCommunity] = []
    else:
        node_metric_rows = await db.execute(
            select(
                CanonicalEntity,
                GraphAnalyticsMembership.community_id,
                GraphAnalyticsEntityMetric,
            )
            .join(
                GraphAnalyticsMembership,
                (GraphAnalyticsMembership.entity_id == CanonicalEntity.id)
                & (GraphAnalyticsMembership.run_id == latest.id)
                & (GraphAnalyticsMembership.level == community_level),
            )
            .join(
                GraphAnalyticsEntityMetric,
                (GraphAnalyticsEntityMetric.entity_id == CanonicalEntity.id)
                & (GraphAnalyticsEntityMetric.run_id == latest.id),
            )
            .where(*base_entities)
            .order_by(GraphAnalyticsEntityMetric.importance.desc(), CanonicalEntity.id)
            .limit(node_limit)
        )
        nodes = [
            ExplorerNode(
                id=item.id,
                canonical_name=item.canonical_name,
                entity_type=item.entity_type,
                community_id=community_id,
                degree=metric.degree,
                weighted_degree=metric.weighted_degree,
                importance=metric.importance,
            )
            for item, community_id, metric in node_metric_rows
        ]
        community_rows = list(
            await db.scalars(
                select(GraphAnalyticsCommunity)
                .where(
                    GraphAnalyticsCommunity.run_id == latest.id,
                    GraphAnalyticsCommunity.level == community_level,
                )
                .order_by(GraphAnalyticsCommunity.community_id)
            )
        )
        child_rows = (
            []
            if community_level == 0
            else list(
                await db.execute(
                    select(
                        GraphAnalyticsCommunity.parent_community_id,
                        GraphAnalyticsCommunity.community_id,
                    ).where(
                        GraphAnalyticsCommunity.run_id == latest.id,
                        GraphAnalyticsCommunity.level == community_level - 1,
                    )
                )
            )
        )
        children: dict[str, list[str]] = {}
        for parent_id, child_id in child_rows:
            if parent_id is not None:
                children.setdefault(parent_id, []).append(child_id)
        communities = [
            ExplorerCommunity(
                id=item.community_id,
                entity_count=item.entity_count,
                parent_id=item.parent_community_id,
                child_ids=children.get(item.community_id, []),
                internal_edges=item.internal_edges,
                external_edges=item.external_edges,
                density=item.density,
                importance=item.importance,
            )
            for item in community_rows
        ]
    node_ids = [item.id for item in nodes]
    relation_rows = (
        []
        if not node_ids
        else list(
            await db.scalars(
                select(RelationAssertion)
                .where(
                    *base_relations,
                    RelationAssertion.source_entity_id.in_(node_ids),
                    RelationAssertion.target_entity_id.in_(node_ids),
                )
                .order_by(RelationAssertion.id)
                .limit(relation_limit)
            )
        )
    )
    return ExplorerView(
        dataset_id=dataset_id,
        community_level=community_level,
        available_levels=[] if latest is None else list(range(latest.levels)),
        analytics=None
        if latest is None
        else ExplorerAnalyticsView(
            **AnalyticsRunView.model_validate(latest, from_attributes=True).model_dump(),
            created_at=latest.created_at,
            stale=stale,
        ),
        refresh_required=stale,
        stats=ExplorerStats(
            entity_count=entity_count,
            relation_count=relation_count,
            density=0.0
            if entity_count < 2
            else (2 * relation_count) / (entity_count * (entity_count - 1)),
        ),
        nodes=nodes,
        relations=[
            ExplorerRelation(
                id=item.id,
                source=item.source_entity_id,
                target=item.target_entity_id,
                type=item.relation_type,
                weight=float(item.confidence),
                confidence=item.confidence,
            )
            for item in relation_rows
        ],
        communities=communities,
    )


@router.get("/evidence/{evidence_id}", response_model=EvidenceView)
async def evidence(
    evidence_id: str,
    project: Project,
    db: Db,
) -> EvidenceView:
    item = await db.scalar(
        select(GraphEvidence).where(
            GraphEvidence.id == evidence_id, GraphEvidence.project_id == project.project_id
        )
    )
    if item is None:
        raise HTTPException(404, "evidence not found")
    chunk = await db.get(Chunk, item.chunk_id)
    return EvidenceView(
        id=item.id,
        dataset_id=item.dataset_id,
        document_id=item.document_id,
        chunk_id=item.chunk_id,
        quote=item.quote,
        run_id=item.run_id,
        entity_id=item.entity_id,
        relation_id=item.relation_id,
        confidence=item.confidence,
        start_offset=item.start_offset,
        end_offset=item.end_offset,
        source_location=source_location(chunk.metadata_) if chunk else None,
    )


@router.get(
    "/datasets/{dataset_id}/relations/{relation_id}/evidence",
    response_model=list[EvidenceView],
)
async def relation_evidence(
    dataset_id: str,
    relation_id: str,
    project: Project,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=MAX_NEIGHBORS)] = 25,
) -> list[EvidenceView]:
    await owned(db, project, dataset_id)
    relation = await db.scalar(
        select(RelationAssertion).where(
            RelationAssertion.id == relation_id,
            RelationAssertion.project_id == project.project_id,
            RelationAssertion.dataset_id == dataset_id,
            supported_relation(),
        )
    )
    if relation is None:
        raise HTTPException(404, "relation not found")
    rows = list(
        await db.execute(
            select(GraphEvidence, Chunk.metadata_)
            .join(
                Chunk,
                (Chunk.id == GraphEvidence.chunk_id)
                & (Chunk.project_id == GraphEvidence.project_id)
                & (Chunk.dataset_id == GraphEvidence.dataset_id),
            )
            .where(
                GraphEvidence.relation_id == relation_id,
                GraphEvidence.project_id == project.project_id,
                GraphEvidence.dataset_id == dataset_id,
            )
            .order_by(GraphEvidence.id)
            .limit(limit)
        )
    )
    return [
        EvidenceView(
            id=item.id,
            dataset_id=item.dataset_id,
            document_id=item.document_id,
            chunk_id=item.chunk_id,
            quote=item.quote,
            run_id=item.run_id,
            entity_id=item.entity_id,
            relation_id=item.relation_id,
            confidence=item.confidence,
            start_offset=item.start_offset,
            end_offset=item.end_offset,
            source_location=source_location(metadata),
        )
        for item, metadata in rows
    ]


@router.get("/graph-runs/{run_id}", response_model=RunView)
async def run(
    run_id: str,
    project: Project,
    db: Db,
) -> RunView:
    item = await db.scalar(
        select(GraphExtractionRun).where(
            GraphExtractionRun.id == run_id, GraphExtractionRun.project_id == project.project_id
        )
    )
    if item is None:
        raise HTTPException(404, "graph run not found")
    return RunView.model_validate(item, from_attributes=True)


@router.get("/graph-jobs/{job_id}", response_model=JobView)
async def job(
    job_id: str,
    project: Project,
    db: Db,
) -> JobView:
    item = await db.scalar(
        select(GraphExtractionJob).where(
            GraphExtractionJob.id == job_id, GraphExtractionJob.project_id == project.project_id
        )
    )
    if item is None:
        raise HTTPException(404, "graph job not found")
    return JobView.model_validate(item, from_attributes=True)


@router.patch("/relations/{relation_id}/review", response_model=RelationView)
async def review_relation(
    relation_id: str,
    body: ReviewInput,
    project: Project,
    db: Db,
) -> RelationView:
    item = await db.scalar(
        select(RelationAssertion).where(
            RelationAssertion.id == relation_id, RelationAssertion.project_id == project.project_id
        )
    )
    if item is None:
        raise HTTPException(404, "relation not found")
    if item.review_state in {
        ReviewState.APPROVED,
        ReviewState.REJECTED,
    } or body.review_state not in {ReviewState.APPROVED, ReviewState.REJECTED}:
        raise HTTPException(409, "invalid review transition")
    item.review_state = body.review_state
    await db.commit()
    return await relation_view(db, item)
