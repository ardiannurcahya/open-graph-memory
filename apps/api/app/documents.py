import hashlib
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from open_graph_core.ids import new_id
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ProjectContext, require_project
from app.datasets import owned
from app.dependencies import get_session
from app.models import Document, DocumentStatus
from app.storage import ObjectStore, get_object_store

router = APIRouter(tags=["documents"])
MAX_SIZE = 25 * 1024 * 1024
MIMES = {
    ".txt": ("text/plain",),
    ".md": ("text/markdown", "text/plain"),
    ".html": ("text/html",),
    ".pdf": ("application/pdf",),
}


async def spool(file: UploadFile) -> tuple[tempfile.SpooledTemporaryFile[bytes], int, str, bytes]:
    output = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    digest, size, signature = hashlib.sha256(), 0, b""
    while chunk := await file.read(64 * 1024):
        size += len(chunk)
        if size > MAX_SIZE:
            output.close()
            raise HTTPException(413, "file exceeds 25 MiB limit")
        if not signature:
            signature = chunk[:16]
        digest.update(chunk)
        output.write(chunk)
    output.seek(0)
    return output, size, digest.hexdigest(), signature


def validate(file: UploadFile, signature: bytes) -> str:
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    if not filename or filename != file.filename or extension not in MIMES:
        raise HTTPException(400, "invalid filename or extension")
    mime = (file.content_type or "").lower()
    if mime not in MIMES[extension]:
        raise HTTPException(415, "MIME type does not match extension")
    if extension == ".pdf" and not signature.startswith(b"%PDF-"):
        raise HTTPException(415, "invalid PDF signature")
    if extension != ".pdf" and b"\x00" in signature:
        raise HTTPException(415, "text upload contains binary data")
    return filename


@router.post("/v1/datasets/{dataset_id}/documents", status_code=201)
async def upload(
    dataset_id: str,
    file: Annotated[UploadFile, File()],
    project: Annotated[ProjectContext, Depends(require_project)],
    db: Annotated[AsyncSession, Depends(get_session)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
) -> dict[str, object]:
    await owned(db, project, dataset_id)
    stream, size, digest, signature = await spool(file)
    try:
        filename = validate(file, signature)
        existing = await db.scalar(
            select(Document).where(
                Document.project_id == project.project_id,
                Document.dataset_id == dataset_id,
                Document.content_hash == digest,
            )
        )
        if existing:
            return serialize(existing, duplicate=True)
        document_id = new_id("doc")
        key = f"projects/{project.project_id}/datasets/{dataset_id}/documents/{document_id}/raw"
        item = Document(
            id=document_id,
            project_id=project.project_id,
            dataset_id=dataset_id,
            filename=filename,
            mime_type=file.content_type,
            size_bytes=size,
            content_hash=digest,
            object_key=key,
            status=DocumentStatus.UPLOADED,
            metadata_={},
        )
        store.upload(key, stream, file.content_type or "application/octet-stream")
        db.add(item)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            store.delete(key)
            winner = await db.scalar(
                select(Document).where(
                    Document.dataset_id == dataset_id, Document.content_hash == digest
                )
            )
            if winner is None:
                raise
            return serialize(winner, duplicate=True)
        return serialize(item, duplicate=False)
    finally:
        stream.close()


def serialize(item: Document, duplicate: bool = False) -> dict[str, object]:
    return {
        "id": item.id,
        "dataset_id": item.dataset_id,
        "filename": item.filename,
        "mime_type": item.mime_type,
        "size_bytes": item.size_bytes,
        "content_hash": item.content_hash,
        "status": item.status.value,
        "duplicate": duplicate,
    }


@router.get("/v1/datasets/{dataset_id}/documents")
async def list_documents(
    dataset_id: str,
    project: Annotated[ProjectContext, Depends(require_project)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict[str, object]]:
    await owned(db, project, dataset_id)
    rows = await db.scalars(
        select(Document).where(
            Document.project_id == project.project_id, Document.dataset_id == dataset_id
        )
    )
    return [serialize(row) for row in rows]


@router.get("/v1/datasets/{dataset_id}/documents/{document_id}")
async def get_document(
    dataset_id: str,
    document_id: str,
    project: Annotated[ProjectContext, Depends(require_project)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    item = await db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.project_id == project.project_id,
            Document.dataset_id == dataset_id,
        )
    )
    if item is None:
        raise HTTPException(404, "document not found")
    return serialize(item)
