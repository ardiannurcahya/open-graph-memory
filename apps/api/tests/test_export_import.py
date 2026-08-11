"""Tests for export/import API."""

import pytest
from app.main import app
from app.models import AgentMemoryEpisode, ApiKey, Project
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_export_project(session: AsyncSession, project: Project, api_key: ApiKey):
    for i in range(3):
        episode = AgentMemoryEpisode(
            id=f"mem_export_{i:03d}",
            project_id=project.id,
            domain="engineering",
            title=f"Episode {i}",
            goal=f"Goal {i}",
            problem_signature=f"sig-{i}",
        )
        session.add(episode)
    await session.commit()

    client = TestClient(app)
    response = client.get(
        f"/v1/projects/{project.id}/export",
        headers={
            "X-API-Key": api_key.key_prefix + "test",
            "X-Project-ID": str(project.id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["episode_count"] == 3
    assert len(data["episodes"]) == 3
    assert "Content-Disposition" in response.headers


async def test_import_project(session: AsyncSession, project: Project, api_key: ApiKey):
    import_data = {
        "metadata": {
            "project_id": str(project.id),
            "exported_at": "2025-01-01T00:00:00Z",
            "schema_version": "1.0.0",
            "episode_count": 2,
        },
        "episodes": [
            {
                "id": "mem_import_001",
                "domain": "engineering",
                "title": "Imported 1",
                "goal": "Goal 1",
                "problem_signature": "import-sig-1",
                "attempts": [],
                "outcome": None,
                "evidence": [],
            },
            {
                "id": "mem_import_002",
                "domain": "trading",
                "title": "Imported 2",
                "goal": "Goal 2",
                "problem_signature": "import-sig-2",
                "attempts": [
                    {
                        "id": "att_import_001",
                        "sequence": 1,
                        "hypothesis": "Test",
                        "actions": [],
                        "result": "success",
                    }
                ],
                "outcome": {
                    "id": "out_import_001",
                    "status": "success",
                    "summary": "Completed",
                    "pattern_key": "import-sig-2",
                },
                "evidence": [{"id": "ev_import_001", "reference": "test.log"}],
            },
        ],
    }

    client = TestClient(app)
    response = client.post(
        f"/v1/projects/{project.id}/import",
        json={"data": import_data, "owner_email": "test@example.com"},
        headers={
            "X-API-Key": api_key.key_prefix + "test",
            "X-Project-ID": str(project.id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["episodes_imported"] == 2

    for ep_id in ["mem_import_001", "mem_import_002"]:
        ep = await session.get(AgentMemoryEpisode, ep_id)
        assert ep is not None
        assert str(ep.project_id) == str(project.id)


async def test_import_duplicate_skipped(session: AsyncSession, project: Project, api_key: ApiKey):
    episode = AgentMemoryEpisode(
        id="mem_dup_001",
        project_id=project.id,
        domain="engineering",
        title="Existing",
        goal="Goal",
        problem_signature="dup-sig",
    )
    session.add(episode)
    await session.commit()

    import_data = {
        "metadata": {"episode_count": 1},
        "episodes": [
            {
                "id": "mem_dup_001",
                "domain": "engineering",
                "title": "Duplicate",
                "goal": "Goal",
                "problem_signature": "dup-sig",
            }
        ],
    }

    client = TestClient(app)
    response = client.post(
        f"/v1/projects/{project.id}/import",
        json={"data": import_data, "owner_email": "test@example.com"},
        headers={
            "X-API-Key": api_key.key_prefix + "test",
            "X-Project-ID": str(project.id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["episodes_imported"] == 0
