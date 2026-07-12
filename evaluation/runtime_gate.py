"""Exercise the complete M2 runtime and write evaluator predictions."""

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def request(
    base: str,
    method: str,
    path: str,
    body: Any = None,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    content_type: str = "application/json",
) -> tuple[int, Any]:
    payload = (
        data if data is not None else (json.dumps(body).encode() if body is not None else None)
    )
    req = urllib.request.Request(
        base + path,
        data=payload,
        method=method,
        headers={"Content-Type": content_type, **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw else None


def wait_ready(base: str, timeout: float = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if request(base, "GET", "/ready")[0] == 200:
                return
        except OSError:
            pass
        time.sleep(2)
    raise RuntimeError("API did not become ready")


def multipart(filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "m2-runtime-gate-boundary"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{filename}"\r\nContent-Type: text/plain\r\n\r\n'
        ).encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, f"multipart/form-data; boundary={boundary}"


def compose(compose_file: Path, *args: str) -> str:
    command = ["docker", "compose", "--env-file", ".env", "-f", str(compose_file), *args]
    return subprocess.run(command, check=True, text=True, capture_output=True).stdout.strip()


def sql(compose_file: Path, statement: str) -> str:
    return compose(
        compose_file,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        os.getenv("POSTGRES_USER", "opengraphrag"),
        "-d",
        os.getenv("POSTGRES_DB", "opengraphrag"),
        "-Atqc",
        statement,
    )


def auth(project: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": project["api_key"], "X-Project-ID": project["id"]}


def expected_document_count(fixtures: dict[str, Any]) -> int:
    """Return the number of documents the runtime gate actually uploads."""
    documents = fixtures.get("documents")
    if not isinstance(documents, list):
        raise ValueError("fixtures must contain a documents list")
    return len(documents)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, default=Path("evaluation/fixtures/v1.0.json"))
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    wait_ready(base)
    admin_key = os.getenv("ADMIN_API_KEY")
    if not admin_key:
        raise RuntimeError("ADMIN_API_KEY must match the API runtime environment")
    admin = {"X-API-Key": admin_key}
    status, project = request(base, "POST", "/v1/projects", {"name": "m2-evaluation"}, admin)
    assert status == 201, project
    status, outsider = request(base, "POST", "/v1/projects", {"name": "m2-isolation"}, admin)
    assert status == 201, outsider
    status, dataset = request(base, "POST", "/v1/datasets", {"name": "golden-v1.0"}, auth(project))
    assert status == 201, dataset

    fixtures = json.loads(args.fixtures.read_text())
    expected_documents = expected_document_count(fixtures)
    documents: list[dict[str, Any]] = []
    for fixture in fixtures["documents"]:
        content = fixture["text"].encode()
        payload, content_type = multipart(fixture["evidence_id"] + ".txt", content)
        status, document = request(
            base,
            "POST",
            f"/v1/datasets/{dataset['id']}/documents",
            headers=auth(project),
            data=payload,
            content_type=content_type,
        )
        assert status == 201, document
        documents.append(document)

    assert len(documents) == expected_documents, (len(documents), expected_documents)

    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        states = [
            request(base, "GET", f"/v1/documents/{doc['id']}", headers=auth(project))[1]["status"]
            for doc in documents
        ]
        if all(state == "indexed" for state in states):
            break
        assert not any(state == "failed" for state in states), states
        time.sleep(2)
    else:
        raise RuntimeError(f"documents did not index: {states}")

    doc_ids = [doc["id"] for doc in documents]
    quoted = ",".join("'" + value.replace("'", "''") + "'" for value in doc_ids)
    chunk_count = int(
        sql(args.compose_file, f"select count(*) from chunks where document_id in ({quoted})")
    )
    assert chunk_count == expected_documents, (chunk_count, expected_documents)
    collection = os.getenv("QDRANT_COLLECTION", "opengraphrag_chunks")
    qdrant_script = (
        "import urllib.request,json; "
        f"u='http://qdrant:6333/collections/{collection}/points/count'; "
        "print(json.load(urllib.request.urlopen(u,data=b'{\"exact\":true}'))['result']['count'])"
    )
    point_count = int(
        compose(
            args.compose_file,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            qdrant_script,
        )
    )
    assert point_count == chunk_count, (point_count, chunk_count)

    # Re-dispatching and re-running a succeeded job must not duplicate authoritative artifacts.
    compose(
        args.compose_file,
        "exec",
        "-T",
        "worker",
        "celery",
        "-A",
        "worker.main.celery_app",
        "call",
        "ingestion.dispatch_outbox",
    )
    job_id = sql(
        args.compose_file, f"select id from indexing_jobs where document_id='{doc_ids[0]}'"
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
        "ingestion.index_document",
        "--args",
        json.dumps([job_id]),
    )
    time.sleep(3)
    assert (
        int(sql(args.compose_file, f"select count(*) from chunks where document_id in ({quoted})"))
        == chunk_count
    )

    # A valid key from another project cannot address this dataset.
    assert request(base, "GET", f"/v1/datasets/{dataset['id']}", headers=auth(outsider))[0] == 404
    assert (
        request(
            base,
            "POST",
            "/v1/query",
            {"dataset_id": dataset["id"], "query": "PostgreSQL metadata", "mode": "vector_only"},
            auth(outsider),
        )[0]
        == 404
    )

    mapping_raw = sql(
        args.compose_file,
        "select c.id || '|' || regexp_replace(d.filename, '\\.txt$', '') "
        "from chunks c join documents d on d.id=c.document_id "
        f"where d.id in ({quoted})",
    )
    evidence = dict(line.split("|", 1) for line in mapping_raw.splitlines())
    golden = json.loads(args.golden.read_text())
    predictions = []
    for case in golden["cases"]:
        started = time.monotonic()
        status, result = request(
            base,
            "POST",
            "/v1/query",
            {
                "dataset_id": dataset["id"],
                "query": case["question"],
                "mode": "vector_only",
                "top_k": 5,
            },
            auth(project),
        )
        assert status == 200, (case["id"], result)
        retrieved = [evidence[item] for item in result["retrieval_trace"]["chunk_ids"]]
        citations = [evidence[item["chunk_id"]] for item in result["citations"]]
        refused = "cannot answer from the supplied evidence" in result["answer"].lower()
        predictions.append(
            {
                "id": case["id"],
                "answer": result["answer"],
                "retrieved": retrieved,
                "citations": citations,
                "unanswerable": refused,
                "latency_ms": (time.monotonic() - started) * 1000,
                "usage": result["usage"],
            }
        )
        trace_id = result["retrieval_trace"]["trace_id"]
        assert (
            sql(args.compose_file, f"select status from query_logs where trace_id='{trace_id}'")
            == "succeeded"
        )

    args.predictions.parent.mkdir(parents=True, exist_ok=True)
    args.predictions.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in predictions)
    )
    print(f"wrote {len(predictions)} real predictions to {args.predictions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
