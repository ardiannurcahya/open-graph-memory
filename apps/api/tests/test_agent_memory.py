from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from app.agent_memory import SupersedeInput, is_promoted, router, supersede_episode
from app.auth import ProjectContext, require_project
from app.dependencies import get_session
from app.models import (
    AgentMemoryAttempt,
    AgentMemoryEpisode,
    AgentMemoryOutcome,
    AgentMemoryPattern,
)
from fastapi import FastAPI


def test_agent_memory_migration_and_models_match() -> None:
    path = Path("apps/api/migrations/versions/0021_agent_memory.py")
    spec = spec_from_file_location("agent_memory", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.down_revision == "0019"
    assert AgentMemoryEpisode.__tablename__ == "agent_memory_episodes"
    assert AgentMemoryAttempt.__tablename__ == "agent_memory_attempts"
    assert AgentMemoryOutcome.__tablename__ == "agent_memory_outcomes"
    assert AgentMemoryPattern.__tablename__ == "agent_memory_patterns"
    assert "search_vector" in AgentMemoryEpisode.__table__.c


def test_agent_memory_timestamp_migration_follows_initial_schema() -> None:
    path = Path("apps/api/migrations/versions/0022_agent_memory_timestamps.py")
    spec = spec_from_file_location("agent_memory_timestamps", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.down_revision == "0021"
    source = path.read_text(encoding="utf-8")
    assert '"agent_memory_attempts"' in source
    assert '"agent_memory_outcomes"' in source


def test_agent_memory_router_has_project_scoped_operations() -> None:
    routes = {(route.path, tuple(sorted(route.methods))) for route in router.routes}
    assert ("/v1/agent-memory/episodes", ("POST",)) in routes
    assert ("/v1/agent-memory/episodes", ("GET",)) in routes
    assert ("/v1/agent-memory/episodes/{episode_id}/attempts", ("POST",)) in routes
    assert ("/v1/agent-memory/episodes/{episode_id}/outcomes", ("POST",)) in routes
    assert ("/v1/agent-memory/search", ("GET",)) in routes
    assert ("/v1/agent-memory/episodes/{episode_id}/feedback", ("POST",)) in routes
    assert ("/v1/agent-memory/episodes/{episode_id}/supersede", ("POST",)) in routes


def test_pattern_promotion_requires_observation_and_confidence_thresholds() -> None:
    assert not is_promoted(2, 1.0)
    assert not is_promoted(3, 0.69)
    assert is_promoted(3, 0.7)


class MockSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, item: object) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        pass


@pytest.mark.asyncio
async def test_create_episode_executes_project_dependency_and_persists_evidence() -> None:
    db = MockSession()
    app = FastAPI()
    app.include_router(router)

    async def project() -> ProjectContext:
        return ProjectContext(uuid4())

    async def session() -> MockSession:
        return db

    app.dependency_overrides[require_project] = project
    app.dependency_overrides[get_session] = session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/agent-memory/episodes",
            json={
                "domain": "engineering",
                "title": "Deploy fix",
                "goal": "restore service",
                "problem_signature": "api deploy failure",
                "scope": {"repository": "api", "environment": "prod"},
                "tags": ["deploy"],
                "evidence": [{"reference": "s3://logs/1"}],
            },
        )
    assert response.status_code == 201
    assert response.json()["status"] == "open"
    assert {item.__class__.__name__ for item in db.added} == {
        "AgentMemoryEpisode",
        "AgentMemoryEvidence",
    }


@pytest.mark.asyncio
async def test_episode_supersession_locks_both_rows_and_rejects_a_cycle(monkeypatch) -> None:
    source = SimpleNamespace(id="source", status="active", superseded_by_id=None)
    replacement = SimpleNamespace(id="replacement", status="active", superseded_by_id="source")
    locks: list[tuple[str, bool]] = []

    async def fake_owned_episode(_db, _project, episode_id: str, lock: bool = False):
        locks.append((episode_id, lock))
        return {"source": source, "replacement": replacement}[episode_id]

    monkeypatch.setattr("app.agent_memory.owned_episode", fake_owned_episode)
    with pytest.raises(Exception) as error:
        await supersede_episode(
            "source",
            SupersedeInput(superseding_episode_id="replacement"),
            ProjectContext(uuid4()),
            SimpleNamespace(),
        )

    assert getattr(error.value, "status_code", None) == 409
    assert locks[:2] == [("source", True), ("replacement", True)]
    assert source.superseded_by_id is None
