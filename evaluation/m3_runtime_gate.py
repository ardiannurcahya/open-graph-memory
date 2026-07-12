"""Run M3's real API/worker graph checks against a fresh Compose stack."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from runtime_gate import auth, compose, multipart, request, sql, wait_ready


def wait_graph(compose_file: Path, document_ids: list[str]) -> None:
    deadline = time.monotonic() + 180
    states: list[str] = []
    quoted = ",".join("'" + item + "'" for item in document_ids)
    while time.monotonic() < deadline:
        states = sql(
            compose_file,
            f"select graph_stage from documents where id in ({quoted}) order by id",
        ).splitlines()
        if all(state == "complete" for state in states):
            return
        if any(state == "failed" for state in states):
            raise RuntimeError(f"graph extraction failed: {states}")
        time.sleep(2)
    raise RuntimeError(f"graph jobs did not finish: {states}")


def upload(
    base: str, headers: dict[str, str], dataset_id: str, fixture: dict[str, Any]
) -> dict[str, Any]:
    payload, content_type = multipart(fixture["id"] + ".txt", fixture["text"].encode())
    status, document = request(
        base,
        "POST",
        f"/v1/datasets/{dataset_id}/documents",
        headers=headers,
        data=payload,
        content_type=content_type,
    )
    assert status == 201, document
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, default=Path("evaluation/m3_golden/v1.0.json"))
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    wait_ready(base)
    admin_key = os.environ["ADMIN_API_KEY"]
    admin = {"X-API-Key": admin_key}
    fixtures = json.loads(args.fixtures.read_text(encoding="utf-8"))
    status, project = request(base, "POST", "/v1/projects", {"name": "m3-primary"}, admin)
    assert status == 201, project
    status, outsider = request(base, "POST", "/v1/projects", {"name": "m3-outsider"}, admin)
    assert status == 201, outsider
    primary_headers, outsider_headers = auth(project), auth(outsider)
    status, dataset = request(base, "POST", "/v1/datasets", {"name": "m3-fixture"}, primary_headers)
    assert status == 201, dataset
    status, outsider_dataset = request(
        base, "POST", "/v1/datasets", {"name": "m3-outsider"}, outsider_headers
    )
    assert status == 201, outsider_dataset
    primary = [item for item in fixtures["documents"] if item.get("tenant", "primary") == "primary"]
    documents = [upload(base, primary_headers, dataset["id"], item) for item in primary]
    upload(
        base,
        outsider_headers,
        outsider_dataset["id"],
        next(item for item in fixtures["documents"] if item.get("tenant") == "other"),
    )
    ids = [item["id"] for item in documents]
    deadline = time.monotonic() + 180
    states: list[str] = []
    while time.monotonic() < deadline:
        states = [
            request(base, "GET", f"/v1/documents/{item}", headers=primary_headers)[1]["status"]
            for item in ids
        ]
        if all(state == "indexed" for state in states):
            break
        assert "failed" not in states, states
        time.sleep(2)
    else:
        raise RuntimeError(f"documents did not index: {states}")
    wait_graph(args.compose_file, ids)
    quoted = ",".join("'" + item + "'" for item in ids)
    assert int(
        sql(
            args.compose_file,
            "select count(*) from graph_extraction_jobs "
            f"where document_id in ({quoted}) and status = 'SUCCEEDED'",
        )
    ) == len(ids)
    assert int(
        sql(
            args.compose_file,
            "select count(*) from graph_extraction_runs "
            f"where document_id in ({quoted}) and status = 'SUCCEEDED'",
        )
    ) >= len(ids)
    assert (
        int(
            sql(
                args.compose_file,
                "select count(*) from graph_evidence "
                f"where document_id in ({quoted}) "
                "and (entity_id is not null or relation_id is not null)",
            )
        )
        > 0
    )
    status, graph = request(
        base,
        "GET",
        f"/v1/datasets/{dataset['id']}/graph?limit=100&depth=1",
        headers=primary_headers,
    )
    assert status == 200 and graph["entity_count"] >= 6 and graph["relation_count"] == 3, graph
    assert (
        request(
            base, "GET", f"/v1/datasets/{dataset['id']}/graph?limit=201", headers=primary_headers
        )[0]
        == 422
    )
    assert (
        request(base, "GET", f"/v1/datasets/{dataset['id']}/graph", headers=outsider_headers)[0]
        == 404
    )
    relation = graph["relations"][0]
    assert relation["citations"]
    status, reviewed = request(
        base,
        "PATCH",
        f"/v1/relations/{relation['id']}/review",
        {"review_state": "approved"},
        primary_headers,
    )
    assert status == 200 and reviewed["review_state"] == "approved", reviewed
    assert (
        request(
            base,
            "PATCH",
            f"/v1/relations/{relation['id']}/review",
            {"review_state": "rejected"},
            primary_headers,
        )[0]
        == 409
    )
    job_id = sql(
        args.compose_file, f"select id from graph_extraction_jobs where document_id='{ids[0]}'"
    )
    before = int(
        sql(args.compose_file, f"select count(*) from graph_evidence where document_id='{ids[0]}'")
    )
    compose(
        args.compose_file,
        "exec",
        "-T",
        "worker",
        "celery",
        "-A",
        "worker.main.celery_app",
        "call",
        "graph.extract_job",
        "--args",
        json.dumps([job_id]),
    )
    time.sleep(2)
    assert (
        int(
            sql(
                args.compose_file,
                f"select count(*) from graph_evidence where document_id='{ids[0]}'",
            )
        )
        == before
    )
    # Projection reconciliation deletes only this document's stale evidence, not shared entities.
    compose(
        args.compose_file,
        "exec",
        "-T",
        "worker",
        "celery",
        "-A",
        "worker.main.celery_app",
        "call",
        "graph.reconcile_jobs",
    )
    neo4j = (
        "MATCH (e:Evidence {project_id: '"
        + project["id"]
        + "', dataset_id: '"
        + dataset["id"]
        + "'}) RETURN count(e)"
    )
    assert (
        int(
            compose(
                args.compose_file,
                "exec",
                "-T",
                "neo4j",
                "sh",
                "-c",
                'cypher-shell -u "${NEO4J_AUTH%%/*}" -p "${NEO4J_AUTH#*/}" --format plain "$1"',
                "sh",
                neo4j,
            ).splitlines()[-1]
        )
        > 0
    )
    print("M3 runtime gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
