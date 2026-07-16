from app.worker import celery_app, ping


def test_ping() -> None:
    assert ping.run() == "pong"


def test_graph_extraction_has_a_dedicated_queue() -> None:
    assert celery_app.conf.task_routes["graph.extract_job"] == {"queue": "graph"}
    assert celery_app.conf.task_default_queue == "default"


def test_graph_cleanup_reconciliation_is_scheduled() -> None:
    assert celery_app.conf.beat_schedule["reconcile-graph-cleanup-outbox"]["task"] == (
        "graph.reconcile_cleanup_outbox"
    )


def test_community_report_tasks_are_not_registered_or_scheduled() -> None:
    assert not any(name.startswith("community.") for name in celery_app.tasks)
    assert not any(
        entry["task"].startswith("community.")
        for entry in celery_app.conf.beat_schedule.values()
    )


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


def test_graph_extraction_has_no_celery_time_limit() -> None:
    from app.worker import extract_graph

    assert extract_graph.soft_time_limit is None
    assert extract_graph.time_limit is None
