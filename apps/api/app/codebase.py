"""Continuous Codebase Knowledge Graph Ingestion and Real-Time File Sync API."""

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from open_graph_core.code_extractor import CodeExtractor
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    dataset_name: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=1000)
    files: list[FileIngestItem] = Field(..., min_length=1, max_length=1000)


class SingleFileSyncRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1, max_length=100)
    file_path: str = Field(..., min_length=1, max_length=500)
    code: str = Field(..., min_length=1)
    language: str | None = Field(None, max_length=50)


class CodebaseIngestResponse(BaseModel):
    dataset_id: str
    dataset_name: str
    files_processed: int
    entities_inserted: int
    relations_inserted: int
    communities_count: int


def _short_id(prefix: str, val: str) -> str:
    digest = hashlib.sha256(val.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


@router.post("/ingest", response_model=CodebaseIngestResponse, status_code=status.HTTP_200_OK)
async def ingest_codebase(
    payload: CodebaseIngestRequest,
    ctx: ProjectDep,
    db: DbDep,
) -> CodebaseIngestResponse:
    """Batch ingest codebase files into Knowledge Graph with AST parsing and Louvain analytics."""
    from app.models import Dataset, DatasetStatus
    from app.graph_analytics import refresh_dataset_analytics
    from sqlalchemy import select

    project_id = ctx.project_id
    dataset_id = payload.dataset_id
    dataset_name = payload.dataset_name or dataset_id

    # 1. Ensure dataset exists
    existing_ds = await db.scalar(select(Dataset).where(Dataset.project_id == project_id, Dataset.id == dataset_id))
    if not existing_ds:
        ds = Dataset(
            id=dataset_id,
            project_id=project_id,
            name=dataset_name,
            description=payload.description or f"AST Knowledge Graph for {dataset_name}",
            status=DatasetStatus.ACTIVE,
        )
        db.add(ds)
        await db.commit()

    now = datetime.now(UTC)
    extracted_entities = []
    extracted_relations = []
    symbol_table = {}
    raw_entity_map = {}

    for item in payload.files:
        res = extractor.extract_file(file_path=item.file_path, content=item.code)
        for entity in res.entities:
            entity_id = _short_id("ce", f"{dataset_id}:{entity.id}")
            raw_entity_map[entity.id] = entity_id
            if entity.kind.value in {"class", "function", "method", "interface", "struct"}:
                symbol_table[entity.name] = entity_id
                symbol_table[entity.name.lower()] = entity_id
            extracted_entities.append((entity, entity_id))
        extracted_relations.extend(res.relations)

    # 2. Insert canonical entities
    for entity, entity_id in extracted_entities:
        normalized_name = f"{entity.file_path if hasattr(entity, 'file_path') else ''}::{entity.name}::{entity.start_line}".lower()[:500]
        kind_val = entity.kind.value if hasattr(entity.kind, "value") else entity.kind
        entity_type = f"code.{kind_val}"

        stmt = (
            pg_insert(CanonicalEntity)
            .values(
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
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"canonical_name": entity.name, "updated_at": now},
            )
        )
        await db.execute(stmt)

    await db.commit()

    db_entity_ids = set(await db.scalars(
        select(CanonicalEntity.id).where(
            CanonicalEntity.project_id == project_id,
            CanonicalEntity.dataset_id == dataset_id
        )
    ))

    # 3. Insert cross-file relations
    total_relations = 0
    seen_rel_keys = set()

    for rel in extracted_relations:
        source_id = raw_entity_map.get(rel.source_id) or _short_id("ce", f"{dataset_id}:{rel.source_id}")
        if source_id not in db_entity_ids:
            continue

        target_id = raw_entity_map.get(rel.target_id)
        if not target_id or target_id not in db_entity_ids:
            extracted_sym = None
            if rel.quote:
                m = rel.quote.split("(")[0].split(" ")[-1].replace(".", "").strip()
                if m in symbol_table:
                    extracted_sym = m
            if not extracted_sym:
                for p in rel.target_id.split("_"):
                    if p in symbol_table:
                        extracted_sym = p
                        break
            if extracted_sym and extracted_sym in symbol_table:
                target_id = symbol_table[extracted_sym]
            else:
                target_id = _short_id("ce", f"{dataset_id}:{rel.target_id}")

        if target_id not in db_entity_ids or source_id == target_id:
            continue

        relation_type_val = rel.kind.value if hasattr(rel.kind, "value") else rel.kind
        rel_key = (source_id, target_id, relation_type_val)
        if rel_key in seen_rel_keys:
            continue
        seen_rel_keys.add(rel_key)

        rel_id = _short_id("ra", f"{dataset_id}:{source_id}->{relation_type_val}->{target_id}")
        stmt = (
            pg_insert(RelationAssertion)
            .values(
                id=rel_id,
                project_id=project_id,
                dataset_id=dataset_id,
                source_entity_id=source_id,
                target_entity_id=target_id,
                relation_type=relation_type_val,
                confidence=1.0,
                review_state=ReviewState.APPROVED,
                extractor_version="deterministic_code_v1",
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"confidence": 1.0, "updated_at": now},
            )
        )
        await db.execute(stmt)
        total_relations += 1

    await db.commit()

    # 4. Refresh Louvain Community Analytics
    analytics_run = await refresh_dataset_analytics(db, project_id, dataset_id)
    communities_count = analytics_run.community_count
    await db.commit()

    return CodebaseIngestResponse(
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        files_processed=len(payload.files),
        entities_inserted=len(db_entity_ids),
        relations_inserted=total_relations,
        communities_count=communities_count,
    )



