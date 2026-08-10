"""Tests for Codebase AST Ingestion and Continuous Sync API."""

import pytest
from app.main import app
from app.models import ApiKey, Project
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_codebase_ingest_and_file_sync(session: AsyncSession, project: Project, api_key: ApiKey):
    client = TestClient(app)
    headers = {
        "X-API-Key": api_key.key_prefix + "test",
        "X-Project-ID": str(project.id),
    }

    # Batch Ingest
    response = client.post(
        "/v1/codebase/ingest",
        json={
            "dataset_id": "ds_test_codebase",
            "files": [
                {
                    "file_path": "src/math_utils.py",
                    "code": "def add(a: int, b: int) -> int:\n    return a + b\n\ndef multiply(a: int, b: int) -> int:\n    return a * b\n",
                    "language": "python",
                }
            ],
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["files_processed"] == 1
    assert data["entities_inserted"] >= 2

    # Single File Sync (Live Edit)
    sync_res = client.post(
        "/v1/codebase/sync-file",
        json={
            "dataset_id": "ds_test_codebase",
            "file_path": "src/math_utils.py",
            "code": "def add(a: int, b: int) -> int:\n    return a + b\n\ndef subtract(a: int, b: int) -> int:\n    return a - b\n",
            "language": "python",
        },
        headers=headers,
    )
    assert sync_res.status_code == 200
    sync_data = sync_res.json()
    assert sync_data["files_processed"] == 1
    assert sync_data["entities_inserted"] >= 2
