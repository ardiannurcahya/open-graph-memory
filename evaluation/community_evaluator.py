"""Score saved community-retrieval cases without external services."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

REFUSAL_MARKERS = ("cannot answer", "can't answer", "not enough evidence", "insufficient evidence")


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * quantile) - 1)]


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("cases must be a list")
    return cases


def evaluate(cases: list[dict[str, Any]], k: int = 5) -> dict[str, Any]:
    if k < 1:
        raise ValueError("k must be positive")
    details: list[dict[str, Any]] = []
    for case in cases:
        expected_report = case.get("expected_report_id")
        expected_chunks = set(map(str, case.get("expected_backing_chunk_ids", [])))
        response = case.get("response", {})
        trace = response.get("retrieval_trace", {})
        community = trace.get("community", {})
        reports = set(map(str, community.get("report_ids", [])))
        hydrated = set(map(str, community.get("backing_chunk_ids", [])))
        retrieved = set(map(str, trace.get("chunk_ids", [])[:k]))
        citations = set(map(str, case.get("citation_chunk_ids", [])))
        answer = str(response.get("answer", "")).lower()
        expected_answerable = bool(case.get("answerable", True))
        refused = bool(case.get("unanswerable")) or any(
            marker in answer for marker in REFUSAL_MARKERS
        )
        details.append(
            {
                "id": str(case["id"]),
                "report_hit": expected_report is None or str(expected_report) in reports,
                "backing_hydration": expected_chunks.issubset(hydrated)
                and expected_chunks.issubset(retrieved),
                "citation_correctness": citations.issubset(retrieved)
                and (bool(citations) if expected_answerable else not citations),
                "answerability_correct": not refused if expected_answerable else refused,
                "latency_ms": float(response.get("latency_ms", trace.get("latency_ms", 0))),
            }
        )
    count = len(details)
    if not count:
        raise ValueError("at least one case is required")
    return {
        "schema_version": "1.0",
        "cases": count,
        "report_hit_rate": sum(item["report_hit"] for item in details) / count,
        "backing_hydration_rate": sum(item["backing_hydration"] for item in details) / count,
        "citation_correctness": sum(item["citation_correctness"] for item in details) / count,
        "answerability_accuracy": sum(item["answerability_correct"] for item in details) / count,
        "latency_ms": {
            "p50": percentile([float(item["latency_ms"]) for item in details], 0.5),
            "p95": percentile([float(item["latency_ms"]) for item in details], 0.95),
        },
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()
    report = evaluate(load_cases(args.cases), args.k)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
