import secrets
from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException, status

from app.config import get_settings


@dataclass(frozen=True)
class ProjectContext:
    project_id: UUID


def require_admin_key(x_api_key: str = Header(...)) -> None:
    expected = get_settings().admin_api_key.get_secret_value()
    if not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")


def require_project(x_project_id: str = Header(...)) -> ProjectContext:
    """Establish an explicit tenant context for all future project-scoped routes."""
    try:
        return ProjectContext(project_id=UUID(x_project_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid project ID"
        ) from exc
