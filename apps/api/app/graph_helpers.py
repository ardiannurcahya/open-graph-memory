"""Shared graph query filters to eliminate duplication."""

from sqlalchemy import exists, or_
from sqlalchemy.sql.elements import ColumnElement

from app.graph_models import (
    CanonicalEntity,
    GraphEvidence,
    RelationAssertion,
    ReviewState,
)


def supported_relation() -> ColumnElement[bool]:
    """Relation needs authoritative citation and must not be rejected."""
    return (RelationAssertion.review_state != ReviewState.REJECTED) & exists().where(
        GraphEvidence.relation_id == RelationAssertion.id
    )


def supported_entity() -> ColumnElement[bool]:
    """Entity needs direct evidence or endpoint of cited relation."""
    cited_endpoint = exists().where(
        GraphEvidence.relation_id == RelationAssertion.id,
        RelationAssertion.review_state != ReviewState.REJECTED,
        or_(
            RelationAssertion.source_entity_id == CanonicalEntity.id,
            RelationAssertion.target_entity_id == CanonicalEntity.id,
        ),
    )
    return or_(
        exists().where(GraphEvidence.entity_id == CanonicalEntity.id),
        cited_endpoint,
    )


def normalize_dataset_id(dataset_id: str) -> str:
    """Ensure dataset_id has the ds_ prefix."""
    if not dataset_id.startswith("ds_"):
        return f"ds_{dataset_id}"
    return dataset_id
