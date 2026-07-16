"""Exercise structured graph APIs against indexed fixtures on a fresh Compose stack."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
from pathlib import Path
from typing import Any

from m3_runtime_gate import upload, wait_graph
from runtime_gate import auth, request, wait_ready


def wait_indexed(base: str, headers: dict[str, str], document_ids: list[str]) -> None:
    deadline = time.monotonic() + 180
    states: list[str] = []
    while time.monotonic() < deadline:
        states = [
            request(base, "GET", f"/v1/documents/{item}", headers=headers)[1]["status"]
            for item in document_ids
        ]
        if all(state == "indexed" for state in states):
            return
        if "failed" in states:
            raise RuntimeError(f"indexing failed: {states}")
        time.sleep(2)
    raise RuntimeError(f"documents did not index: {states}")


def get(
    base: str, path: str, headers: dict[str, str], params: dict[str, Any] | None = None
) -> tuple[int, Any]:
    query = "" if params is None else "?" + urllib.parse.urlencode(params)
    return request(base, "GET", path + query, headers=headers)


def unique_entity(
    base: str,
    headers: dict[str, str],
    dataset_id: str,
    query: str,
    *,
    canonical_name: str | None = None,
    entity_type: str | None = None,
) -> dict[str, Any]:
    status, entities = get(
        base, f"/v1/datasets/{dataset_id}/entities/search", headers, {"q": query}
    )
    assert status == 200, entities
    expected_name = (canonical_name or query).casefold()
    matches = [
        item
        for item in entities
        if item["canonical_name"].casefold() == expected_name
        and (entity_type is None or item["entity_type"].casefold() == entity_type.casefold())
    ]
    assert len(matches) == 1, (query, canonical_name, entity_type, entities)
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument(
        "--fixtures", type=Path, default=Path("evaluation/m4_golden/fixture-v1.1.json")
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    wait_ready(base)
    admin = {"X-API-Key": os.environ["ADMIN_API_KEY"]}
    fixtures = json.loads(args.fixtures.read_text(encoding="utf-8"))

    status, project = request(base, "POST", "/v1/projects", {"name": "m4-primary"}, admin)
    assert status == 201, project
    status, outsider = request(base, "POST", "/v1/projects", {"name": "m4-outsider"}, admin)
    assert status == 201, outsider
    headers, outsider_headers = auth(project), auth(outsider)
    status, dataset = request(base, "POST", "/v1/datasets", {"name": "m4-fixture"}, headers)
    assert status == 201, dataset
    status, outsider_dataset = request(
        base, "POST", "/v1/datasets", {"name": "m4-outsider"}, outsider_headers
    )
    assert status == 201, outsider_dataset

    primary_fixtures = [
        item for item in fixtures["documents"] if item.get("tenant", "primary") == "primary"
    ]
    outsider_fixture = next(item for item in fixtures["documents"] if item.get("tenant") == "other")
    documents = [upload(base, headers, dataset["id"], item) for item in primary_fixtures]
    documents.append(
        upload(
            base,
            headers,
            dataset["id"],
            {
                "id": "structured-path-extension",
                "text": "Atlas [Product]\nBeacon [Service]\nAtlas -> DEPENDS_ON -> Beacon",
            },
        )
    )
    outsider_document = upload(
        base, outsider_headers, outsider_dataset["id"], outsider_fixture
    )
    document_ids = [item["id"] for item in documents]
    wait_indexed(base, headers, document_ids)
    wait_indexed(base, outsider_headers, [outsider_document["id"]])
    wait_graph(args.compose_file, document_ids)
    wait_graph(args.compose_file, [outsider_document["id"]])

    alice = unique_entity(
        base, headers, dataset["id"], "Alice Nguyen", entity_type="Person"
    )
    atlas = unique_entity(base, headers, dataset["id"], "Atlas", entity_type="Product")
    acme = unique_entity(
        base, headers, dataset["id"], "Acme Labs", entity_type="Organization"
    )
    beacon = unique_entity(base, headers, dataset["id"], "Beacon", entity_type="Service")
    assert alice["canonical_name"] == "Alice Nguyen" and alice["entity_type"] == "Person", alice
    assert atlas["entity_type"] == "Product", atlas
    assert acme["entity_type"] == "Organization", acme

    status, path = get(
        base,
        f"/v1/datasets/{dataset['id']}/graph/path",
        headers,
        {
            "source_entity_id": alice["id"],
            "target_entity_id": beacon["id"],
            "max_depth": 2,
            "relation_limit": 6,
        },
    )
    assert status == 200 and path["found"] and path["hops"] == 2, path
    assert [item["id"] for item in path["nodes"]] == [
        alice["id"],
        atlas["id"],
        beacon["id"],
    ], path
    assert {item["relation_type"] for item in path["relations"]} == {
        "LEADS",
        "DEPENDS_ON",
    }, path

    evidence_ids: set[str] = set()
    for relation in path["relations"]:
        assert relation["citations"], relation
        status, evidence = get(
            base,
            f"/v1/datasets/{dataset['id']}/relations/{relation['id']}/evidence",
            headers,
        )
        assert status == 200 and evidence, (relation, evidence)
        assert all(
            item["dataset_id"] == dataset["id"]
            and item["relation_id"] == relation["id"]
            and item["quote"]
            for item in evidence
        ), evidence
        evidence_ids.update(item["id"] for item in evidence)

    evidence_id = next(iter(evidence_ids))
    status, evidence = get(base, f"/v1/evidence/{evidence_id}", headers)
    assert status == 200 and evidence["id"] == evidence_id and evidence["quote"], evidence

    status, subgraph = get(
        base,
        f"/v1/datasets/{dataset['id']}/graph/subgraph",
        headers,
        {"entity_id": alice["id"], "depth": 2, "node_limit": 10, "relation_limit": 6},
    )
    assert status == 200 and subgraph["root_entity_id"] == alice["id"], subgraph
    assert {alice["id"], atlas["id"], acme["id"]} <= {
        item["id"] for item in subgraph["nodes"]
    }, subgraph
    assert {"EMPLOYS", "LEADS", "BUILT_BY"} <= {
        item["relation_type"] for item in subgraph["relations"]
    }, subgraph
    assert len(subgraph["nodes"]) <= 10 and len(subgraph["relations"]) <= 6

    outsider_acme = unique_entity(
        base,
        outsider_headers,
        outsider_dataset["id"],
        "Acme Labs",
        entity_type="Organization",
    )
    eve = unique_entity(
        base, outsider_headers, outsider_dataset["id"], "Eve", entity_type="Person"
    )
    assert outsider_acme["id"] != acme["id"]
    status, primary_eve = get(
        base, f"/v1/datasets/{dataset['id']}/entities/search", headers, {"q": "Eve"}
    )
    assert status == 200 and primary_eve == [], primary_eve

    primary_paths = [
        f"/v1/datasets/{dataset['id']}/entities/search?q=Atlas",
        f"/v1/datasets/{dataset['id']}/graph/path?source_entity_id={alice['id']}&target_entity_id={acme['id']}",
        f"/v1/datasets/{dataset['id']}/graph/subgraph?entity_id={alice['id']}",
        f"/v1/datasets/{dataset['id']}/relations/{path['relations'][0]['id']}/evidence",
        f"/v1/entities/{alice['id']}",
        f"/v1/evidence/{evidence_id}",
    ]
    assert all(
        request(base, "GET", item, headers=outsider_headers)[0] == 404
        for item in primary_paths
    )
    assert get(base, f"/v1/entities/{eve['id']}", headers)[0] == 404
    assert get(
        base,
        f"/v1/datasets/{dataset['id']}/graph/subgraph",
        headers,
        {"entity_id": alice["id"], "depth": 3},
    )[0] == 422

    print(
        "structured graph gate passed: entity search, 2-hop path, bounded subgraph, "
        "relation evidence, evidence lookup, and project/dataset isolation"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
