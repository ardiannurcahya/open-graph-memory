"""Bounded, PostgreSQL-authoritative graph inspection and review API with temporal tracking."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.auth import ProjectContext, require_project
from app.datasets import owned
from app.dependencies import get_session
from app.graph.analytics import refresh_dataset_analytics, snapshot_hash
from app.graph.helpers import supported_entity, supported_relation
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
    ExplorerAnalyticsView,
    ExplorerCommunity,
    ExplorerNode,
    ExplorerNodePage,
    ExplorerRelation,
    ExplorerRelationPage,
    ExplorerStats,
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
    GRAPH_CANDIDATE_LIMIT,
    MAX_EXPLORER_NODES,
    MAX_EXPLORER_RELATIONS,
    MAX_NEIGHBORS,
    MAX_NODES,
    MAX_PATH_DEPTH,
    MAX_PATH_RELATIONS,
    MAX_SUBGRAPH_DEPTH,
    MAX_SUBGRAPH_RELATIONS,
    bounded_walk,
    entity_view,
    path_ids,
    rank_graph_entities,
    relation_view,
    scoped_dataset_entity,
    scoped_entity,
    source_location,
    temporal_filter,
)
from app.models import (
    Chunk,
    GraphAnalyticsCommunity,
    GraphAnalyticsEntityMetric,
    GraphAnalyticsMembership,
    GraphAnalyticsRun,
)

"""Bounded, PostgreSQL-authoritative graph inspection and review API with temporal tracking."""


router = APIRouter(prefix="/v1", tags=["graph"])


Project = Annotated[ProjectContext, Depends(require_project)]


Db = Annotated[AsyncSession, Depends(get_session)]


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
    as_of: datetime | None = Query(None, description="Temporal snapshot timestamp"),  # noqa: B008
    include_history: bool = Query(False, description="Include all temporal versions"),  # noqa: B008
) -> GraphSummary:
    await owned(db, project, dataset_id)
    candidate_entities = list(
        await db.scalars(
            select(CanonicalEntity)
            .where(
                CanonicalEntity.project_id == project.project_id,
                CanonicalEntity.dataset_id == dataset_id,
                supported_entity(),
                temporal_filter(as_of=as_of, include_history=include_history, entity=True),
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
            temporal_filter(as_of=as_of, include_history=include_history, entity=False),
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
            temporal_filter(as_of=as_of, include_history=include_history, entity=False),
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
                    temporal_filter(as_of=as_of, include_history=include_history, entity=False),
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
    node_limit: int = Query(MAX_EXPLORER_NODES, ge=1, le=MAX_EXPLORER_NODES),
    relation_limit: int = Query(MAX_EXPLORER_RELATIONS, ge=1, le=MAX_EXPLORER_RELATIONS),
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
            .order_by(
                GraphAnalyticsEntityMetric.importance.desc(),
                CanonicalEntity.id,
            )
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
    await owned(db, project, dataset_id)
    latest = await db.scalar(
        select(GraphAnalyticsRun)
        .where(
            GraphAnalyticsRun.project_id == project.project_id,
            GraphAnalyticsRun.dataset_id == dataset_id,
        )
        .order_by(GraphAnalyticsRun.created_at.desc(), GraphAnalyticsRun.id.desc())
        .limit(1)
    )
    filters: list[ColumnElement[bool]] = [
        CanonicalEntity.project_id == project.project_id,
        CanonicalEntity.dataset_id == dataset_id,
        supported_entity(),
    ]
    if cursor is not None:
        filters.append(CanonicalEntity.id > cursor)
    if latest is None:
        rows = list(
            await db.scalars(
                select(CanonicalEntity)
                .where(*filters)
                .order_by(CanonicalEntity.id)
                .limit(limit + 1)
            )
        )
        has_more = len(rows) > limit
        entity_page = rows[:limit]
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
            for item in entity_page
        ]
    else:
        result = list(
            await db.execute(
                select(
                    CanonicalEntity,
                    GraphAnalyticsMembership.community_id,
                    GraphAnalyticsEntityMetric,
                )
                .outerjoin(
                    GraphAnalyticsMembership,
                    (GraphAnalyticsMembership.entity_id == CanonicalEntity.id)
                    & (GraphAnalyticsMembership.run_id == latest.id)
                    & (GraphAnalyticsMembership.level == community_level),
                )
                .outerjoin(
                    GraphAnalyticsEntityMetric,
                    (GraphAnalyticsEntityMetric.entity_id == CanonicalEntity.id)
                    & (GraphAnalyticsEntityMetric.run_id == latest.id),
                )
                .where(*filters)
                .order_by(CanonicalEntity.id)
                .limit(limit + 1)
            )
        )
        has_more = len(result) > limit
        metric_page = result[:limit]
        nodes = [
            ExplorerNode(
                id=item.id,
                canonical_name=item.canonical_name,
                entity_type=item.entity_type,
                community_id=community_id,
                degree=0 if metric is None else metric.degree,
                weighted_degree=0.0 if metric is None else metric.weighted_degree,
                importance=0.0 if metric is None else metric.importance,
            )
            for item, community_id, metric in metric_page
        ]
    return ExplorerNodePage(
        nodes=nodes,
        next_cursor=nodes[-1].id if has_more and nodes else None,
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
    await owned(db, project, dataset_id)
    filters: list[ColumnElement[bool]] = [
        RelationAssertion.project_id == project.project_id,
        RelationAssertion.dataset_id == dataset_id,
        supported_relation(),
    ]
    if cursor is not None:
        filters.append(RelationAssertion.id > cursor)
    rows = list(
        await db.scalars(
            select(RelationAssertion)
            .where(*filters)
            .order_by(RelationAssertion.id)
            .limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    relations = [
        ExplorerRelation(
            id=item.id,
            source=item.source_entity_id,
            target=item.target_entity_id,
            type=item.relation_type,
            weight=float(item.confidence),
            confidence=item.confidence,
        )
        for item in page
    ]
    return ExplorerRelationPage(
        relations=relations,
        next_cursor=relations[-1].id if has_more and relations else None,
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
