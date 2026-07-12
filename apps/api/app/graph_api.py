"""Bounded, PostgreSQL-authoritative graph inspection and review API."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ProjectContext, require_project
from app.datasets import owned
from app.dependencies import get_session
from app.graph_models import (
    CanonicalEntity,
    GraphEvidence,
    GraphExtractionJob,
    GraphExtractionRun,
    RelationAssertion,
    ReviewState,
)

router = APIRouter(prefix="/v1", tags=["graph"])
Project = Annotated[ProjectContext, Depends(require_project)]
Db = Annotated[AsyncSession, Depends(get_session)]
MAX_NEIGHBORS = 100
MAX_NODES = 200


class Citation(BaseModel):
    dataset_id: str
    document_id: str
    chunk_id: str
    quote: str


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


def entity_view(item: CanonicalEntity) -> EntityView:
    return EntityView.model_validate(item, from_attributes=True)


async def citations(db: AsyncSession, relation_id: str) -> list[Citation]:
    rows = await db.execute(
        select(
            GraphEvidence.dataset_id,
            GraphEvidence.document_id,
            GraphEvidence.chunk_id,
            GraphEvidence.quote,
        )
        .where(GraphEvidence.relation_id == relation_id)
        .order_by(GraphEvidence.id)
    )
    return [Citation(dataset_id=r[0], document_id=r[1], chunk_id=r[2], quote=r[3]) for r in rows]


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
            CanonicalEntity.id == entity_id, CanonicalEntity.project_id == project.project_id
        )
    )
    if item is None:
        raise HTTPException(404, "entity not found")
    return item


@router.get("/entities/{entity_id}", response_model=EntityView)
async def get_entity(
    entity_id: str,
    project: Project,
    db: Db,
) -> EntityView:
    return entity_view(await scoped_entity(db, project, entity_id))


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
                CanonicalEntity.id == other_id, CanonicalEntity.project_id == project.project_id
            )
        )
        if other is not None:
            result.append(
                NeighborView(relation=await relation_view(db, relation), entity=entity_view(other))
            )
    return result


@router.get("/datasets/{dataset_id}/graph", response_model=GraphSummary)
async def graph(
    dataset_id: str,
    project: Project,
    db: Db,
    limit: int = Query(100, ge=1, le=MAX_NODES),
    depth: int = Query(1, ge=0, le=1),
) -> GraphSummary:
    await owned(db, project, dataset_id)
    entities = list(
        await db.scalars(
            select(CanonicalEntity)
            .where(
                CanonicalEntity.project_id == project.project_id,
                CanonicalEntity.dataset_id == dataset_id,
            )
            .order_by(CanonicalEntity.id)
            .limit(limit)
        )
    )
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
    )


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
