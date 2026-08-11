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
    """Relation needs authoritative citation or approved review state."""
    has_evidence = exists().where(GraphEvidence.relation_id == RelationAssertion.id)
    return (RelationAssertion.review_state != ReviewState.REJECTED) & (
        (RelationAssertion.review_state == ReviewState.APPROVED) | has_evidence
    )


def supported_entity() -> ColumnElement[bool]:
    """Entity needs direct evidence, cited relation endpoint, or approved review state."""
    has_evidence = or_(
        exists().where(GraphEvidence.entity_id == CanonicalEntity.id),
        exists().where(
            GraphEvidence.relation_id == RelationAssertion.id,
            RelationAssertion.review_state != ReviewState.REJECTED,
            or_(
                RelationAssertion.source_entity_id == CanonicalEntity.id,
                RelationAssertion.target_entity_id == CanonicalEntity.id,
            ),
        ),
    )
    return (CanonicalEntity.review_state != ReviewState.REJECTED) & (
        (CanonicalEntity.review_state == ReviewState.APPROVED) | has_evidence
    )


def normalize_dataset_id(dataset_id: str) -> str:
    """Ensure dataset_id has the ds_ prefix."""
    if not dataset_id.startswith("ds_"):
        return f"ds_{dataset_id}"
    return dataset_id
