"""Retention policy API for data lifecycle management."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from open_graph_core.ids import uuid7
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ProjectContext, require_project
from app.dependencies import get_session
from app.models import AgentMemoryEpisode, LegalHold, RetentionPolicy

router = APIRouter(prefix="/v1/retention", tags=["retention"])
Project = Annotated[ProjectContext, Depends(require_project)]
Db = Annotated[AsyncSession, Depends(get_session)]


class RetentionInput(BaseModel):
    resource_type: str = Field(pattern="^(episode|memory)$")
    older_than_days: int = Field(gt=0, le=3650)
    action: str = Field(pattern="^(archive|delete)$")


class RetentionPreviewItem(BaseModel):
    resource_id: str
    resource_type: str
    created_at: datetime
    status: str


class RetentionPreviewResponse(BaseModel):
    policy_id: str | None
    eligible_count: int
    items: list[RetentionPreviewItem]


class RetentionApplyResponse(BaseModel):
    policy_id: str
    affected_count: int
    action: str


class RetentionPolicyView(BaseModel):
    id: str
    project_id: str
    resource_type: str
    older_than_days: int
    action: str
    status: str
    created_by: str
    created_at: datetime


def policy_id() -> str:
    return f"rp_{uuid7()}"


@router.post("/preview", response_model=RetentionPreviewResponse)
async def preview_retention(
    body: RetentionInput, project: Project, db: Db
) -> RetentionPreviewResponse:
    cutoff = datetime.now(UTC) - timedelta(days=body.older_than_days)

    query = select(AgentMemoryEpisode).where(
        AgentMemoryEpisode.project_id == project.project_id,
        AgentMemoryEpisode.created_at < cutoff,
    )
    if body.action == "archive":
        query = query.where(AgentMemoryEpisode.status.in_(["active", "open"]))
    elif body.action == "delete":
        query = query.where(AgentMemoryEpisode.status.in_(["archived", "superseded", "rejected"]))

    items = list(await db.scalars(query.limit(100)))
    total = len(items)

    return RetentionPreviewResponse(
        policy_id=None,
        eligible_count=total,
        items=[
            RetentionPreviewItem(
                resource_id=item.id,
                resource_type="episode",
                created_at=item.created_at,
                status=item.status,
            )
            for item in items
        ],
    )


@router.post("/apply", response_model=RetentionApplyResponse)
async def apply_retention(body: RetentionInput, project: Project, db: Db) -> RetentionApplyResponse:
    cutoff = datetime.now(UTC) - timedelta(days=body.older_than_days)
    pid = policy_id()

    policy = RetentionPolicy(
        id=pid,
        project_id=project.project_id,
        resource_type=body.resource_type,
        older_than_days=body.older_than_days,
        action=body.action,
        status="active",
        created_by="api_key",
    )
    db.add(policy)

    held_ids = set()
    holds = list(
        await db.scalars(
            select(LegalHold).where(
                LegalHold.project_id == project.project_id,
                LegalHold.resource_type.in_(["episode", "memory"]),
            )
        )
    )
    for h in holds:
        held_ids.add(h.resource_id)

    query = select(AgentMemoryEpisode).where(
        AgentMemoryEpisode.project_id == project.project_id,
        AgentMemoryEpisode.created_at < cutoff,
    )

    if body.action == "archive":
        query = query.where(AgentMemoryEpisode.status.in_(["active", "open"]))
    else:
        query = query.where(AgentMemoryEpisode.status.in_(["archived", "superseded", "rejected"]))

    items = list(await db.scalars(query))
    affected = 0
    for item in items:
        if item.id in held_ids:
            continue
        if body.action == "archive":
            item.status = "archived"
            item.updated_at = datetime.now(UTC)
        else:
            await db.delete(item)
        affected += 1

    policy.status = "completed"
    await db.commit()

    return RetentionApplyResponse(
        policy_id=pid,
        affected_count=affected,
        action=body.action,
    )


@router.get("/policies", response_model=list[RetentionPolicyView])
async def list_retention_policies(
    project: Project,
    db: Db,
    status: str | None = Query(None, pattern="^(active|paused|completed)$"),
) -> list[RetentionPolicyView]:
    query = select(RetentionPolicy).where(RetentionPolicy.project_id == project.project_id)
    if status:
        query = query.where(RetentionPolicy.status == status)
    items = list(await db.scalars(query.order_by(RetentionPolicy.created_at.desc())))
    return [
        RetentionPolicyView(
            id=p.id,
            project_id=str(p.project_id),
            resource_type=p.resource_type,
            older_than_days=p.older_than_days,
            action=p.action,
            status=p.status,
            created_by=p.created_by,
            created_at=p.created_at,
        )
        for p in items
    ]
