"""Deterministic, dependency-free evaluation of RAG JSONL result artifacts."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

REFUSAL_MARKERS = ("cannot answer", "can't answer", "not enough evidence", "insufficient evidence")


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            item_id = row.get("id")
            if not isinstance(item_id, str) or item_id in rows:
                raise ValueError(f"{path}:{line_number}: id must be a unique string")
            rows[item_id] = row
    return rows


def percentile(values: list[float], quantile: float) -> float:
    """Return nearest-rank percentile, avoiding interpolation/version differences."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def _ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [value if isinstance(value, str) else str(value.get("id", "")) for value in values]


def evaluate(
    golden: dict[str, Any], predictions: dict[str, dict[str, Any]], k: int
) -> dict[str, Any]:
    cases = golden.get("cases", [])
    if not isinstance(cases, list) or not 20 <= len(cases) <= 30:
        raise ValueError("golden set must contain 20-30 cases")
    case_ids = {case["id"] for case in cases}
    missing_ids = case_ids - predictions.keys()
    extra_ids = predictions.keys() - case_ids
    details: list[dict[str, Any]] = []
    latencies: list[float] = []
    prompt_tokens = completion_tokens = 0
    estimated_cost = 0.0
    for case in cases:
        prediction = predictions.get(case["id"], {})
        retrieved = _ids(prediction.get("retrieved"))[:k]
        expected = set(case.get("evidence_ids", []))
        cited = set(_ids(prediction.get("citations")))
        answer = str(prediction.get("answer", "")).lower()
        answerable = bool(case["answerable"])
        recall = len(expected.intersection(retrieved)) / len(expected) if expected else 1.0
        evidence_hit = bool(expected.intersection(retrieved)) if expected else True
        citation_correct = cited.issubset(set(retrieved)) and (
            bool(cited) if answerable else not cited
        )
        refused = bool(prediction.get("unanswerable")) or any(x in answer for x in REFUSAL_MARKERS)
        unanswerable_correct = refused if not answerable else not refused
        latency = float(prediction.get("latency_ms", 0))
        usage = prediction.get("usage", {})
        prompt_tokens += int(usage.get("prompt_tokens", 0))
        completion_tokens += int(usage.get("completion_tokens", 0))
        estimated_cost += float(usage.get("estimated_cost_usd", 0))
        latencies.append(latency)
        details.append(
            {
                "id": case["id"],
                "recall_at_k": recall,
                "evidence_hit": evidence_hit,
                "citation_correct": citation_correct,
                "unanswerable_correct": unanswerable_correct,
            }
        )
    count = len(details)

    def mean(key: str) -> float:
        return sum(float(row[key]) for row in details) / count

    return {
        "schema_version": "1.0",
        "golden_version": golden["version"],
        "k": k,
        "cases": count,
        "metrics": {
            "recall_at_k": mean("recall_at_k"),
            "evidence_hit_rate": mean("evidence_hit"),
            "citation_correctness": mean("citation_correct"),
            "unanswerable_accuracy": mean("unanswerable_correct"),
            "latency_ms": {
                "p50": percentile(latencies, 0.50),
                "p95": percentile(latencies, 0.95),
            },
            "token_usage": {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": prompt_tokens + completion_tokens,
            },
            "estimated_cost_usd": round(estimated_cost, 8),
            "missing_predictions": len(missing_ids),
            "extra_predictions": len(extra_ids),
        },
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score deterministic RAG evaluation results")
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument(
        "--predictions", type=Path, required=True, help="One result object per JSONL line"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()
    if args.k < 1:
        parser.error("k must be positive")
    report = evaluate(load_json(args.golden), load_jsonl(args.predictions), args.k)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
