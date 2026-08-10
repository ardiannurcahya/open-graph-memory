"""Continuous Codebase Knowledge Graph Ingestion and Real-Time File Sync API."""

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from open_graph_core.code_extractor import CodeExtractor
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ProjectContext, require_project
from app.dependencies import get_session
from app.graph_models import CanonicalEntity, RelationAssertion, ReviewState

router = APIRouter(prefix="/v1/codebase", tags=["codebase"])
extractor = CodeExtractor()

ProjectDep = Annotated[ProjectContext, Depends(require_project)]
DbDep = Annotated[AsyncSession, Depends(get_session)]


class FileIngestItem(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=500)
    code: str = Field(..., min_length=1)
    language: str | None = Field(None, max_length=50)


class CodebaseIngestRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1, max_length=100)
    files: list[FileIngestItem] = Field(..., min_length=1, max_length=500)


class SingleFileSyncRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1, max_length=100)
    file_path: str = Field(..., min_length=1, max_length=500)
    code: str = Field(..., min_length=1)
    language: str | None = Field(None, max_length=50)


class CodebaseIngestResponse(BaseModel):
    dataset_id: str
    files_processed: int
    entities_inserted: int
    relations_inserted: int


def _short_id(prefix: str, val: str) -> str:
    digest = hashlib.sha256(val.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


@router.post("/ingest", response_model=CodebaseIngestResponse, status_code=status.HTTP_200_OK)
async def ingest_codebase(
    payload: CodebaseIngestRequest,
    ctx: ProjectDep,
    db: DbDep,
) -> CodebaseIngestResponse:

    """Batch ingest codebase files into Knowledge Graph with AST parsing."""
    project_id = ctx.project_id
    dataset_id = payload.dataset_id

    total_entities = 0
    total_relations = 0
    now = datetime.now(UTC)

    for item in payload.files:
        result = extractor.extract(
            code=item.code, file_path=item.file_path, language=item.language
        )

        # Insert or update canonical entities
        for entity in result.entities:
            normalized_name = f"{item.file_path}::{entity.name}".lower()[:500]
            kind_val = entity.kind.value if hasattr(entity.kind, "value") else entity.kind
            entity_type = f"code.{kind_val}"


            existing = await db.scalar(
                select(CanonicalEntity).where(
                    CanonicalEntity.project_id == project_id,
                    CanonicalEntity.dataset_id == dataset_id,
                    CanonicalEntity.normalized_name == normalized_name,
                    CanonicalEntity.entity_type == entity_type,
                )
            )

            if existing:
                existing.canonical_name = entity.name
                existing.version += 1
                existing.valid_until = None
                existing.updated_at = now
            else:
                entity_id = _short_id("ce", entity.id)
                c_entity = CanonicalEntity(
                    id=entity_id,
                    project_id=project_id,
                    dataset_id=dataset_id,
                    canonical_name=entity.name,
                    normalized_name=normalized_name,
                    entity_type=entity_type,
                    confidence=1.0,
                    review_state=ReviewState.APPROVED,
                    created_at=now,
                    updated_at=now,
                )
                db.add(c_entity)
            total_entities += 1

        # Insert relations
        for rel in result.relations:
            rel_kind = rel.kind.value if hasattr(rel.kind, "value") else str(rel.kind)
            relation_id = _short_id("rel", f"{rel.source_id}_{rel_kind}_{rel.target_id}")

            existing_rel = await db.scalar(
                select(RelationAssertion).where(
                    RelationAssertion.id == relation_id,
                    RelationAssertion.project_id == project_id,
                    RelationAssertion.dataset_id == dataset_id,
                )
            )
            if existing_rel:
                existing_rel.valid_until = None
                existing_rel.updated_at = now
            else:
                r_assertion = RelationAssertion(
                    id=relation_id,
                    project_id=project_id,
                    dataset_id=dataset_id,
                    source_entity_id=_short_id("ce", rel.source_id),
                    target_entity_id=_short_id("ce", rel.target_id),
                    relation_type=rel_kind,
                    extractor_version="1.0.0",
                    confidence=rel.confidence if hasattr(rel, "confidence") else 1.0,
                    review_state=ReviewState.APPROVED,
                    created_at=now,
                    updated_at=now,
                )
                db.add(r_assertion)
            total_relations += 1



    await db.commit()

    return CodebaseIngestResponse(
        dataset_id=dataset_id,
        files_processed=len(payload.files),
        entities_inserted=total_entities,
        relations_inserted=total_relations,
    )


@router.post("/sync-file", response_model=CodebaseIngestResponse, status_code=status.HTTP_200_OK)
async def sync_codebase_file(
    payload: SingleFileSyncRequest,
    ctx: ProjectDep,
    db: DbDep,
) -> CodebaseIngestResponse:
    """Real-time single file AST sync for AI agents during live editing."""
    file_item = FileIngestItem(
        file_path=payload.file_path,
        code=payload.code,
        language=payload.language,
    )
    ingest_req = CodebaseIngestRequest(
        dataset_id=payload.dataset_id,
        files=[file_item],
    )
    return await ingest_codebase(payload=ingest_req, ctx=ctx, db=db)

