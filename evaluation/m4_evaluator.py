"""Deterministically score real M4 API results by retrieval mode."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

REFUSAL_MARKERS = ("cannot answer", "can't answer", "not enough evidence", "insufficient evidence")
MODES = ("vector_only", "graph_only", "hybrid")


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * quantile) - 1)]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                row = json.loads(line)
                if not isinstance(row.get("id"), str) or row.get("mode") not in MODES:
                    raise ValueError(f"{path}:{line_number}: id and supported mode are required")
                rows.append(row)
    return rows


def metric_summary(details: list[dict[str, Any]], mode: str) -> dict[str, float]:
    if not details:
        raise ValueError(f"no applicable M4 cases for {mode}")
    count = len(details)
    return {
        "recall_at_k": sum(float(item["recall_at_k"]) for item in details) / count,
        "evidence_hit_rate": sum(float(item["evidence_hit"]) for item in details) / count,
        "citation_correctness": sum(float(item["citation_correct"]) for item in details) / count,
        "answerability_accuracy": sum(float(item["answerability_correct"]) for item in details)
        / count,
        "fallback_correctness": sum(float(item["fallback_correct"]) for item in details) / count,
    }


def evaluate(
    golden: dict[str, Any], predictions: list[dict[str, Any]], k: int = 5
) -> dict[str, Any]:
    cases = golden.get("cases", [])
    if not 20 <= len(cases) <= 30:
        raise ValueError("M4 golden set must contain 20-30 cases")
    expected = {str(case["id"]): case for case in cases}
    rows = {(str(row["id"]), str(row["mode"])): row for row in predictions}
    if len(rows) != len(predictions):
        raise ValueError("predictions must contain one row per case and mode")
    reports: dict[str, Any] = {}
    for mode in MODES:
        details: list[dict[str, Any]] = []
        latencies: list[float] = []
        traversal_counts: list[float] = []
        for case_id, case in expected.items():
            row = rows.get((case_id, mode), {})
            retrieved = [str(item) for item in row.get("retrieved", [])][:k]
            cited = [str(item) for item in row.get("citations", [])]
            evidence = set(case.get("evidence_ids", []))
            answerable = bool(case["answerable"])
            refused = bool(row.get("unanswerable")) or any(
                marker in str(row.get("answer", "")).lower() for marker in REFUSAL_MARKERS
            )
            graph = row.get("trace", {}).get("graph", {})
            paths = graph.get("paths", []) if isinstance(graph, dict) else []
            details.append(
                {
                    "id": case_id,
                    "applicable": mode in case.get("applicable_modes", MODES),
                    "recall_at_k": len(evidence & set(retrieved)) / len(evidence) if evidence else 1.0,
                    "evidence_hit": bool(evidence & set(retrieved)) if evidence else True,
                    "citation_correct": set(cited).issubset(retrieved)
                    and (bool(cited) if answerable else not cited),
                    "answerability_correct": (not refused) if answerable else refused,
                    "fallback_correct": mode == "vector_only"
                    or graph.get("status") != "fallback"
                    or bool(retrieved),
                    "traversal_paths": len(paths),
                    "missing": not bool(row),
                }
            )
            latencies.append(float(row.get("latency_ms", 0)))
            traversal_counts.append(float(len(paths)))
        relevant = [detail for detail in details if detail["applicable"]]
        reports[mode] = {
            **metric_summary(relevant, mode),
            "applicable_cases": len(relevant),
            "all_cases": metric_summary(details, mode),
            "latency_ms": {"p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95)},
            "graph_traversal": {
                "p95_paths": percentile(traversal_counts, 0.95),
                "max_paths": max(traversal_counts, default=0),
            },
            "missing_predictions": sum(detail["missing"] for detail in details),
            "details": details,
        }
    graph_answerable = {
        str(case["id"])
        for case in cases
        if case["answerable"] and "graph_only" in case.get("applicable_modes", MODES)
    }

    def graph_quality(mode: str, name: str) -> float:
        details = [item for item in reports[mode]["details"] if item["id"] in graph_answerable]
        return sum(float(item[name]) for item in details) / len(details)

    return {
        "schema_version": "1.0",
        "golden_version": golden["version"],
        "k": k,
        "modes": reports,
        "hybrid_delta_vs_vector": {
            "recall_at_k": reports["hybrid"]["recall_at_k"] - reports["vector_only"]["recall_at_k"],
            "evidence_hit_rate": reports["hybrid"]["evidence_hit_rate"]
            - reports["vector_only"]["evidence_hit_rate"],
        },
        "graph_answerable_quality_delta_vs_vector": {
            name: graph_quality("hybrid", name) - graph_quality("vector_only", name)
            for name in ("citation_correct", "answerability_correct")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()
    if args.k < 1:
        parser.error("k must be positive")
    report = evaluate(
        json.loads(args.golden.read_text(encoding="utf-8")), load_jsonl(args.predictions), args.k
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["modes"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
