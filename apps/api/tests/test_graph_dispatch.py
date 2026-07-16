from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.graph_dispatch import renew_graph_job_lease
from app.graph_models import GraphExtractionJob, GraphJobStatus


class Session:
    def __init__(self, job: GraphExtractionJob) -> None:
        self.job = job
        self.commits = 0

    async def scalar(self, statement: object) -> GraphExtractionJob:
        return self.job

    async def commit(self) -> None:
        self.commits += 1


class Factory:
    def __init__(self, session: Session) -> None:
        self.session = session

    def __call__(self) -> "Factory":
        return self

    async def __aenter__(self) -> Session:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_renew_graph_job_lease_extends_running_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    job = SimpleNamespace(
        id="job",
        status=GraphJobStatus.RUNNING,
        lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    session = Session(job)  # type: ignore[arg-type]
    monkeypatch.setattr(
        "app.graph_dispatch.async_sessionmaker", lambda *args, **kwargs: Factory(session)
    )
    monkeypatch.setattr("app.graph_dispatch.lease_seconds", lambda: 300)

    await renew_graph_job_lease("job")

    assert job.lease_expires_at > datetime.now(UTC) + timedelta(seconds=299)
    assert session.commits == 1
