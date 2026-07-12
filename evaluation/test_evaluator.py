import json
import subprocess
import sys
from pathlib import Path

import pytest
from evaluator import evaluate, percentile
from runtime_gate import expected_document_count


def golden(count: int = 20) -> dict[str, object]:
    return {
        "version": "test-v1",
        "cases": [
            {"id": f"q{i}", "answerable": i != 19, "evidence_ids": [] if i == 19 else [f"c{i}"]}
            for i in range(count)
        ],
    }


def test_metrics_are_deterministic() -> None:
    predictions = {
        f"q{i}": {
            "retrieved": [f"c{i}", "noise"],
            "citations": [] if i == 19 else [f"c{i}"],
            "answer": "cannot answer" if i == 19 else "answer",
            "latency_ms": i + 1,
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "estimated_cost_usd": 0.001},
        }
        for i in range(20)
    }
    result = evaluate(golden(), predictions, 1)
    assert result["metrics"]["recall_at_k"] == 1
    assert result["metrics"]["citation_correctness"] == 1
    assert result["metrics"]["unanswerable_accuracy"] == 1
    assert result["metrics"]["latency_ms"] == {"p50": 10.0, "p95": 19.0}
    assert result["metrics"]["token_usage"]["total"] == 60
    assert result["metrics"]["estimated_cost_usd"] == 0.02


def test_wrong_and_out_of_context_citations_fail() -> None:
    predictions = {
        "q0": {"retrieved": ["c0"], "citations": ["invented"], "answer": "answer"},
        "extra": {},
    }
    result = evaluate(golden(), predictions, 5)
    assert result["details"][0]["citation_correct"] is False
    assert result["metrics"]["missing_predictions"] == 19
    assert result["metrics"]["extra_predictions"] == 1


def test_golden_size_is_enforced() -> None:
    with pytest.raises(ValueError, match="20-30"):
        evaluate(golden(19), {}, 5)


def test_nearest_rank_percentile() -> None:
    assert percentile([5, 1, 3, 2, 4], 0.95) == 5
    assert percentile([], 0.5) == 0


def test_runtime_gate_matches_public_document_state_values() -> None:
    source = Path(__file__).with_name("runtime_gate.py").read_text()
    assert 'state == "indexed"' in source
    assert 'state == "failed"' in source


def test_runtime_gate_derives_document_count_from_fixtures() -> None:
    fixtures = {"documents": [{"evidence_id": f"doc-{i}"} for i in range(19)]}

    assert expected_document_count(fixtures) == 19
    assert len(golden(20)["cases"]) == 20


def test_cli_writes_report(tmp_path: Path) -> None:
    golden_path, predictions_path, output = (
        tmp_path / "golden.json",
        tmp_path / "results.jsonl",
        tmp_path / "report.json",
    )
    golden_path.write_text(json.dumps(golden()), encoding="utf-8")
    predictions_path.write_text("", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("evaluator.py")),
            "--golden",
            str(golden_path),
            "--predictions",
            str(predictions_path),
            "--output",
            str(output),
        ],
        check=False,
    )
    assert completed.returncode == 0
    assert json.loads(output.read_text())["cases"] == 20
