from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from open_graph_core.ids import new_id
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ProjectContext, require_project
from app.dependencies import get_session
from app.graph_cleanup import create_dataset_cleanup, mark_cleanup_ready
from app.models import Dataset, DatasetStatus, Document, DocumentStatus
from app.storage import ObjectStore, get_object_store

router = APIRouter(prefix="/v1/datasets", tags=["datasets"])
Project = Annotated[ProjectContext, Depends(require_project)]
Db = Annotated[AsyncSession, Depends(get_session)]


class DatasetInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, object] = Field(default_factory=dict)


class DatasetPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, object] | None = None


class DatasetView(DatasetInput):
    id: str
    project_id: str
    status: str
    error_message: str | None
    model_config = {"from_attributes": True}


def view(item: Dataset) -> DatasetView:
    return DatasetView(
        id=item.id,
        project_id=str(item.project_id),
        name=item.name,
        description=item.description,
        metadata=item.metadata_,
        status=item.status.value,
        error_message=item.error_message,
    )


async def owned(db: AsyncSession, project: ProjectContext, dataset_id: str) -> Dataset:
    # Accept both formats: with prefix (ds_xxx) or without (xxx)
    if not dataset_id.startswith("ds_"):
        dataset_id = f"ds_{dataset_id}"
    item = await db.scalar(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project.project_id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return item


@router.post("", response_model=DatasetView, status_code=201)
async def create(body: DatasetInput, project: Project, db: Db) -> DatasetView:
    item = Dataset(
        id=new_id("ds"),
        project_id=project.project_id,
        name=body.name,
        description=body.description,
        metadata_=body.metadata,
        status=DatasetStatus.ACTIVE,
    )
    db.add(item)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="dataset name already exists") from exc
    return view(item)


@router.get("", response_model=list[DatasetView])
async def list_datasets(project: Project, db: Db) -> list[DatasetView]:
    rows = await db.scalars(
        select(Dataset).where(Dataset.project_id == project.project_id).order_by(Dataset.created_at)
    )
    return [view(row) for row in rows]


@router.get("/{dataset_id}", response_model=DatasetView)
async def get(dataset_id: str, project: Project, db: Db) -> DatasetView:
    return view(await owned(db, project, dataset_id))


@router.patch("/{dataset_id}", response_model=DatasetView)
async def update(dataset_id: str, body: DatasetPatch, project: Project, db: Db) -> DatasetView:
    item = await owned(db, project, dataset_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(item, "metadata_" if key == "metadata" else key, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="dataset name already exists") from exc
    return view(item)


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    dataset_id: str,
    project: Project,
    db: Db,
    store: Annotated[ObjectStore, Depends(get_object_store)],
) -> Response:
    item = await owned(db, project, dataset_id)
    item.status, item.error_message = DatasetStatus.DELETING, None
    cleanup = await create_dataset_cleanup(db, item)
    await db.commit()
    documents = list(
        await db.scalars(
            select(Document).where(
                Document.project_id == project.project_id, Document.dataset_id == dataset_id
            )
        )
    )
    last_document = None
    try:
        for document in documents:
            last_document = document
            document.status = DocumentStatus.DELETING
            await db.commit()
            await store.delete(document.object_key)
            await db.delete(document)
            await db.commit()
    except Exception as exc:
        item.status, item.error_message = DatasetStatus.DELETE_FAILED, str(exc)[:2000]
        if last_document is not None and last_document.status == DocumentStatus.DELETING:
            last_document.status, last_document.error_message = DocumentStatus.DELETE_FAILED, str(exc)[:2000]
        await db.commit()
        raise HTTPException(503, "dataset object deletion failed") from exc
    await mark_cleanup_ready(db, cleanup)
    await db.delete(item)
    await db.commit()
    return Response(status_code=204)