class DirectoryIndexRequest(BaseModel):
    directory_path: str = Field(..., min_length=1, max_length=1000)
    dataset_id: str | None = Field(None, max_length=100)
    dataset_name: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=1000)


class DirectoryIndexResponse(BaseModel):
    dataset_id: str
    dataset_name: str
    files_processed: int
    loc_count: int
    entities_inserted: int
    relations_inserted: int
    communities_count: int
    duration_seconds: float


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


@router.post("/index-directory", response_model=DirectoryIndexResponse, status_code=status.HTTP_200_OK)
async def index_directory(
    payload: DirectoryIndexRequest,
    ctx: ProjectDep,
    db: DbDep,
) -> DirectoryIndexResponse:
    """Scan and index an entire local codebase directory into an isolated dataset in seconds."""
    import time
    from pathlib import Path
    from app.models import Dataset, DatasetStatus
    from app.graph_analytics import refresh_dataset_analytics
    from sqlalchemy import select, delete

    start_time = time.perf_counter()
    project_id = ctx.project_id
    dir_path = Path(payload.directory_path)

    if not dir_path.exists() or not dir_path.is_dir():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Directory '{payload.directory_path}' does not exist on server.")

    dir_stem = dir_path.name.lower().replace("-", "_").replace(" ", "_")
    dataset_id = payload.dataset_id or f"ds_{dir_stem}"
    dataset_name = payload.dataset_name or f"{dir_path.name} Codebase"
    dataset_desc = payload.description or f"AST Knowledge Graph for {dir_path.name}"

    # 1. Ensure clean dataset record
    existing_ds = await db.scalar(select(Dataset).where(Dataset.project_id == project_id, Dataset.id == dataset_id))
    if not existing_ds:
        ds = Dataset(
            id=dataset_id,
            project_id=project_id,
            name=dataset_name,
            description=dataset_desc,
            status=DatasetStatus.ACTIVE,
        )
        db.add(ds)
        await db.commit()

    # 2. Scan source files
    valid_exts = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs", ".c", ".cpp", ".h", ".hpp"}
    ignore_dirs = {".venv", "venv", ".git", "__pycache__", "build", "dist", "node_modules", "out", ".next", "generated", ".prisma"}

    code_items = []
    total_loc = 0

    for file_path in dir_path.rglob("*"):
        if not file_path.is_file():
            continue
        if any(ign in file_path.parts for ign in ignore_dirs):
            continue
        if file_path.name.endswith(".min.js") or file_path.name.endswith(".d.ts"):
            continue
        if file_path.suffix.lower() not in valid_exts:
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            rel_path = str(file_path.relative_to(dir_path)).replace("\\", "/")
            code_items.append((rel_path, content))
            total_loc += len(content.splitlines())
        except Exception:
            continue

    now = datetime.now(UTC)
    extracted_entities = []
    extracted_relations = []
    symbol_table = {}
    raw_entity_map = {}

    for rel_path, code in code_items:
        res = extractor.extract_file(file_path=rel_path, content=code)
        for entity in res.entities:
            entity_id = _short_id("ce", f"{dataset_id}:{entity.id}")
            raw_entity_map[entity.id] = entity_id
            if entity.kind.value in {"class", "function", "method", "interface", "struct"}:
                symbol_table[entity.name] = entity_id
                symbol_table[entity.name.lower()] = entity_id
            extracted_entities.append((entity, entity_id))
        extracted_relations.extend(res.relations)

    # 3. Insert canonical entities
    for entity, entity_id in extracted_entities:
        normalized_name = f"{entity.file_path if hasattr(entity, 'file_path') else ''}::{entity.name}::{entity.start_line}".lower()[:500]
        kind_val = entity.kind.value if hasattr(entity.kind, "value") else entity.kind
        entity_type = f"code.{kind_val}"

        stmt = (
            pg_insert(CanonicalEntity)
            .values(
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
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"canonical_name": entity.name, "updated_at": now},
            )
        )
        await db.execute(stmt)

    await db.commit()

    db_entity_ids = set(await db.scalars(
        select(CanonicalEntity.id).where(
            CanonicalEntity.project_id == project_id,
            CanonicalEntity.dataset_id == dataset_id
        )
    ))

    # 4. Insert cross-file relations
    total_relations = 0
    seen_rel_keys = set()

    for rel in extracted_relations:
        source_id = raw_entity_map.get(rel.source_id) or _short_id("ce", f"{dataset_id}:{rel.source_id}")
        if source_id not in db_entity_ids:
            continue

        target_id = raw_entity_map.get(rel.target_id)
        if not target_id or target_id not in db_entity_ids:
            extracted_sym = None
            if rel.quote:
                m = rel.quote.split("(")[0].split(" ")[-1].replace(".", "").strip()
                if m in symbol_table:
                    extracted_sym = m
            if not extracted_sym:
                for p in rel.target_id.split("_"):
                    if p in symbol_table:
                        extracted_sym = p
                        break
            if extracted_sym and extracted_sym in symbol_table:
                target_id = symbol_table[extracted_sym]
            else:
                target_id = _short_id("ce", f"{dataset_id}:{rel.target_id}")

        if target_id not in db_entity_ids or source_id == target_id:
            continue

        relation_type_val = rel.kind.value if hasattr(rel.kind, "value") else rel.kind
        rel_key = (source_id, target_id, relation_type_val)
        if rel_key in seen_rel_keys:
            continue
        seen_rel_keys.add(rel_key)

        rel_id = _short_id("ra", f"{dataset_id}:{source_id}->{relation_type_val}->{target_id}")
        stmt = (
            pg_insert(RelationAssertion)
            .values(
                id=rel_id,
                project_id=project_id,
                dataset_id=dataset_id,
                source_entity_id=source_id,
                target_entity_id=target_id,
                relation_type=relation_type_val,
                confidence=1.0,
                review_state=ReviewState.APPROVED,
                extractor_version="deterministic_code_v1",
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"confidence": 1.0, "updated_at": now},
            )
        )
        await db.execute(stmt)
        total_relations += 1

    await db.commit()

    # 5. Louvain Analytics
    analytics_run = await refresh_dataset_analytics(db, project_id, dataset_id)
    communities_count = analytics_run.community_count
    await db.commit()

    duration = time.perf_counter() - start_time

    return DirectoryIndexResponse(
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        files_processed=len(code_items),
        loc_count=total_loc,
        entities_inserted=len(db_entity_ids),
        relations_inserted=total_relations,
        communities_count=communities_count,
        duration_seconds=round(duration, 3),
    )

