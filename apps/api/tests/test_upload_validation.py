from io import BytesIO
from uuid import uuid4

from app.documents import serialize, spool, validate
from app.models import Document, DocumentStatus
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers


def upload(name: str, content_type: str, data: bytes) -> UploadFile:
    return UploadFile(
        filename=name, file=BytesIO(data), headers=Headers({"content-type": content_type})
    )


def test_pdf_requires_signature() -> None:
    file = upload("report.pdf", "application/pdf", b"not a pdf")
    try:
        validate(file, b"not a pdf", b"not a pdf")
    except HTTPException as exc:
        assert exc.status_code == 415
    else:
        raise AssertionError("invalid PDF accepted")


def test_pdf_accepts_eof_signature_at_end_of_large_file() -> None:
    head = b"%PDF-1.7\n" + b"0" * 8183
    tail = b"1" * 8186 + b"%%EOF\n"
    file = upload("report.pdf", "application/pdf", head + tail)

    assert validate(file, head, tail) == "report.pdf"


def test_txt_upload_is_accepted() -> None:
    file = upload("notes.txt", "text/plain", b"plain notes")

    assert validate(file, b"plain notes", b"plain notes") == "notes.txt"


def test_csv_upload_is_accepted() -> None:
    file = upload("rows.csv", "text/csv", b"name,value\nalpha,1\n")

    data = b"name,value\nalpha,1\n"

    assert validate(file, data, data) == "rows.csv"


def test_html_upload_is_accepted() -> None:
    data = b"<!doctype html><html><body>hello</body></html>"
    file = upload("page.html", "text/html", data)

    assert validate(file, data, data) == "page.html"


def test_path_traversal_is_rejected() -> None:
    file = upload("../secret.txt", "text/plain", b"safe")
    try:
        validate(file, b"safe", b"safe")
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("traversal filename accepted")


async def test_spool_hashes_stream() -> None:
    stream, size, digest, head, tail = await spool(upload("a.txt", "text/plain", b"hello"))
    try:
        assert size == 5
        assert digest == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        assert head == b"hello"
        assert tail == b"hello"
        assert stream.read() == b"hello"
    finally:
        stream.close()


def test_serialize_hides_indexed_until_graph_complete() -> None:
    document = Document(
        id="doc_1",
        project_id=uuid4(),
        dataset_id="ds_1",
        filename="a.txt",
        mime_type="text/plain",
        size_bytes=1,
        content_hash="hash",
        object_key="key",
        status=DocumentStatus.INDEXED,
        graph_stage="extracting",
        metadata_={},
    )

    assert serialize(document)["status"] == "persisting"

    document.graph_stage = "complete"
    assert serialize(document)["status"] == "indexed"
