from m4_evaluator import evaluate, percentile


def golden() -> dict[str, object]:
    return {
        "version": "test-v1",
        "cases": [
            {"id": f"q{i}", "answerable": i != 19, "evidence_ids": [] if i == 19 else [f"e{i}"]}
            for i in range(20)
        ],
    }


def predictions() -> list[dict[str, object]]:
    rows = []
    for mode in ("vector_only", "graph_only", "hybrid"):
        for i in range(20):
            rows.append(
                {
                    "id": f"q{i}",
                    "mode": mode,
                    "retrieved": [] if i == 19 else [f"e{i}"],
                    "citations": [] if i == 19 else [f"e{i}"],
                    "answer": "cannot answer" if i == 19 else "answer [1]",
                    "latency_ms": i + 1,
                    "trace": {
                        "graph": {"status": "ok", "paths": [{}] if mode != "vector_only" else []}
                    },
                }
            )
    return rows


def test_m4_metrics_compare_each_mode_and_traversal_budget() -> None:
    report = evaluate(golden(), predictions())
    for mode in ("vector_only", "graph_only", "hybrid"):
        metrics = report["modes"][mode]
        assert metrics["recall_at_k"] == 1
        assert metrics["citation_correctness"] == 1
        assert metrics["answerability_accuracy"] == 1
        assert metrics["latency_ms"] == {"p50": 10.0, "p95": 19.0}
    assert report["modes"]["hybrid"]["graph_traversal"]["max_paths"] == 1
    assert report["hybrid_delta_vs_vector"]["recall_at_k"] == 0


def test_m4_fallback_requires_vector_evidence() -> None:
    rows = predictions()
    hybrid = next(row for row in rows if row["id"] == "q0" and row["mode"] == "hybrid")
    hybrid["retrieved"] = []
    hybrid["trace"] = {"graph": {"status": "fallback", "paths": []}}
    report = evaluate(golden(), rows)
    assert report["modes"]["hybrid"]["fallback_correctness"] == 19 / 20


def test_m4_rejects_duplicate_case_mode_rows() -> None:
    rows = predictions()
    rows.append(rows[0])
    try:
        evaluate(golden(), rows)
    except ValueError as exc:
        assert "one row" in str(exc)
    else:
        raise AssertionError("duplicate result was accepted")


def test_m4_nearest_rank_percentile() -> None:
    assert percentile([5, 1, 3, 2, 4], 0.95) == 5
