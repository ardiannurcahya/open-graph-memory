from uuid import uuid4

import pytest
from app.auth import require_admin_key, require_project
from app.config import get_settings
from fastapi import HTTPException


def test_admin_key_uses_configured_secret() -> None:
    require_admin_key(get_settings().admin_api_key.get_secret_value())


def test_admin_key_rejects_invalid_key() -> None:
    with pytest.raises(HTTPException) as error:
        require_admin_key("wrong")
    assert error.value.status_code == 401


def test_project_context_parses_uuid() -> None:
    project_id = uuid4()
    assert require_project(str(project_id)).project_id == project_id


def test_project_context_rejects_invalid_uuid() -> None:
    with pytest.raises(HTTPException) as error:
        require_project("not-a-uuid")
    assert error.value.status_code == 400
