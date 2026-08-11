from pathlib import Path

from app.graph_helpers import supported_entity, supported_relation
from app.graph_store import current_evidence_subject
from sqlalchemy.dialects import postgresql


def test_current_evidence_subject_requires_scoped_current_subject() -> None:
    sql = str(
        current_evidence_subject("project", "dataset").compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    assert "canonical_entities.project_id = 'project'" in sql
    assert "canonical_entities.dataset_id = 'dataset'" in sql
    assert "canonical_entities.valid_until IS NULL" in sql
    assert "canonical_entities.superseded_by IS NULL" in sql
    assert "relation_assertions.project_id = 'project'" in sql
    assert "relation_assertions.dataset_id = 'dataset'" in sql
    assert "relation_assertions.valid_until IS NULL" in sql
    assert "relation_assertions.superseded_by IS NULL" in sql


def test_multi_frontier_traversal_uses_the_matched_endpoint_as_path_parent() -> None:
    source = Path("apps/api/app/graph_store.py").read_text(encoding="utf-8")

    assert "paths[entity_id] = paths[matched_id]" in source
    assert "next(iter(frontier))" not in source


def test_supported_traversal_subjects_match_graph_review_rules() -> None:
    relation_sql = str(
        supported_relation().compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    entity_sql = str(
        supported_entity().compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    assert "review_state != 'REJECTED'" in relation_sql
    assert "graph_evidence.relation_id = relation_assertions.id" in relation_sql
    assert "graph_evidence.entity_id = canonical_entities.id" in entity_sql
    assert "graph_evidence.relation_id = relation_assertions.id" in entity_sql


def test_traversal_filters_seed_relations_and_frontier_endpoints() -> None:
    source = Path("apps/api/app/graph_store.py").read_text(encoding="utf-8")

    assert source.count("supported_relation(),") == 2
    assert "seed_entity_ids = await supported_entity_ids(" in source
    assert "supported_endpoints = await supported_entity_ids(" in source
    assert "if entity_id not in supported_endpoints:" in source
    assert source.index("if entity_id not in supported_endpoints:") < source.index(
        "relation_ids.add(relation.id)"
    )
