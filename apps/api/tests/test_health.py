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
