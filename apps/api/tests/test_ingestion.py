from io import BytesIO

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


def test_csv_parser_repairs_malformed_unclosed_quote() -> None:
    parsed = default_registry().parse(
        "text/csv", b'name,description\nalpha,"broken\nbeta,second\n', "malformed.csv"
    )

    assert parsed.metadata == {"rows": 2, "columns": ["name", "description"], "repaired": True}
    assert "name: alpha; description: broken" in parsed.text
    assert "name: beta; description: second" in parsed.text


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
    assert parsed.metadata == {"pages": 1}


def test_errors_are_bounded_and_secrets_redacted() -> None:
    result = sanitized_error(ValueError("token=super-secret\n failed" + "x" * 2000))
    assert "super-secret" not in result
    assert "token=[redacted]" in result
    assert len(result) <= 1000
