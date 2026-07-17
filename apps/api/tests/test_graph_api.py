from types import SimpleNamespace

from app.graph_api import (
    MAX_EXPLORER_NODES,
    MAX_EXPLORER_RELATIONS,
    MAX_PATH_DEPTH,
    MAX_PATH_RELATIONS,
    MAX_SUBGRAPH_DEPTH,
    MAX_SUBGRAPH_RELATIONS,
    low_signal_entity,
    path_ids,
    rank_graph_entities,
    router,
    source_location,
    supported_entity,
    supported_relation,
)
from fastapi import FastAPI
from sqlalchemy.dialects import postgresql


def entity(row_id: str, name: str, entity_type: str) -> SimpleNamespace:
    return SimpleNamespace(id=row_id, canonical_name=name, entity_type=entity_type)


def test_graph_evidence_source_location_keeps_known_integer_fields_only() -> None:
    assert source_location(
        {"page_number": 2, "record_number": 4, "segment_part": 3, "untrusted": "drop"}
    ) == {"page_number": 2, "record_number": 4, "segment_part": 3}
    assert source_location({"page_number": "2"}) is None


def test_low_signal_entity_filters_numeric_dates_and_identifiers() -> None:
    assert low_signal_entity("0.15", "numeric value")
    assert low_signal_entity("20 August 2024", "access_date")
    assert low_signal_entity("10.3390/app14177509", "doi")
    assert not low_signal_entity("Ardian Nurcahya", "Person")


def test_rank_graph_entities_prefers_connected_human_readable_nodes() -> None:
    rows = [
        entity("n", "0.15", "numeric value"),
        entity("p", "Ardian Nurcahya", "Person"),
        entity("s", "Python", "Skill"),
        entity("d", "20 August 2024", "access_date"),
    ]

    ranked = rank_graph_entities(rows, {"n": 100, "p": 20, "s": 10, "d": 50}, 3)  # type: ignore[arg-type]

    assert [item.canonical_name for item in ranked] == ["Ardian Nurcahya", "Python"]


def test_path_ids_reconstructs_ordered_shortest_path() -> None:
    nodes, relations = path_ids(
        "a",
        "c",
        {"b": ("a", "r1"), "c": ("b", "r2")},
    )

    assert nodes == ["a", "b", "c"]
    assert relations == ["r1", "r2"]
    assert path_ids("a", "a", {}) == (["a"], [])
    assert path_ids("a", "missing", {}) == ([], [])


def test_supported_relations_require_evidence_and_exclude_rejected_state() -> None:
    sql = str(
        supported_relation().compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    assert "review_state != 'REJECTED'" in sql
    assert "EXISTS" in sql
    assert "graph_evidence.relation_id = relation_assertions.id" in sql

    entity_sql = str(
        supported_entity().compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "review_state != 'REJECTED'" in entity_sql


def test_agent_graph_routes_publish_hard_bounds_and_structured_responses() -> None:
    app = FastAPI()
    app.include_router(router)
    schema = app.openapi()

    assert schema["paths"]["/v1/datasets/{dataset_id}/entities/search"]["get"]["responses"]["200"]
    path_parameters = {
        item["name"]: item["schema"]
        for item in schema["paths"]["/v1/datasets/{dataset_id}/graph/path"]["get"][
            "parameters"
        ]
    }
    subgraph_parameters = {
        item["name"]: item["schema"]
        for item in schema["paths"]["/v1/datasets/{dataset_id}/graph/subgraph"]["get"][
            "parameters"
        ]
    }
    explorer_parameters = {
        item["name"]: item["schema"]
        for item in schema["paths"]["/v1/datasets/{dataset_id}/graph/explorer"]["get"][
            "parameters"
        ]
    }
    assert path_parameters["max_depth"]["maximum"] == MAX_PATH_DEPTH
    assert path_parameters["relation_limit"]["maximum"] == MAX_PATH_RELATIONS
    assert subgraph_parameters["depth"]["maximum"] == MAX_SUBGRAPH_DEPTH
    assert subgraph_parameters["relation_limit"]["maximum"] == MAX_SUBGRAPH_RELATIONS
    assert explorer_parameters["node_limit"] == {
        "type": "integer",
        "maximum": MAX_EXPLORER_NODES,
        "minimum": 1,
        "default": MAX_EXPLORER_NODES,
        "title": "Node Limit",
    }
    assert explorer_parameters["relation_limit"] == {
        "type": "integer",
        "maximum": MAX_EXPLORER_RELATIONS,
        "minimum": 1,
        "default": MAX_EXPLORER_RELATIONS,
        "title": "Relation Limit",
    }
    node_page_parameters = {
        item["name"]: item["schema"]
        for item in schema["paths"][
            "/v1/datasets/{dataset_id}/graph/explorer/nodes"
        ]["get"]["parameters"]
    }
    relation_page_parameters = {
        item["name"]: item["schema"]
        for item in schema["paths"][
            "/v1/datasets/{dataset_id}/graph/explorer/relations"
        ]["get"]["parameters"]
    }
    assert node_page_parameters["limit"]["maximum"] == MAX_EXPLORER_NODES
    assert relation_page_parameters["limit"]["maximum"] == MAX_EXPLORER_RELATIONS
    assert node_page_parameters["cursor"]["anyOf"][0]["type"] == "string"
    assert relation_page_parameters["cursor"]["anyOf"][0]["type"] == "string"
    assert schema["paths"][
        "/v1/datasets/{dataset_id}/relations/{relation_id}/evidence"
    ]["get"]["responses"]["200"]
    assert not any("community-report" in path for path in schema["paths"])
