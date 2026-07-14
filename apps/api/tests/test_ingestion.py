from io import BytesIO

import pytest
from app.chunking import RecursiveTextChunker
from app.ingestion import PIPELINE_VERSION, deterministic_id, embed_in_batches, sanitized_error
from app.parsers import default_registry
from pypdf import PdfWriter


def test_artifact_ids_are_deterministic_and_versioned() -> None:
    first = deterministic_id("chunk", "doc_1", "hash", PIPELINE_VERSION, 0)
    assert first == deterministic_id("chunk", "doc_1", "hash", PIPELINE_VERSION, 0)
    assert first != deterministic_id("chunk", "doc_1", "hash", PIPELINE_VERSION, 1)


def test_parser_chunker_orchestration_inputs() -> None:
    parsed = default_registry().parse("text/markdown", b"# Heading\n\nBody")
    chunks = RecursiveTextChunker(size=20, overlap=2).split("doc_1", parsed.text)
    assert chunks
    assert "Heading" in chunks[0].text


def test_default_chunker_accepts_large_tabular_text() -> None:
    text = "\n".join(f"name: project-{index}; value: {'x' * 900}" for index in range(650))

    chunks = RecursiveTextChunker().split("doc_1", text)

    assert len(chunks) > 500
    assert chunks[-1].text


def test_text_parser_accepts_utf8_sig_text() -> None:
    parsed = default_registry().parse("text/plain", b"\xef\xbb\xbfHello\r\nworld", "notes.txt")

    assert parsed.text == "Hello\nworld"


def test_csv_parser_accepts_large_field() -> None:
    large_value = "x" * (140 * 1024)
    content = f"name,description\nproject,{large_value}\n".encode()

    parsed = default_registry().parse("text/csv", content, "documents.csv")

    assert parsed.metadata["rows"] == 1
    assert parsed.metadata["columns"] == ["name", "description"]
    assert f"description: {large_value}" in parsed.text


def test_csv_parser_accepts_quoted_newline_field() -> None:
    parsed = default_registry().parse(
        "text/csv",
        b'name,description\r\nalpha,"line one\r\nline two"\r\n',
        "quoted.csv",
    )

    assert parsed.metadata == {"rows": 1, "columns": ["name", "description"]}
    assert "name: alpha; description: line one\r\nline two" in parsed.text


def test_csv_parser_accepts_semicolon_delimiter() -> None:
    parsed = default_registry().parse(
        "text/csv", b"name;description\nalpha;first\nbeta;second\n", "semicolon.csv"
    )

    assert parsed.metadata == {"rows": 2, "columns": ["name", "description"]}
    assert "name: alpha; description: first" in parsed.text
    assert "name: beta; description: second" in parsed.text


def test_csv_parser_rejects_malformed_unmatched_quote() -> None:
    with pytest.raises(ValueError, match="malformed CSV: unmatched quote"):
        default_registry().parse(
            "text/csv", b'name,description\nalpha,"broken\nbeta,second\n', "malformed.csv"
        )


def test_source_aware_chunks_keep_pdf_pages_and_blank_page_numbers() -> None:
    from app.parsers import ParsedDocument, ParsedSegment

    document = ParsedDocument(
        "first\n\nthird",
        segments=(
            ParsedSegment("first " * 20, {"page_number": 1}),
            ParsedSegment("third " * 20, {"page_number": 3}),
        ),
    )
    chunks = RecursiveTextChunker(size=30, overlap=5).split_document("doc", document)

    assert {chunk.metadata["page_number"] for chunk in chunks} == {1, 3}
    assert all("first" in chunk.text or "third" in chunk.text for chunk in chunks)
    assert all(chunk.metadata["segment_count"] > 1 for chunk in chunks)
    first_page_parts = {
        chunk.metadata["segment_part"] for chunk in chunks if chunk.metadata["page_number"] == 1
    }
    assert first_page_parts == {
        1,
        2,
        3,
        4,
        5,
    }


def test_csv_chunks_never_merge_records_and_long_record_keeps_location() -> None:
    parsed = default_registry().parse(
        "text/csv", b"name,value\na,1\nb,2\nc," + b"x" * 100 + b"\n", "rows.csv"
    )
    chunks = RecursiveTextChunker(size=30, overlap=5).split_document("doc", parsed)

    assert [chunk.metadata["record_number"] for chunk in chunks[:2]] == [1, 2]
    long_record = [chunk for chunk in chunks if chunk.metadata["record_number"] == 3]
    assert len(long_record) > 1
    assert {chunk.metadata["segment_part"] for chunk in long_record} == set(
        range(1, len(long_record) + 1)
    )


def test_csv_quoted_multiline_field_is_one_logical_record_and_limit_restores() -> None:
    import csv

    previous = csv.field_size_limit()
    parsed = default_registry().parse(
        "text/csv", b'name,description\na,"line one\nline two"\nb,plain\n', "rows.csv"
    )

    assert csv.field_size_limit() == previous
    assert len(parsed.segments) == 2
    assert parsed.segments[0].metadata["record_number"] == 1
    assert "line one\nline two" in parsed.segments[0].text


@pytest.mark.parametrize(
    ("mime", "content"),
    [
        ("text/plain", b"plain text"),
        ("text/markdown", b"# Heading\n\nBody"),
        ("text/html", b"<h1>Title</h1><p>Body</p>"),
    ],
)
def test_generic_formats_remain_single_generic_segment(mime: str, content: bytes) -> None:
    parsed = default_registry().parse(mime, content)

    chunks = RecursiveTextChunker(size=100, overlap=1).split_document("doc", parsed)
    assert len(chunks) == 1
    assert chunks[0].metadata["segment_part"] == 1
    assert chunks[0].metadata["segment_count"] == 1


def test_plain_text_csv_filename_uses_csv_parser() -> None:
    parsed = default_registry().parse("text/plain", b"name,value\nalpha,1\n", "rows.csv")

    assert parsed.metadata == {"rows": 1, "columns": ["name", "value"]}
    assert parsed.text == "name: alpha; value: 1"


class RecordingEmbeddings:
    name = "recording"
    dimensions = 1

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        self.calls.append(texts)
        return [[float(len(text))] for text in texts]


async def test_embed_in_batches_preserves_order() -> None:
    embeddings = RecordingEmbeddings()

    vectors = await embed_in_batches(embeddings, ["a", "bb", "ccc", "dddd", "eeeee"], "model", 2)

    assert embeddings.calls == [["a", "bb"], ["ccc", "dddd"], ["eeeee"]]
    assert vectors == [[1.0], [2.0], [3.0], [4.0], [5.0]]


def test_pdf_parser_accepts_a_real_large_pdf() -> None:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/Subject": "x" * 9000})
    writer.write(output)
    content = output.getvalue()

    assert len(content) > 8192
    parsed = default_registry().parse("application/pdf", content, "manual.pdf")
    assert parsed.metadata == {"pages": 1, "non_empty_pages": 0}


def test_errors_are_bounded_and_secrets_redacted() -> None:
    result = sanitized_error(ValueError("token=super-secret\n failed" + "x" * 2000))
    assert "super-secret" not in result
    assert "token=[redacted]" in result
    assert len(result) <= 1000
