from app.query import build_context
from app.vector_store import VectorHit


def test_build_context_keeps_evidence_blocks_and_citation_indexes_aligned() -> None:
    context = build_context(
        [
            VectorHit(
                "people", 0.9, {"document_id": "people-doc", "text": "Acme -> EMPLOYS -> Alice"}
            ),
            VectorHit(
                "product", 0.8, {"document_id": "product-doc", "text": "Atlas -> BUILT_BY -> Acme"}
            ),
        ]
    )
    assert "[1] chunk_id=people document_id=people-doc" in context
    assert "[2] chunk_id=product document_id=product-doc" in context
    assert context.index("[1]") < context.index("[2]")
