import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from m3_evaluator import deterministic_predictions, evaluate


def test_m3_fixture_scores_deterministic_extractor_without_fabricated_relations() -> None:
    golden = json.loads(open("evaluation/m3_golden/v1.0.json", encoding="utf-8").read())
    predictions = deterministic_predictions(golden)
    metrics = evaluate(golden, predictions)
    assert metrics["entity"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    assert metrics["relation"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    assert metrics["provenance_completeness"] == 1.0
    assert {relation["type"] for relation in predictions["relations"]} == {
        "EMPLOYS",
        "BUILT_BY",
        "LEADS",
    }


def test_m3_metrics_penalize_missing_graph_artifacts() -> None:
    golden = json.loads(open("evaluation/m3_golden/v1.0.json", encoding="utf-8").read())
    metrics = evaluate(golden, {"entities": [], "relations": [], "idempotency": 0.0})
    assert metrics["entity"]["recall"] == 0.0
    assert metrics["relation"]["precision"] == 0.0
    assert metrics["provenance_completeness"] == 0.0
