"""Tests for legal hold API."""

import pytest
from app.main import app
from app.models import AgentMemoryEpisode, ApiKey, LegalHold, Project
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_create_legal_hold(session: AsyncSession, project: Project, api_key: ApiKey):
    episode = AgentMemoryEpisode(
        id="mem_test_001",
        project_id=project.id,
        domain="engineering",
        title="Test episode",
        goal="Test goal",
        problem_signature="test-sig",
    )
    session.add(episode)
    await session.commit()

    client = TestClient(app)
    response = client.post(
        "/v1/legal-holds",
        json={
            "resource_type": "episode",
            "resource_id": "mem_test_001",
            "reason": "Compliance requirement",
        },
        headers={
            "X-API-Key": api_key.key_prefix + "test",
            "X-Project-ID": str(project.id),
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["resource_type"] == "episode"
    assert data["resource_id"] == "mem_test_001"
    assert data["reason"] == "Compliance requirement"


async def test_create_duplicate_legal_hold(
    session: AsyncSession, project: Project, api_key: ApiKey
):
    hold = LegalHold(
        id="lh_test_001",
        project_id=project.id,
        resource_type="episode",
        resource_id="mem_test_001",
        reason="Existing hold",
        created_by="api_key",
    )
    session.add(hold)
    await session.commit()

    client = TestClient(app)
    response = client.post(
        "/v1/legal-holds",
        json={
            "resource_type": "episode",
            "resource_id": "mem_test_001",
            "reason": "Duplicate",
        },
        headers={
            "X-API-Key": api_key.key_prefix + "test",
            "X-Project-ID": str(project.id),
        },
    )
    assert response.status_code == 409


async def test_list_legal_holds(session: AsyncSession, project: Project, api_key: ApiKey):
    for i in range(3):
        hold = LegalHold(
            id=f"lh_test_{i:03d}",
            project_id=project.id,
            resource_type="episode",
            resource_id=f"mem_test_{i:03d}",
            reason=f"Reason {i}",
            created_by="api_key",
        )
        session.add(hold)
    await session.commit()

    client = TestClient(app)
    response = client.get(
        "/v1/legal-holds",
        headers={
            "X-API-Key": api_key.key_prefix + "test",
            "X-Project-ID": str(project.id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["holds"]) == 3


async def test_delete_legal_hold(session: AsyncSession, project: Project, api_key: ApiKey):
    hold = LegalHold(
        id="lh_test_del",
        project_id=project.id,
        resource_type="episode",
        resource_id="mem_test_001",
        reason="To delete",
        created_by="api_key",
    )
    session.add(hold)
    await session.commit()

    client = TestClient(app)
    response = client.delete(
        "/v1/legal-holds/lh_test_del",
        headers={
            "X-API-Key": api_key.key_prefix + "test",
            "X-Project-ID": str(project.id),
        },
    )
    assert response.status_code == 204

    deleted = await session.get(LegalHold, "lh_test_del")
    assert deleted is None
