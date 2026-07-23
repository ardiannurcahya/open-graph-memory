from io import BytesIO

import pytest
from app.chunking import RecursiveTextChunker
from app.ingestion import PIPELINE_VERSION, deterministic_id, sanitized_error
from app.parsers import LiteParsePdfParser, ParsedDocument, ParsedSegment, default_registry
from pypdf import PdfWriter


def test_artifact_ids_are_deterministic_and_versioned() -> None:
    first = deterministic_id("chunk", "doc_1", "hash", PIPELINE_VERSION, 0)
    assert first == deterministic_id("chunk", "doc_1", "hash", PIPELINE_VERSION, 0)
    assert first != deterministic_id("chunk", "doc_1", "hash", PIPELINE_VERSION, 1)


def test_parser_chunker_orchestration_inputs() -> None:
    parsed = default_registry().parse("text/markdown", b"# Heading\n\nBody")
    chunks = RecursiveTextChunker(size=20, overlap=2).split_document("doc_1", parsed)
    assert chunks
    assert chunks[0].text == "Body"
    assert chunks[0].metadata["section_path"] == ["Heading"]


def test_default_chunker_accepts_large_tabular_text() -> None:
    text = "\n".join(f"name: project-{index}; value: {'x' * 900}" for index in range(650))

    chunks = RecursiveTextChunker().split("doc_1", text)

    assert len(chunks) > 500
    assert chunks[-1].text


def test_text_parser_accepts_utf8_sig_text() -> None:
    parsed = default_registry().parse("text/plain", b"\xef\xbb\xbfHello\r\nworld", "notes.txt")

    assert parsed.text == "Hello\nworld"


def test_json_parser_normalizes_structured_document() -> None:
    parsed = default_registry().parse(
        "application/json",
        b'{"items":[{"name":"beta"}],"enabled":true}',
        "record.json",
    )

    assert parsed.text == (
        '{\n  "enabled": true,\n  "items": [\n    {\n      "name": "beta"\n    }\n  ]\n}'
    )
    assert parsed.metadata == {"root_type": "object", "json_path": "$"}


def test_json_array_chunks_preserve_record_paths_and_unicode() -> None:
    parsed = default_registry().parse(
        "application/json",
        '[{"id":"a","name":"München"},{"id":"b","body":"'.encode()
        + b"x" * 100
        + b'"}]',
        "records.json",
    )
    chunks = RecursiveTextChunker(size=40, overlap=5).split_document("doc", parsed)

    assert parsed.metadata == {"root_type": "array", "records": 2}
    assert parsed.segments[0].metadata == {"record_number": 1, "json_path": "$[0]"}
    assert "München" in parsed.segments[0].text
    assert {chunk.metadata["json_path"] for chunk in chunks} == {"$[0]", "$[1]"}
    long_record = [chunk for chunk in chunks if chunk.metadata["json_path"] == "$[1]"]
    assert len(long_record) > 1
    assert {chunk.metadata["record_number"] for chunk in long_record} == {2}


def test_empty_json_array_is_valid_source_document() -> None:
    parsed = default_registry().parse("application/json", b"[]", "empty.json")

    assert parsed.text == ""
    assert parsed.segments == ()
    assert parsed.metadata == {"root_type": "array", "records": 0}


def test_plain_text_json_filename_uses_json_parser() -> None:
    parsed = default_registry().parse("text/plain", b'{"name":"alpha"}', "record.json")

    assert parsed.text == '{\n  "name": "alpha"\n}'


@pytest.mark.parametrize("content", [b'{"name":}', b'{"value": NaN}'])
def test_json_parser_rejects_invalid_json(content: bytes) -> None:
    with pytest.raises(ValueError, match="invalid JSON"):
        default_registry().parse("application/json", content, "broken.json")


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
    document = ParsedDocument(
        "first\n\nthird",
        segments=(
            ParsedSegment("first " * 20, {"page_number": 1}),
            ParsedSegment("third " * 20, {"page_number": 3}),
        ),
    )
    chunks = RecursiveTextChunker(size=30, overlap=5).split_document("doc", document)

    assert [chunk.metadata["page_number"] for chunk in chunks] == [1, 3]
    assert [chunk.text for chunk in chunks] == [("first " * 20).strip(), ("third " * 20).strip()]
    assert all(chunk.metadata["segment_count"] == 1 for chunk in chunks)
    assert all(chunk.metadata["segment_part"] == 1 for chunk in chunks)


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


def test_markdown_sections_do_not_mix_and_keep_heading_context_out_of_body() -> None:
    parsed = default_registry().parse(
        "text/markdown", b"# First\n\nAlpha body.\n\n# Second\n\nBeta body."
    )
    chunks = RecursiveTextChunker(size=100, overlap=1).split_document("doc", parsed)

    assert [chunk.text for chunk in chunks] == ["Alpha body.", "Beta body."]
    assert [chunk.metadata["section_path"] for chunk in chunks] == [["First"], ["Second"]]


def test_chunk_offsets_exactly_select_persisted_text() -> None:
    segment = ParsedSegment("  alpha beta gamma  ", {"section_title": "Test"})
    chunks = RecursiveTextChunker(size=12, overlap=2).split_document(
        "doc", ParsedDocument(segment.text, segments=(segment,))
    )

    for chunk in chunks:
        start = chunk.metadata["segment_start_char"]
        end = chunk.metadata["segment_end_char"]
        assert segment.text[start:end] == chunk.text


