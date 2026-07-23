from uuid import uuid4

import pytest
from app.graph_consolidation import (
    ConsolidationOutput,
    ConsolidationRelation,
    build_input,
    validate_output,
)
from app.models import Chunk


def chunks() -> list[Chunk]:
    project_id = uuid4()
    return [
        Chunk(
            id="first",
            project_id=project_id,
            dataset_id="dataset",
            document_id="document",
            chunk_index=0,
            text="Acme introduces Project Nova.",
            metadata_={"section_path": ["Overview"], "page_number": 1},
        ),
        Chunk(
            id="second",
            project_id=project_id,
            dataset_id="dataset",
            document_id="document",
            chunk_index=1,
            text="Project Nova uses PostgreSQL.",
            metadata_={"section_path": ["Architecture"], "page_number": 2},
        ),
    ]


def test_snapshot_identity_is_stable_and_uses_raw_extraction() -> None:
    values = {
        "first": {"entities": [{"name": "Acme"}], "relations": []},
        "second": {"entities": [{"name": "Project Nova"}], "relations": []},
    }

    first = build_input(chunks(), values)
    second = build_input(list(reversed(chunks())), values)
    changed = build_input(chunks(), {**values, "second": {"entities": [], "relations": []}})

    assert first.snapshot_hash == second.snapshot_hash
    assert first.snapshot_hash != changed.snapshot_hash
    assert [item["chunk_id"] for item in first.payload] == ["first", "second"]


def test_cross_chunk_relation_evidence_is_valid() -> None:
    source = chunks()
    output = ConsolidationOutput(
        relations=[
            ConsolidationRelation(
                source="Project Nova",
                source_type="Project",
                target="PostgreSQL",
                target_type="Technology",
                type="USES",
                evidence_chunk_id="second",
                quote="Project Nova uses PostgreSQL.",
                confidence=1,
            )
        ]
    )

    validate_output(output, {chunk.id: chunk for chunk in source})


def test_empty_consolidation_output_is_valid_and_additive() -> None:
    validate_output(ConsolidationOutput(), {chunk.id: chunk for chunk in chunks()})


@pytest.mark.parametrize(
    ("chunk_id", "quote", "message"),
    [
        ("missing", "Project Nova uses PostgreSQL.", "unknown chunk"),
        ("second", "fabricated proof", "exact chunk substring"),
    ],
)
def test_invalid_consolidation_evidence_is_rejected(
    chunk_id: str, quote: str, message: str
) -> None:
    output = ConsolidationOutput(
        relations=[
            ConsolidationRelation(
                source="Project Nova",
                source_type="Project",
                target="PostgreSQL",
                target_type="Technology",
                type="USES",
                evidence_chunk_id=chunk_id,
                quote=quote,
                confidence=1,
            )
        ]
    )

    with pytest.raises(ValueError, match=message):
        validate_output(output, {chunk.id: chunk for chunk in chunks()})


def test_relation_quote_must_support_both_endpoints() -> None:
    output = ConsolidationOutput(
        relations=[
            ConsolidationRelation(
                source="Acme",
                source_type="Organization",
                target="Widget",
                target_type="Product",
                type="OWNS",
                evidence_chunk_id="second",
                quote="Project Nova uses PostgreSQL.",
                confidence=1,
            )
        ]
    )

    with pytest.raises(ValueError, match="mention both endpoints"):
        validate_output(output, {chunk.id: chunk for chunk in chunks()})


def test_consolidation_accepts_pdf_normalized_evidence() -> None:
    source = chunks()
    source[1].text = "Project Nova uses Postgre-\nSQL."
    output = ConsolidationOutput(
        relations=[
            ConsolidationRelation(
                source="Project Nova",
                source_type="Project",
                target="PostgreSQL",
                target_type="Technology",
                type="USES",
                evidence_chunk_id="second",
                quote="Project Nova uses PostgreSQL.",
                confidence=1,
            )
        ]
    )

    validate_output(output, {chunk.id: chunk for chunk in source})
