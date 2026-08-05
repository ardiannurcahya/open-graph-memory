"""Tests for retention policy API."""

from datetime import UTC, datetime, timedelta

import pytest
from app.main import app
from app.models import AgentMemoryEpisode, ApiKey, Project, RetentionPolicy
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_preview_retention(session: AsyncSession, project: Project, api_key: ApiKey):
    now = datetime.now(UTC)
    for i in range(5):
        episode = AgentMemoryEpisode(
            id=f"mem_old_{i:03d}",
            project_id=project.id,
            domain="engineering",
            title=f"Old episode {i}",
            goal="Test goal",
            problem_signature=f"old-sig-{i}",
            status="active",
            created_at=now - timedelta(days=100),
        )
        session.add(episode)
    await session.commit()

    client = TestClient(app)
    response = client.post(
        "/v1/retention/preview",
        json={
            "resource_type": "episode",
            "older_than_days": 30,
            "action": "archive",
        },
        headers={
            "X-API-Key": api_key.key_prefix + "test",
            "X-Project-ID": str(project.id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["eligible_count"] == 5


async def test_apply_retention(session: AsyncSession, project: Project, api_key: ApiKey):
    now = datetime.now(UTC)
    for i in range(3):
        episode = AgentMemoryEpisode(
            id=f"mem_apply_{i:03d}",
            project_id=project.id,
            domain="engineering",
            title=f"Old episode {i}",
            goal="Test goal",
            problem_signature=f"apply-sig-{i}",
            status="active",
            created_at=now - timedelta(days=100),
        )
        session.add(episode)
    await session.commit()

    client = TestClient(app)
    response = client.post(
        "/v1/retention/apply",
        json={
            "resource_type": "episode",
            "older_than_days": 30,
            "action": "archive",
        },
        headers={
            "X-API-Key": api_key.key_prefix + "test",
            "X-Project-ID": str(project.id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["affected_count"] == 3
    assert data["action"] == "archive"


async def test_list_retention_policies(session: AsyncSession, project: Project, api_key: ApiKey):
    for i in range(2):
        policy = RetentionPolicy(
            id=f"rp_test_{i:03d}",
            project_id=project.id,
            resource_type="episode",
            older_than_days=30,
            action="archive",
            status="completed",
            created_by="api_key",
        )
        session.add(policy)
    await session.commit()

    client = TestClient(app)
    response = client.get(
        "/v1/retention/policies",
        headers={
            "X-API-Key": api_key.key_prefix + "test",
            "X-Project-ID": str(project.id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
