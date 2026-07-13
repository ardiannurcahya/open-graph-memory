from datetime import UTC, datetime
from uuid import uuid4

from app.memory import fact_content, fact_view
from app.models import MemoryFact, MemoryFactStatus
from app.query import build_context
from app.vector_store import VectorHit


def test_fact_content_is_stable_for_search_and_context() -> None:
    assert fact_content("alice", "prefers_language", "Indonesian") == (
        "alice prefers_language: Indonesian"
    )


def test_fact_view_preserves_lifecycle_and_provenance_fields() -> None:
    now = datetime.now(UTC)
    row = MemoryFact(
        id="mem_test",
        project_id=uuid4(),
        user_id="usr_test",
        agent_id=None,
        session_id=None,
        scope="user",
        subject="alice",
        predicate="prefers_language",
        value="Indonesian",
        content="alice prefers_language: Indonesian",
        confidence=98,
        status=MemoryFactStatus.ACTIVE,
        supersedes_id="mem_old",
        source_message_id="msg_test",
        provenance={"source": "message", "source_message_id": "msg_test"},
        metadata_={"source": "fixture"},
        valid_from=now,
        valid_until=None,
        deleted_at=None,
    )
    view = fact_view(row)

    assert view.status == "active"
    assert view.supersedes_id == "mem_old"
    assert view.provenance["source_message_id"] == "msg_test"
    assert view.metadata == {"source": "fixture"}


def test_query_context_includes_memory_without_citation_indexes() -> None:
    fact = MemoryFact(
        id="mem_1",
        project_id=uuid4(),
        user_id="usr_1",
        agent_id=None,
        session_id=None,
        scope="user",
        subject="alice",
        predicate="prefers_language",
        value="Indonesian",
        content="alice prefers_language: Indonesian",
        confidence=100,
        status=MemoryFactStatus.ACTIVE,
        supersedes_id=None,
        source_message_id="msg_1",
        provenance={},
        metadata_={},
        valid_from=datetime.now(UTC),
        valid_until=None,
        deleted_at=None,
    )

    context = build_context(
        [VectorHit("chunk_1", 0.9, {"document_id": "doc_1", "text": "Atlas is built by Acme."})],
        [fact],
    )

    assert "[1] chunk_id=chunk_1 document_id=doc_1" in context
    assert "Memory facts for personalization only" in context
    assert "alice prefers_language: Indonesian" in context
    assert "[2]" not in context
