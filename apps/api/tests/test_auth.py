import hashlib
from uuid import uuid4

import pytest
from app.auth import require_admin_key, require_project
from app.config import get_settings
from app.models import ApiKey
from fastapi import HTTPException


class FakeSession:
    def __init__(self, key: ApiKey | None) -> None:
        self.key = key

    async def scalar(self, statement: object) -> ApiKey | None:
        return self.key


def test_admin_key_uses_configured_secret() -> None:
    require_admin_key(get_settings().admin_api_key.get_secret_value())


def test_admin_key_rejects_invalid_key() -> None:
    with pytest.raises(HTTPException) as error:
        require_admin_key("wrong")
    assert error.value.status_code == 401


async def test_project_context_authenticates_project_key() -> None:
    project_id = uuid4()
    token = "project-secret-token"
    key = ApiKey(
        id=uuid4(),
        project_id=project_id,
        name="test",
        key_prefix=token[:16],
        key_hash=hashlib.sha256(token.encode()).hexdigest(),
    )
    context = await require_project(FakeSession(key), token, str(project_id))  # type: ignore[arg-type]
    assert context.project_id == project_id


async def test_project_context_rejects_invalid_uuid() -> None:
    with pytest.raises(HTTPException) as error:
        await require_project(FakeSession(None), "token", "not-a-uuid")  # type: ignore[arg-type]
    assert error.value.status_code == 400


async def test_project_context_rejects_unknown_key() -> None:
    with pytest.raises(HTTPException) as error:
        await require_project(FakeSession(None), "token", str(uuid4()))  # type: ignore[arg-type]
    assert error.value.status_code == 401
