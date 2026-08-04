"""Audit trail API for tracking all mutations."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from open_graph_core.ids import uuid7
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ProjectContext, require_project
from app.dependencies import get_session
from app.models import AuditLog

router = APIRouter(prefix="/v1/audit-logs", tags=["audit"])
Project = Annotated[ProjectContext, Depends(require_project)]
Db = Annotated[AsyncSession, Depends(get_session)]


class AuditLogView(BaseModel):
    id: str
    project_id: str
    actor_type: str
    actor_id: str | None
    operation: str
    resource_type: str
    resource_id: str
    metadata: dict[str, object]
    created_at: datetime


class AuditLogListResponse(BaseModel):
    logs: list[AuditLogView]
    total: int


def audit_id() -> str:
    return f"al_{uuid7()}"


async def create_audit_log(
    db: AsyncSession,
    project_id: str,
    actor_type: str,
    actor_id: str | None,
    operation: str,
    resource_type: str,
    resource_id: str,
    metadata: dict[str, object] | None = None,
) -> AuditLog:
    log = AuditLog(
        id=audit_id(),
        project_id=project_id,
        actor_type=actor_type,
        actor_id=actor_id,
        operation=operation,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_=metadata or {},
    )
    db.add(log)
    return log


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    project: Project,
    db: Db,
    resource_type: str | None = Query(None, max_length=32),
    resource_id: str | None = Query(None, max_length=40),
    operation: str | None = Query(None, max_length=64),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> AuditLogListResponse:
    query = select(AuditLog).where(AuditLog.project_id == project.project_id)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if resource_id:
        query = query.where(AuditLog.resource_id == resource_id)
    if operation:
        query = query.where(AuditLog.operation == operation)

    total = len(list(await db.scalars(query)))
    items = list(
        await db.scalars(query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset))
    )
    return AuditLogListResponse(
        logs=[
            AuditLogView(
                id=log.id,
                project_id=str(log.project_id),
                actor_type=log.actor_type,
                actor_id=log.actor_id,
                operation=log.operation,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                metadata=log.metadata_,
                created_at=log.created_at,
            )
            for log in items
        ],
        total=total,
    )
