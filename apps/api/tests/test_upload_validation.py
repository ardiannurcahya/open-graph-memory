from io import BytesIO

from app.documents import spool, validate
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
