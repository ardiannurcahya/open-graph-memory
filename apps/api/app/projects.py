import hashlib
import secrets
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_key
from app.dependencies import get_session
from app.models import ApiKey, Project

router = APIRouter(prefix="/v1/projects", tags=["projects"])


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ProjectCreated(BaseModel):
    id: str
    name: str
    api_key: str


@router.post("", response_model=ProjectCreated, status_code=201)
async def create_project(
    body: ProjectInput,
    _: Annotated[None, Depends(require_admin_key)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> ProjectCreated:
    project_id = uuid4()
    raw_key = "ogm_" + secrets.token_urlsafe(32)
    db.add(Project(id=project_id, name=body.name))
    # No ORM relationship links these rows, so establish FK ordering explicitly.
    await db.flush()
    db.add(
        ApiKey(
            id=uuid4(),
            project_id=project_id,
            name="default",
            key_prefix=raw_key[:16],
            key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        )
    )
    await db.commit()
    return ProjectCreated(id=str(project_id), name=body.name, api_key=raw_key)
