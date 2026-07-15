from community_evaluator import evaluate, percentile


def test_scores_report_hydration_citations_and_latency() -> None:
    report = evaluate(
        [
            {
                "id": "hit",
                "expected_report_id": "report-1",
                "expected_backing_chunk_ids": ["chunk-1"],
                "citation_chunk_ids": ["chunk-1"],
                "response": {
                    "answer": "Supported [1].",
                    "latency_ms": 12,
                    "retrieval_trace": {
                        "chunk_ids": ["chunk-1"],
                        "community": {"report_ids": ["report-1"], "backing_chunk_ids": ["chunk-1"]},
                    },
                },
            },
            {
                "id": "empty",
                "answerable": False,
                "citation_chunk_ids": [],
                "response": {
                    "answer": "I cannot answer from supplied evidence.",
                    "latency_ms": 4,
                    "retrieval_trace": {
                        "chunk_ids": [],
                        "community": {"report_ids": [], "backing_chunk_ids": []},
                    },
                },
            },
        ]
    )

    assert report["report_hit_rate"] == 1
    assert report["backing_hydration_rate"] == 1
    assert report["citation_correctness"] == 1
    assert report["answerability_accuracy"] == 1
    assert report["latency_ms"] == {"p50": 4.0, "p95": 12.0}


def test_reports_fail_missing_backing_chunk() -> None:
    report = evaluate(
        [
            {
                "id": "missing",
                "expected_report_id": "report-1",
                "expected_backing_chunk_ids": ["chunk-1"],
                "response": {
                    "answer": "Answer [1].",
                    "retrieval_trace": {
                        "chunk_ids": [],
                        "community": {"report_ids": ["report-1"], "backing_chunk_ids": []},
                    },
                },
            }
        ]
    )

    assert report["report_hit_rate"] == 1
    assert report["backing_hydration_rate"] == 0
    assert percentile([3, 1, 2], 0.95) == 3
