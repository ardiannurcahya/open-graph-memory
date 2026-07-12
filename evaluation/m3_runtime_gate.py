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
    outsider_document = upload(
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
    wait_graph(args.compose_file, [outsider_document["id"]])
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
    for table in (
        "graph_extraction_runs",
        "canonical_entities",
        "relation_assertions",
        "graph_evidence",
    ):
        assert (
            int(
                sql(
                    args.compose_file,
                    f"select count(*) from {table} where created_at is null or updated_at is null",
                )
            )
            == 0
        ), table
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
        + "'}) WHERE e.created_at IS NOT NULL AND e.updated_at IS NOT NULL "
        + "AND e.document_id IS NOT NULL AND e.chunk_id IS NOT NULL "
        + "AND e.provider IS NOT NULL AND e.model IS NOT NULL "
        + "AND e.extractor_version IS NOT NULL AND e.prompt_version IS NOT NULL RETURN count(e)"
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
    # Deletion commits PostgreSQL intent first; the worker removes only the scoped Neo4j projection.
    deleted_document = ids[0]
    assert (
        request(base, "DELETE", f"/v1/documents/{deleted_document}", headers=primary_headers)[0]
        == 204
    )
    # Simulate a broker-accepted task lost before a worker starts it. Reconciliation must release
    # the expired delivery lease rather than leaving the deletion intent permanently published.
    sql(
        args.compose_file,
        "update graph_cleanup_outbox set published_at=now(), "
        "lease_expires_at=now() - interval '1 second', "
        "next_attempt_at=now(), attempts=1 where document_id='" + deleted_document + "'",
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
        "graph.reconcile_cleanup_outbox",
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        released = sql(
            args.compose_file,
            "select count(*) from graph_cleanup_outbox where document_id='"
            + deleted_document
            + "' and (completed_at is not null "
            "or (lease_expires_at is null and published_at is null))",
        )
        if released == "1":
            break
        time.sleep(1)
    else:
        raise RuntimeError("stale graph cleanup delivery lease was not reclaimed")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        completed = sql(
            args.compose_file,
            "select count(*) from graph_cleanup_outbox "
            f"where document_id='{deleted_document}' and completed_at is not null",
        )
        if completed == "1":
            break
        time.sleep(2)
    else:
        raise RuntimeError("document graph cleanup did not finish")
    assert (
        sql(args.compose_file, f"select count(*) from documents where id='{deleted_document}'")
        == "0"
    )
    # The authoritative graph must not retain deleted-only subjects, while shared rows survive.
    assert (
        int(
            sql(
                args.compose_file,
                "select count(*) from relation_assertions where project_id='"
                + project["id"]
                + "' and dataset_id='"
                + dataset["id"]
                + "' and relation_type='EMPLOYS'",
            )
        )
        == 0
    )
    assert (
        int(
            sql(
                args.compose_file,
                "select count(*) from canonical_entities where project_id='"
                + project["id"]
                + "' and dataset_id='"
                + dataset["id"]
                + "' and canonical_name='Alice'",
            )
        )
        == 0
    )
    status, graph = request(
        base,
        "GET",
        f"/v1/datasets/{dataset['id']}/graph?limit=100&depth=1",
        headers=primary_headers,
    )
    assert status == 200, graph
    assert all(relation["relation_type"] != "EMPLOYS" for relation in graph["relations"]), graph
    assert {"Acme Labs", "Alice Nguyen"} <= {node["canonical_name"] for node in graph["nodes"]}, (
        graph
    )
    status, outsider_graph = request(
        base,
        "GET",
        f"/v1/datasets/{outsider_dataset['id']}/graph?limit=100&depth=1",
        headers=outsider_headers,
    )
    assert status == 200 and any(
        relation["relation_type"] == "EMPLOYS" for relation in outsider_graph["relations"]
    ), outsider_graph
    # A reconciliation replay reads authoritative rows and cannot recreate deleted artifacts.
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
    assert (
        int(
            sql(
                args.compose_file,
                "select count(*) from relation_assertions where project_id='"
                + project["id"]
                + "' and dataset_id='"
                + dataset["id"]
                + "' and relation_type='EMPLOYS'",
            )
        )
        == 0
    )
    deleted_graph = (
        "MATCH (n) WHERE n.project_id = '"
        + project["id"]
        + "' AND n.dataset_id = '"
        + dataset["id"]
        + "' AND (n:Document OR n:Chunk OR n:Evidence) "
        + "AND (n.id = '"
        + deleted_document
        + "' OR n.document_id = '"
        + deleted_document
        + "') RETURN count(n)"
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
                deleted_graph,
            ).splitlines()[-1]
        )
        == 0
    )
    deleted_subjects = (
        "MATCH (n) WHERE n.project_id = '"
        + project["id"]
        + "' AND n.dataset_id = '"
        + dataset["id"]
        + "' AND ((n:Relation AND n.relation_type = 'EMPLOYS') "
        + "OR (n:Entity AND n.canonical_name = 'Alice')) RETURN count(n)"
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
                deleted_subjects,
            ).splitlines()[-1]
        )
        == 0
    )
    surviving_subjects = (
        "MATCH (n) WHERE (n.project_id = '"
        + project["id"]
        + "' AND n.dataset_id = '"
        + dataset["id"]
        + "' AND n:Entity AND n.canonical_name IN ['Acme Labs', 'Alice Nguyen']) "
        + "OR (n.project_id = '"
        + outsider["id"]
        + "' AND n.dataset_id = '"
        + outsider_dataset["id"]
        + "' AND n:Relation AND n.relation_type = 'EMPLOYS') RETURN count(n)"
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
                surviving_subjects,
            ).splitlines()[-1]
        )
        == 3
    )
    assert (
        request(base, "DELETE", f"/v1/datasets/{dataset['id']}", headers=primary_headers)[0] == 204
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        completed = sql(
            args.compose_file,
            "select count(*) from graph_cleanup_outbox "
            f"where dataset_id='{dataset['id']}' and target='DATASET' and completed_at is not null",
        )
        if completed == "1":
            break
        time.sleep(2)
    else:
        raise RuntimeError("dataset graph cleanup did not finish")
    assert (
        sql(args.compose_file, f"select count(*) from datasets where id='{dataset['id']}'") == "0"
    )
    dataset_graph = (
        "MATCH (n) WHERE n.project_id = '"
        + project["id"]
        + "' AND n.dataset_id = '"
        + dataset["id"]
        + "' RETURN count(n)"
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
                dataset_graph,
            ).splitlines()[-1]
        )
        == 0
    )
    outsider_graph = (
        "MATCH (n:Document {project_id: '"
        + outsider["id"]
        + "', dataset_id: '"
        + outsider_dataset["id"]
        + "', id: '"
        + outsider_document["id"]
        + "'}) RETURN count(n)"
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
                outsider_graph,
            ).splitlines()[-1]
        )
        == 1
    )
    print("M3 runtime gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
