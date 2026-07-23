from types import SimpleNamespace

import pytest
from app.arq_worker import WorkerSettings, enqueue_extract_graph, redis_settings


def test_worker_has_all_tasks() -> None:
    task_names = {fn.name for fn in WorkerSettings.functions}
    assert task_names == {"task_index_document", "task_extract_graph"}


def test_worker_uses_configured_redis() -> None:
    assert redis_settings().host == "redis"
    assert WorkerSettings.redis_settings.host == "redis"


def test_worker_task_limits_are_explicit() -> None:
    functions = {fn.name: fn for fn in WorkerSettings.functions}
    assert functions["task_index_document"].max_tries == 5
    assert functions["task_index_document"].timeout_s == 1800
    assert functions["task_extract_graph"].max_tries == 1
    assert functions["task_extract_graph"].timeout_s >= 3600


@pytest.mark.asyncio
async def test_enqueue_graph_uses_deterministic_id_and_closes_pool(monkeypatch) -> None:
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    closed = False

    class Pool:
        async def enqueue_job(self, name: str, *args: object, **kwargs: object) -> object:
            calls.append((name, args, kwargs))
            return SimpleNamespace()

        async def close(self) -> None:
            nonlocal closed
            closed = True

    async def pool() -> Pool:
        return Pool()

    monkeypatch.setattr("app.arq_worker.create_redis_pool", pool)
    await enqueue_extract_graph("job-a")

    assert calls == [("task_extract_graph", ("job-a",), {"_job_id": "graph:job-a"})]
    assert closed


def test_graph_job_lease_exceeds_extractor_timeout(monkeypatch) -> None:
    from types import SimpleNamespace

    import app.config
    from app.graph_dispatch import lease_seconds

    monkeypatch.setattr(
        app.config,
        "get_settings",
        lambda: SimpleNamespace(graph_extractor_timeout_seconds=420),
    )

    assert lease_seconds() == 480
