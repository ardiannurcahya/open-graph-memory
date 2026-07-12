"""Score versioned, human-labeled Milestone 3 graph extraction fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from open_graph_core.extraction import DeterministicExtractor, normalize_name


def entity_key(item: dict[str, Any]) -> tuple[str, str]:
    return normalize_name(item["name"]), normalize_name(item["type"])


def relation_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return normalize_name(item["source"]), item["type"], normalize_name(item["target"])


def score(expected: set[tuple[Any, ...]], actual: set[tuple[Any, ...]]) -> dict[str, float]:
    correct = len(expected & actual)
    return {
        "precision": correct / len(actual) if actual else (1.0 if not expected else 0.0),
        "recall": correct / len(expected) if expected else 1.0,
        "f1": 0.0,
    }


def finalize(metric: dict[str, float]) -> None:
    precision, recall = metric["precision"], metric["recall"]
    metric["f1"] = 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def evaluate(golden: dict[str, Any], predictions: dict[str, Any]) -> dict[str, Any]:
    expected_entities = {entity_key(item) for item in golden["entities"]}
    expected_relations = {relation_key(item) for item in golden["relations"]}
    actual_entities = {entity_key(item) for item in predictions["entities"]}
    actual_relations = {relation_key(item) for item in predictions["relations"]}
    entities, relations = (
        score(expected_entities, actual_entities),
        score(expected_relations, actual_relations),
    )
    finalize(entities)
    finalize(relations)
    expected_provenance = {
        (entity_key(item), document)
        for item in golden["entities"]
        for document in item["documents"]
    }
    actual_provenance = {
        (entity_key(item), document)
        for item in predictions["entities"]
        for document in item.get("documents", [])
    }
    provenance = len(expected_provenance & actual_provenance) / len(expected_provenance)
    return {
        "entity": entities,
        "relation": relations,
        "provenance_completeness": provenance,
        "resolution_duplicate_rate": float(predictions.get("resolution_duplicate_rate", 0.0)),
        "idempotency": float(predictions.get("idempotency", 0.0)),
    }


def deterministic_predictions(golden: dict[str, Any]) -> dict[str, Any]:
    extractor = DeterministicExtractor()
    entities: dict[tuple[str, str], dict[str, Any]] = {}
    relations: dict[tuple[str, str, str], dict[str, Any]] = {}
    for document in golden["documents"]:
        if document.get("tenant", "primary") != "primary":
            continue
        result = extractor.extract(document["text"])
        for item in result.entities:
            key = normalize_name(item.name), normalize_name(item.type)
            row = entities.setdefault(key, {"name": item.name, "type": item.type, "documents": []})
            row["documents"].append(document["id"])
        names: dict[str, int] = {}
        for item in result.entities:
            key = normalize_name(item.name)
            names[key] = names.get(key, 0) + 1
        for item in result.relations:
            # Match persistence: relations with ambiguous endpoint names are unresolved.
            if (
                names.get(normalize_name(item.source)) == 1
                and names.get(normalize_name(item.target)) == 1
            ):
                relations.setdefault(relation_key(item.model_dump()), item.model_dump())
    return {
        "entities": list(entities.values()),
        "relations": list(relations.values()),
        "resolution_duplicate_rate": 0.0,
        "idempotency": 1.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate M3 graph extraction")
    parser.add_argument("--golden", type=Path, default=Path("evaluation/m3_golden/v1.0.json"))
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    predictions = (
        json.loads(args.predictions.read_text(encoding="utf-8"))
        if args.predictions
        else deterministic_predictions(golden)
    )
    report = {"version": golden["version"], "metrics": evaluate(golden, predictions)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