def test_plain_text_csv_filename_uses_csv_parser() -> None:
    parsed = default_registry().parse("text/plain", b"name,value\nalpha,1\n", "rows.csv")

    assert parsed.metadata == {"rows": 1, "columns": ["name", "value"]}
    assert parsed.text == "name: alpha; value: 1"


def test_pipeline_version_has_no_embedding_projection() -> None:
    assert "embedding" not in PIPELINE_VERSION


def test_pdf_parser_accepts_a_real_large_pdf() -> None:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/Subject": "x" * 9000})
    writer.write(output)
    content = output.getvalue()

    assert len(content) > 8192
    parsed = default_registry().parse("application/pdf", content, "manual.pdf")
    assert parsed.metadata == {
        "parser": "pypdf",
        "parser_version": "pypdf",
        "pages": 1,
        "non_empty_pages": 0,
    }


class _Complexity:
    def __init__(self, page_number: int, needs_ocr: bool) -> None:
        self.page_number = page_number
        self.needs_ocr = needs_ocr


class _TextItem:
    text = "Digital text"
    x = 10.0
    y = 20.0
    width = 30.0
    height = 12.0
    font_name = "Helvetica"
    font_size = 10.0
    rotation = 0.0


class _Page:
    page_num = 1
    text = "Ada Lovelace developed GraphMem using Neo4j."
    text_items = [_TextItem(), _TextItem()]


class _Result:
    text = "Digital text"
    pages = [_Page()]
    num_pages = 1


class _FakeLiteParse:
    instances: list["_FakeLiteParse"] = []
    complex = False

    def __init__(self, **options: object) -> None:
        self.options = options
        self.instances.append(self)

    def is_complex(self, content: bytes) -> list[_Complexity]:
        assert content == b"pdf"
        return [_Complexity(1, self.complex)]

    def parse(self, content: bytes) -> _Result:
        assert content == b"pdf"
        return _Result()


def test_liteparse_digital_pdf_avoids_ocr_and_coalesces_page_text() -> None:
    _FakeLiteParse.instances.clear()
    _FakeLiteParse.complex = False
    parser = LiteParsePdfParser(parser_factory=_FakeLiteParse)  # type: ignore[arg-type]

    parsed = parser.parse(b"pdf")

    assert len(_FakeLiteParse.instances) == 1
    assert _FakeLiteParse.instances[0].options["ocr_enabled"] is False
    assert parsed.metadata["ocr_requested"] is False
    assert parsed.segments == (
        ParsedSegment("Ada Lovelace developed GraphMem using Neo4j.", {"page_number": 1}),
    )


def test_liteparse_page_segment_keeps_explicit_relation_in_one_chunk() -> None:
    parsed = LiteParsePdfParser(parser_factory=_FakeLiteParse).parse(b"pdf")  # type: ignore[arg-type]

    chunks = RecursiveTextChunker(size=100, overlap=1).split_document("doc", parsed)

    assert [chunk.text for chunk in chunks] == ["Ada Lovelace developed GraphMem using Neo4j."]
    assert [chunk.metadata["page_number"] for chunk in chunks] == [1]


def test_liteparse_uses_page_reading_order_not_layout_item_order() -> None:
    class Item:
        def __init__(self, text: str) -> None:
            self.text = text

    class Page:
        page_num = 1
        text = "Ada Lovelace developed GraphMem using Neo4j."
        text_items = [Item("Neo4j."), Item("Ada Lovelace developed"), Item("GraphMem using")]

    class Result:
        text = Page.text
        pages = [Page()]
        num_pages = 1

    class Parser(_FakeLiteParse):
        def parse(self, content: bytes) -> Result:
            assert content == b"pdf"
            return Result()

    parsed = LiteParsePdfParser(parser_factory=Parser).parse(b"pdf")  # type: ignore[arg-type]

    assert parsed.segments[0].text == "Ada Lovelace developed GraphMem using Neo4j."


def test_liteparse_complex_pdf_routes_to_single_worker_ocr() -> None:
    _FakeLiteParse.instances.clear()
    _FakeLiteParse.complex = True
    parser = LiteParsePdfParser(parser_factory=_FakeLiteParse)  # type: ignore[arg-type]

    parsed = parser.parse(b"pdf")

    assert [item.options["ocr_enabled"] for item in _FakeLiteParse.instances] == [False, True]
    assert _FakeLiteParse.instances[1].options["num_workers"] == 1
    assert _FakeLiteParse.instances[1].options["dpi"] == 150
    assert _FakeLiteParse.instances[1].options["max_pages"] == 300
    assert parsed.metadata["complex_pages"] == [1]


def test_liteparse_disabled_ocr_does_not_probe_or_fallback() -> None:
    class FailingLiteParse(_FakeLiteParse):
        def is_complex(self, content: bytes) -> list[_Complexity]:
            raise AssertionError("disabled mode must not probe complexity")

        def parse(self, content: bytes) -> _Result:
            raise RuntimeError("parse failed")

    with pytest.raises(RuntimeError, match="parse failed"):
        LiteParsePdfParser(
            ocr_mode="disabled", parser_factory=FailingLiteParse  # type: ignore[arg-type]
        ).parse(b"pdf")


def test_errors_are_bounded_and_secrets_redacted() -> None:
    result = sanitized_error(ValueError("token=super-secret\n failed" + "x" * 2000))
    assert "super-secret" not in result
    assert "token=[redacted]" in result
    assert len(result) <= 1000
