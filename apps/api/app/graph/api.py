"""Bounded, PostgreSQL-authoritative graph inspection and review API with temporal tracking."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import exists, func, or_, select

from app.auth import Project
from app.datasets import owned
from app.dependencies import Db
from app.graph.analytics import refresh_dataset_analytics
from app.graph.helpers import supported_entity, supported_relation
from app.graph.limits import (
    MAX_EXPLORER_NODES,
    MAX_EXPLORER_RELATIONS,
    MAX_NEIGHBORS,
    MAX_NODES,
    MAX_PATH_DEPTH,
    MAX_PATH_RELATIONS,
    MAX_SUBGRAPH_DEPTH,
    MAX_SUBGRAPH_RELATIONS,
)
from app.graph.models import (
    CanonicalEntity,
    EntityAlias,
    GraphEvidence,
    GraphExtractionJob,
    GraphExtractionRun,
    RelationAssertion,
    ReviewState,
)
from app.graph.schemas import (
    AnalyticsRunView,
    EntityView,
    EvidenceView,
    ExplorerNodePage,
    ExplorerRelationPage,
    ExplorerView,
    GraphSummary,
    JobView,
    NeighborView,
    PathView,
    RelationView,
    ReviewInput,
    RunView,
    SubgraphView,
)
from app.graph.service import (
    bounded_walk,
    build_dataset_graph,
    build_explorer_node_page,
    build_explorer_view,
    entity_view,
    list_explorer_relations,
    path_ids,
    relation_view,
    scoped_dataset_entity,
    scoped_entity,
    source_location,
    temporal_filter,
)
from app.models import (
    Chunk,
)

"""Bounded, PostgreSQL-authoritative graph inspection and review API with temporal tracking."""


router = APIRouter(prefix="/v1", tags=["graph"])




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
    as_of: Annotated[datetime | None, Query(description="Temporal snapshot timestamp")] = None,
    include_history: Annotated[bool, Query(description="Include all temporal versions")] = False,
) -> list[EntityView]:
    ds = await owned(db, project, dataset_id)
    dataset_id = ds.id
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
        temporal_filter(as_of=as_of, include_history=include_history, entity=True),
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
    ds = await owned(db, project, dataset_id)
    dataset_id = ds.id
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
    ds = await owned(db, project, dataset_id)
    dataset_id = ds.id
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
                CanonicalEntity.dataset_id == entity.dataset_id,
                supported_entity(),
                temporal_filter(entity=True),
            )
        )
        if other is not None:
            result.append(
                NeighborView(relation=await relation_view(db, relation), entity=entity_view(other))
            )
    return result


@router.post("/datasets/{dataset_id}/analytics/refresh", response_model=AnalyticsRunView)
async def refresh_analytics(dataset_id: str, project: Project, db: Db) -> AnalyticsRunView:
    ds = await owned(db, project, dataset_id)
    dataset_id = ds.id
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
    as_of: datetime | None = Query(None, description="Temporal snapshot timestamp"),  # noqa: B008
    include_history: bool = Query(False, description="Include all temporal versions"),  # noqa: B008
) -> GraphSummary:
    ds = await owned(db, project, dataset_id)
    dataset_id = ds.id
    return await build_dataset_graph(
        db, project, dataset_id, limit=limit, depth=depth, as_of=as_of,
        include_history=include_history,
    )


@router.get("/datasets/{dataset_id}/graph/explorer", response_model=ExplorerView)
async def explorer(
    dataset_id: str,
    project: Project,
    db: Db,
    node_limit: int = Query(MAX_EXPLORER_NODES, ge=1, le=MAX_EXPLORER_NODES),
    relation_limit: int = Query(MAX_EXPLORER_RELATIONS, ge=1, le=MAX_EXPLORER_RELATIONS),
    community_level: int = Query(0, ge=0, le=2),
) -> ExplorerView:
    """Bounded Postgres graph view. Analytics enriches but never gates nodes."""
    ds = await owned(db, project, dataset_id)
    dataset_id = ds.id
    return await build_explorer_view(
        db, project, dataset_id, node_limit=node_limit,
        relation_limit=relation_limit, community_level=community_level,
    )


@router.get("/datasets/{dataset_id}/graph/explorer/nodes", response_model=ExplorerNodePage)
async def explorer_nodes(
    dataset_id: str,
    project: Project,
    db: Db,
    cursor: str | None = Query(None, max_length=64),
    limit: int = Query(MAX_EXPLORER_NODES, ge=1, le=MAX_EXPLORER_NODES),
    community_level: int = Query(0, ge=0, le=2),
) -> ExplorerNodePage:
    """Keyset-paged supported nodes; analytics enriches but never gates rows."""
    ds = await owned(db, project, dataset_id)
    dataset_id = ds.id
    return await build_explorer_node_page(
        db, project, dataset_id, cursor=cursor, limit=limit,
        community_level=community_level,
    )


@router.get(
    "/datasets/{dataset_id}/graph/explorer/relations",
    response_model=ExplorerRelationPage,
)
async def explorer_relations(
    dataset_id: str,
    project: Project,
    db: Db,
    cursor: str | None = Query(None, max_length=64),
    limit: int = Query(MAX_EXPLORER_RELATIONS, ge=1, le=MAX_EXPLORER_RELATIONS),
) -> ExplorerRelationPage:
    """Keyset-paged relations independent of node pages, preserving cross-page edges."""
    ds = await owned(db, project, dataset_id)
    dataset_id = ds.id
    return await list_explorer_relations(db, project, dataset_id, cursor=cursor, limit=limit)


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
    ds = await owned(db, project, dataset_id)
    dataset_id = ds.id
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
