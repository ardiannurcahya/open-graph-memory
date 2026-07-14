import hashlib
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from open_graph_core.ids import new_id
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ProjectContext, require_project
from app.config import get_settings
from app.datasets import owned
from app.dependencies import get_session
from app.graph_cleanup import create_document_cleanup, mark_cleanup_ready
from app.graph_gc import cleanup_document_graph
from app.ingestion import enqueue_document
from app.models import Document, DocumentStatus
from app.storage import ObjectStore, get_object_store

router = APIRouter(tags=["documents"])
MIMES = {
    ".txt": ("text/plain",),
    ".md": ("text/markdown", "text/plain"),
    ".html": ("text/html",),
    ".pdf": ("application/pdf",),
    ".csv": ("text/csv", "text/plain", "application/csv"),
}


async def spool(
    file: UploadFile, max_bytes: int | None = None
) -> tuple[tempfile.SpooledTemporaryFile[bytes], int, str, bytes, bytes]:
    settings = get_settings()
    limit = max_bytes or settings.upload_max_bytes
    output = tempfile.SpooledTemporaryFile(max_size=settings.upload_spool_max_bytes, mode="w+b")
    digest, size, head, tail = hashlib.sha256(), 0, bytearray(), bytearray()
    while chunk := await file.read(64 * 1024):
        size += len(chunk)
        if size > limit:
            output.close()
            raise HTTPException(413, f"file exceeds {limit} byte limit")
        if len(head) < 8192:
            head.extend(chunk[: 8192 - len(head)])
        tail.extend(chunk)
        if len(tail) > 8192:
            del tail[:-8192]
        digest.update(chunk)
        output.write(chunk)
    output.seek(0)
    return output, size, digest.hexdigest(), bytes(head), bytes(tail)


def validate(file: UploadFile, head: bytes, tail: bytes) -> str:
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    if not filename or filename != file.filename or extension not in MIMES:
        raise HTTPException(400, "invalid filename or extension")
    mime = (file.content_type or "").split(";", 1)[0].lower()
    if mime not in MIMES[extension]:
        raise HTTPException(415, "MIME type does not match extension")
    if not head:
        raise HTTPException(415, "empty files are not supported")
    if extension == ".pdf" and (not head.startswith(b"%PDF-") or b"%%EOF" not in tail):
        raise HTTPException(415, "invalid PDF signature")
    if extension != ".pdf":
        try:
            text = head.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(415, "text upload is not UTF-8") from exc
        if "\x00" in text:
            raise HTTPException(415, "text upload contains binary data")
        lowered = text.lstrip().lower()
        if extension == ".html" and not lowered.startswith(
            ("<!doctype html", "<html", "<head", "<body")
        ):
            raise HTTPException(415, "invalid HTML content")
    return filename


def serialize(item: Document, duplicate: bool = False) -> dict[str, object]:
    return {
        "id": item.id,
        "project_id": str(item.project_id),
        "dataset_id": item.dataset_id,
        "filename": item.filename,
        "mime_type": item.mime_type,
        "size_bytes": item.size_bytes,
        "content_hash": item.content_hash,
        "object_key": item.object_key,
        "status": item.status.value,
        "error_message": item.error_message,
        "duplicate": duplicate,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@router.post("/v1/datasets/{dataset_id}/documents", status_code=201)
async def upload(
    dataset_id: str,
    file: Annotated[UploadFile, File()],
    project: Annotated[ProjectContext, Depends(require_project)],
    db: Annotated[AsyncSession, Depends(get_session)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
) -> dict[str, object]:
    await owned(db, project, dataset_id)
    stream, size, digest, head, tail = await spool(file)
    try:
        filename = validate(file, head, tail)
        query = (
            select(Document)
            .where(
                Document.project_id == project.project_id,
                Document.dataset_id == dataset_id,
                Document.content_hash == digest,
            )
            .with_for_update()
        )
        existing = await db.scalar(query)
        if existing is None:
            document_id = new_id("doc")
            candidate = Document(
                id=document_id,
                project_id=project.project_id,
                dataset_id=dataset_id,
                filename=filename,
                mime_type=(file.content_type or "").split(";", 1)[0].lower(),
                size_bytes=size,
                content_hash=digest,
                object_key=f"projects/{project.project_id}/datasets/{dataset_id}/documents/{document_id}/raw",
                status=DocumentStatus.PENDING_UPLOAD,
                metadata_={},
            )
            try:
                # A savepoint contains the uniqueness failure without expiring the
                # outer transaction's identity map.
                async with db.begin_nested():
                    db.add(candidate)
                    await db.flush()
                existing = candidate
            except IntegrityError:
                # The unique constraint waits for a concurrent inserter. Lock its
                # committed row before deciding whether this request must upload.
                existing = await db.scalar(query)
                if existing is None:
                    raise

        if existing.status == DocumentStatus.UPLOADED:
            result = serialize(existing, True)
            await db.commit()
            return result

        existing.status, existing.error_message = DocumentStatus.PENDING_UPLOAD, None
        await db.flush()
        try:
            await store.upload(existing.object_key, stream, existing.mime_type)
        except Exception as exc:
            existing.status, existing.error_message = DocumentStatus.STORAGE_FAILED, str(exc)[:2000]
            await db.commit()
            raise HTTPException(503, "object storage upload failed") from exc
        existing.status, existing.error_message = DocumentStatus.UPLOADED, None
        await enqueue_document(db, existing)
        await db.flush()
        # SQL expressions used by onupdate expire updated_at after flush; reload
        # explicitly while async IO is legal before passing the object to sync code.
        await db.refresh(existing)
        result = serialize(existing)
        await db.commit()
        return result
    finally:
        stream.close()


async def owned_document(db: AsyncSession, project: ProjectContext, document_id: str) -> Document:
    item = await db.scalar(
        select(Document).where(
            Document.id == document_id, Document.project_id == project.project_id
        )
    )
    if item is None:
        raise HTTPException(404, "document not found")
    return item


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
    item = await owned_document(db, project, document_id)
    if item.dataset_id != dataset_id:
        raise HTTPException(404, "document not found")
    return serialize(item)


@router.get("/v1/documents/{document_id}")
async def get_document_by_id(
    document_id: str,
    project: Annotated[ProjectContext, Depends(require_project)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    return serialize(await owned_document(db, project, document_id))


@router.delete("/v1/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    project: Annotated[ProjectContext, Depends(require_project)],
    db: Annotated[AsyncSession, Depends(get_session)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
) -> Response:
    item = await owned_document(db, project, document_id)
    item.status, item.error_message = DocumentStatus.DELETING, None
    cleanup = await create_document_cleanup(db, item)
    await db.commit()
    try:
        await store.delete(item.object_key)
    except Exception as exc:
        item.status, item.error_message = DocumentStatus.DELETE_FAILED, str(exc)[:2000]
        await db.commit()
        raise HTTPException(503, "object storage deletion failed") from exc
    # Flush the document cascade first so concurrent evidence inserts cannot escape collection.
    await db.delete(item)
    await db.flush()
    await cleanup_document_graph(db, item.project_id, item.dataset_id, item.id)
    await mark_cleanup_ready(db, cleanup)
    await db.commit()
    return Response(status_code=204)
