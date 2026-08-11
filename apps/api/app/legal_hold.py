"""Legal hold API for compliance."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from open_graph_core.ids import uuid7
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ProjectContext, require_project
from app.dependencies import get_session
from app.models import AgentMemoryEpisode, LegalHold

router = APIRouter(prefix="/v1/legal-holds", tags=["legal-holds"])
Project = Annotated[ProjectContext, Depends(require_project)]
Db = Annotated[AsyncSession, Depends(get_session)]
ResourceType = str


class LegalHoldInput(BaseModel):
    resource_type: ResourceType = Field(pattern="^(episode|memory|entity|project)$")
    resource_id: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=1)


class LegalHoldView(BaseModel):
    id: str
    project_id: str
    resource_type: str
    resource_id: str
    reason: str
    created_by: str
    created_at: datetime


class LegalHoldListResponse(BaseModel):
    holds: list[LegalHoldView]
    total: int


def hold_id() -> str:
    return f"lh_{uuid7()}"


@router.post("", response_model=LegalHoldView, status_code=201)
async def create_legal_hold(body: LegalHoldInput, project: Project, db: Db) -> LegalHoldView:
    existing = await db.scalar(
        select(LegalHold).where(
            LegalHold.project_id == project.project_id,
            LegalHold.resource_type == body.resource_type,
            LegalHold.resource_id == body.resource_id,
        )
    )
    if existing:
        raise HTTPException(409, "legal hold already exists for this resource")

    if body.resource_type == "episode":
        episode = await db.scalar(
            select(AgentMemoryEpisode).where(
                AgentMemoryEpisode.id == body.resource_id,
                AgentMemoryEpisode.project_id == project.project_id,
            )
        )
        if not episode:
            raise HTTPException(404, "episode not found")

    item = LegalHold(
        id=hold_id(),
        project_id=project.project_id,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        reason=body.reason,
        created_by="api_key",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return LegalHoldView(
        id=item.id,
        project_id=str(item.project_id),
        resource_type=item.resource_type,
        resource_id=item.resource_id,
        reason=item.reason,
        created_by=item.created_by,
        created_at=item.created_at,
    )


@router.get("", response_model=LegalHoldListResponse)
async def list_legal_holds(
    project: Project,
    db: Db,
    resource_type: str | None = Query(None, pattern="^(episode|memory|entity|project)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> LegalHoldListResponse:
    query = select(LegalHold).where(LegalHold.project_id == project.project_id)
    if resource_type:
        query = query.where(LegalHold.resource_type == resource_type)

    total_query = select(LegalHold).where(LegalHold.project_id == project.project_id)
    if resource_type:
        total_query = total_query.where(LegalHold.resource_type == resource_type)

    total = len(list(await db.scalars(total_query)))
    items = list(
        await db.scalars(query.order_by(LegalHold.created_at.desc()).limit(limit).offset(offset))
    )
    return LegalHoldListResponse(
        holds=[
            LegalHoldView(
                id=h.id,
                project_id=str(h.project_id),
                resource_type=h.resource_type,
                resource_id=h.resource_id,
                reason=h.reason,
                created_by=h.created_by,
                created_at=h.created_at,
            )
            for h in items
        ],
        total=total,
    )


@router.get("/{hold_id}", response_model=LegalHoldView)
async def get_legal_hold(hold_id: str, project: Project, db: Db) -> LegalHoldView:
    item = await db.scalar(
        select(LegalHold).where(
            LegalHold.id == hold_id,
            LegalHold.project_id == project.project_id,
        )
    )
    if not item:
        raise HTTPException(404, "legal hold not found")
    return LegalHoldView(
        id=item.id,
        project_id=str(item.project_id),
        resource_type=item.resource_type,
        resource_id=item.resource_id,
        reason=item.reason,
        created_by=item.created_by,
        created_at=item.created_at,
    )


@router.delete("/{hold_id}", status_code=204)
async def delete_legal_hold(hold_id: str, project: Project, db: Db) -> None:
    item = await db.scalar(
        select(LegalHold).where(
            LegalHold.id == hold_id,
            LegalHold.project_id == project.project_id,
        )
    )
    if not item:
        raise HTTPException(404, "legal hold not found")
    await db.delete(item)
    await db.commit()


async def check_legal_hold(
    db: AsyncSession,
    project_id: str,
    resource_ids: list[str],
    resource_types: list[str] | None = None,
) -> None:
    if not resource_ids:
        return
    query = select(LegalHold).where(
        LegalHold.project_id == project_id,
        LegalHold.resource_id.in_(resource_ids),
    )
    if resource_types:
        query = query.where(LegalHold.resource_type.in_(resource_types))
    holds = list(await db.scalars(query))
    if holds:
        resource_list = ", ".join(f"{h.resource_type}:{h.resource_id}" for h in holds)
        raise HTTPException(
            423,
            f"resources are under legal hold: {resource_list}",
        )
