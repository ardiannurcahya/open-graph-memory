"""Exercise M4 retrieval modes through the public API on indexed graph fixtures."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from m3_runtime_gate import upload, wait_graph
from runtime_gate import auth, compose, request, sql, wait_ready

MODES = ("vector_only", "graph_only", "hybrid")


def wait_indexed(base: str, headers: dict[str, str], document_ids: list[str]) -> None:
    deadline = time.monotonic() + 180
    states: list[str] = []
    while time.monotonic() < deadline:
        states = [request(base, "GET", f"/v1/documents/{item}", headers=headers)[1]["status"] for item in document_ids]
        if all(state == "indexed" for state in states):
            return
        if "failed" in states:
            raise RuntimeError(f"indexing failed: {states}")
        time.sleep(2)
    raise RuntimeError(f"documents did not index: {states}")


def evidence_mapping(compose_file: Path, document_ids: list[str]) -> dict[str, str]:
    quoted = ",".join("'" + item + "'" for item in document_ids)
    rows = sql(
        compose_file,
        "select c.id || '|' || regexp_replace(d.filename, '\\.txt$', '') "
        "from chunks c join documents d on d.id = c.document_id "
        f"where c.document_id in ({quoted})",
    )
    return dict(row.split("|", 1) for row in rows.splitlines())


def query_row(
    base: str, headers: dict[str, str], dataset_id: str, case: dict[str, Any], mode: str, evidence: dict[str, str]
) -> dict[str, Any]:
    started = time.monotonic()
    status, result = request(
        base,
        "POST",
        "/v1/query",
        {"dataset_id": dataset_id, "query": case["question"], "mode": mode, "top_k": 5, "graph_depth": 2, "graph_fanout": 3},
        headers,
    )
    assert status == 200, (case["id"], mode, result)
    trace = result["retrieval_trace"]
    trace_id = trace["trace_id"]
    refused = "cannot answer from the supplied evidence" in result["answer"].lower()
    return {
        "id": case["id"], "mode": mode, "answer": result["answer"],
        "retrieved": [evidence[item] for item in trace["chunk_ids"]],
        "citations": [evidence[item["chunk_id"]] for item in result["citations"]],
        "unanswerable": refused, "latency_ms": (time.monotonic() - started) * 1000,
        "trace": trace, "usage": result["usage"], "trace_id": trace_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, default=Path("evaluation/m3_golden/v1.0.json"))
    parser.add_argument("--golden", type=Path, default=Path("evaluation/m4_golden/v1.0.json"))
    parser.add_argument("--predictions", type=Path, required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    wait_ready(base)
    admin = {"X-API-Key": os.environ["ADMIN_API_KEY"]}
    fixtures = json.loads(args.fixtures.read_text(encoding="utf-8"))
    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    status, project = request(base, "POST", "/v1/projects", {"name": "m4-primary"}, admin)
    assert status == 201, project
    status, outsider = request(base, "POST", "/v1/projects", {"name": "m4-outsider"}, admin)
    assert status == 201, outsider
    headers, outsider_headers = auth(project), auth(outsider)
    status, dataset = request(base, "POST", "/v1/datasets", {"name": "m4-fixture"}, headers)
    assert status == 201, dataset
    status, outsider_dataset = request(base, "POST", "/v1/datasets", {"name": "m4-outsider"}, outsider_headers)
    assert status == 201, outsider_dataset
    primary = [item for item in fixtures["documents"] if item.get("tenant", "primary") == "primary"]
    documents = [upload(base, headers, dataset["id"], item) for item in primary]
    outsider_document = upload(base, outsider_headers, outsider_dataset["id"], next(item for item in fixtures["documents"] if item.get("tenant") == "other"))
    ids = [item["id"] for item in documents]
    wait_indexed(base, headers, ids)
    wait_indexed(base, outsider_headers, [outsider_document["id"]])
    wait_graph(args.compose_file, ids)
    wait_graph(args.compose_file, [outsider_document["id"]])
    evidence = evidence_mapping(args.compose_file, ids)
    # The API authorization boundary is tested before scoring to prevent cross-tenant evidence leakage.
    assert request(base, "POST", "/v1/query", {"dataset_id": dataset["id"], "query": "Atlas", "mode": "hybrid"}, outsider_headers)[0] == 404
    rows = []
    for mode in MODES:
        for case in golden["cases"]:
            row = query_row(base, headers, dataset["id"], case, mode, evidence)
            assert sql(args.compose_file, f"select status from query_logs where trace_id='{row['trace_id']}'") == "succeeded"
            assert len(row["trace"].get("graph", {}).get("paths", [])) <= 6
            row.pop("trace_id")
            rows.append(row)
    # A real Neo4j outage must preserve scoped vector evidence for graph_only and hybrid requests.
    compose(args.compose_file, "stop", "neo4j")
    outage_case = golden["cases"][0]
    for mode in ("graph_only", "hybrid"):
        row = query_row(base, headers, dataset["id"], outage_case, mode, evidence)
        assert row["trace"]["graph"]["status"] == "fallback", row["trace"]
        assert row["retrieved"], row
    args.predictions.parent.mkdir(parents=True, exist_ok=True)
    args.predictions.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    print(f"wrote {len(rows)} M4 API predictions to {args.predictions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
