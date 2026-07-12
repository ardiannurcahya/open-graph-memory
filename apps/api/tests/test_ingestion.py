from app.chunking import RecursiveTextChunker
from app.ingestion import PIPELINE_VERSION, deterministic_id, sanitized_error
from app.parsers import default_registry


def test_artifact_ids_are_deterministic_and_versioned() -> None:
    first = deterministic_id("chunk", "doc_1", "hash", PIPELINE_VERSION, 0)
    assert first == deterministic_id("chunk", "doc_1", "hash", PIPELINE_VERSION, 0)
    assert first != deterministic_id("chunk", "doc_1", "hash", PIPELINE_VERSION, 1)


def test_parser_chunker_orchestration_inputs() -> None:
    parsed = default_registry().parse("text/markdown", b"# Heading\n\nBody")
    chunks = RecursiveTextChunker(size=20, overlap=2).split("doc_1", parsed.text)
    assert chunks
    assert "Heading" in chunks[0].text


def test_errors_are_bounded_and_secrets_redacted() -> None:
    result = sanitized_error(ValueError("token=super-secret\n failed" + "x" * 2000))
    assert "super-secret" not in result
    assert "token=[redacted]" in result
    assert len(result) <= 1000
