import hashlib
import secrets
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import get_session
from app.models import ApiKey


@dataclass(frozen=True)
class ProjectContext:
    project_id: UUID


def require_admin_key(x_api_key: str = Header(...)) -> None:
    expected = get_settings().admin_api_key.get_secret_value()
    if not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")


async def require_project(
    db: Annotated[AsyncSession, Depends(get_session)],
    x_api_key: str = Header(...),
    x_project_id: str = Header(...),
) -> ProjectContext:
    try:
        project_id = UUID(x_project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid project ID") from exc
    digest = hashlib.sha256(x_api_key.encode()).hexdigest()
    key = await db.scalar(
        select(ApiKey).where(
            ApiKey.project_id == project_id,
            ApiKey.key_prefix == x_api_key[:16],
            ApiKey.key_hash == digest,
            ApiKey.revoked_at.is_(None),
        )
    )
    if key is None:
        raise HTTPException(status_code=401, detail="invalid project API key")
    return ProjectContext(project_id=project_id)
