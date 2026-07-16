from app.main import app
from fastapi.testclient import TestClient


def test_liveness() -> None:
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_readiness_failure(monkeypatch) -> None:
    async def unavailable():
        return {"postgres": False}

    monkeypatch.setattr("app.health.checks", unavailable)
    response = TestClient(app).get("/ready")
    assert response.status_code == 503


def test_generated_runtime_routes_are_not_exposed() -> None:
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/v1/query" not in paths
    assert not any(path.startswith("/v1/memory") for path in paths)
    assert not any("community-report" in path for path in paths)
