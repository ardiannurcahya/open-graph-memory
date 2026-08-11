"""Tests for audit trail API."""

import pytest
from app.audit import create_audit_log
from app.main import app
from app.models import ApiKey, AuditLog, Project
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_create_audit_log(session: AsyncSession, project: Project):
    log = await create_audit_log(
        db=session,
        project_id=str(project.id),
        actor_type="api_key",
        actor_id="test-key",
        operation="episode.create",
        resource_type="episode",
        resource_id="mem_test_001",
        metadata={"title": "Test episode"},
    )
    await session.commit()
    await session.refresh(log)

    assert log.id.startswith("al_")
    assert log.operation == "episode.create"
    assert log.resource_type == "episode"


async def test_list_audit_logs(session: AsyncSession, project: Project, api_key: ApiKey):
    for i in range(5):
        log = AuditLog(
            id=f"al_test_{i:03d}",
            project_id=project.id,
            actor_type="api_key",
            actor_id="test-key",
            operation=f"operation_{i}",
            resource_type="episode",
            resource_id=f"mem_test_{i:03d}",
        )
        session.add(log)
    await session.commit()

    client = TestClient(app)
    response = client.get(
        "/v1/audit-logs",
        headers={
            "X-API-Key": api_key.key_prefix + "test",
            "X-Project-ID": str(project.id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["logs"]) == 5


async def test_list_audit_logs_filter(session: AsyncSession, project: Project, api_key: ApiKey):
    for i in range(3):
        log = AuditLog(
            id=f"al_filter_{i:03d}",
            project_id=project.id,
            actor_type="api_key",
            actor_id="test-key",
            operation="episode.create",
            resource_type="episode",
            resource_id=f"mem_test_{i:03d}",
        )
        session.add(log)
    log_other = AuditLog(
        id="al_filter_other",
        project_id=project.id,
        actor_type="api_key",
        actor_id="test-key",
        operation="memory.commit",
        resource_type="memory",
        resource_id="mem_other",
    )
    session.add(log_other)
    await session.commit()

    client = TestClient(app)
    response = client.get(
        "/v1/audit-logs?operation=episode.create",
        headers={
            "X-API-Key": api_key.key_prefix + "test",
            "X-Project-ID": str(project.id),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
