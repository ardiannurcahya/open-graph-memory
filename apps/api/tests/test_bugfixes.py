"""Regression test suite for verified bug fixes."""

import hashlib
import io
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.audit import create_audit_log
from app.auth import ProjectContext
from app.legal_hold import check_legal_hold
from app.main import app
from app.mcp_server import execute_tool
from app.memory.confidence import supersede_memory
from app.memory.service import fetch_search_results
from app.models import (
    AgentMemoryEpisode,
    ApiKey,
    Dataset,
    DatasetStatus,
    Document,
    DocumentStatus,
    LegalHold,
    Project,
)
from app.retention import RetentionInput, apply_retention
from app.storage import LocalObjectStore
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


# 1. LocalObjectStore path traversal protection
async def test_local_object_store_path_traversal(tmp_path: Path):
    store = LocalObjectStore(tmp_path)

    # Valid key
    await store.upload("valid/file.txt", io.BytesIO(b"hello"), "text/plain")
    data = await store.download("valid/file.txt")
    assert data == b"hello"

    # Absolute path / leading slash should not escape base_dir
    await store.upload("/nested/abs.txt", io.BytesIO(b"content"), "text/plain")
    assert (tmp_path / "nested/abs.txt").exists()

    # Traversal attempt escaping base_dir must raise ValueError
    with pytest.raises(ValueError, match="Path traversal detected"):
        await store.upload("../evil.txt", io.BytesIO(b"evil"), "text/plain")

    with pytest.raises(ValueError, match="Path traversal detected"):
        await store.download("../../etc/passwd")

    with pytest.raises(ValueError, match="Path traversal detected"):
        await store.delete("../../etc/passwd")


# 2. Audit and Legal Hold pagination count with func.count()
async def test_audit_and_legal_hold_pagination(
    session: AsyncSession, project: Project, api_key: ApiKey
):
    client = TestClient(app)
    headers = {
        "X-API-Key": api_key.key_prefix + "test",
        "X-Project-ID": str(project.id),
    }

    # Add audit logs
    for i in range(3):
        await create_audit_log(
            db=session,
            project_id=project.id,
            actor_type="api_key",
            actor_id="test",
            operation=f"op_{i}",
            resource_type="episode",
            resource_id=f"mem_audit_{i}",
        )
    await session.commit()

    res = client.get("/v1/audit-logs?limit=2&offset=0", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert len(data["logs"]) == 2

    # Add legal holds
    for i in range(3):
        hold = LegalHold(
            id=f"lh_test_p_{i}",
            project_id=project.id,
            resource_type="episode",
            resource_id=f"mem_hold_{i}",
            reason="testing",
            created_by="api_key",
        )
        session.add(hold)
    await session.commit()

    res = client.get("/v1/legal-holds?limit=2&offset=0", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert len(data["holds"]) == 2


# 3. Supersede memory cycle detection
async def test_supersede_memory_cycle_detection(session: AsyncSession, project: Project):
    ep1 = AgentMemoryEpisode(
        id="mem_cycle_1",
        project_id=project.id,
        domain="engineering",
        title="Episode 1",
        goal="Goal 1",
        problem_signature="sig1",
    )
    ep2 = AgentMemoryEpisode(
        id="mem_cycle_2",
        project_id=project.id,
        domain="engineering",
        title="Episode 2",
        goal="Goal 2",
        problem_signature="sig2",
    )
    session.add_all([ep1, ep2])
    await session.commit()

    # Self-supersession must fail
    with pytest.raises(HTTPException) as exc_info:
        await supersede_memory(session, ep1, ep1.id)
    assert exc_info.value.status_code == 400

    # ep1 superseded by ep2
    await supersede_memory(session, ep1, ep2.id)
    assert ep1.status == "superseded"
    assert ep1.superseded_by_id == ep2.id

    # ep2 superseded by ep1 must detect cycle
    with pytest.raises(HTTPException) as exc_info:
        await supersede_memory(session, ep2, ep1.id)
    assert exc_info.value.status_code == 400
    assert "cycle" in exc_info.value.detail


# 4. Project-level legal hold in retention and check_legal_hold
async def test_project_level_legal_hold(session: AsyncSession, project: Project):
    # Add project-level legal hold
    hold = LegalHold(
        id="lh_proj_hold_1",
        project_id=project.id,
        resource_type="project",
        resource_id=str(project.id),
        reason="Litigation hold on entire project",
        created_by="legal",
    )
    session.add(hold)
    await session.commit()

    # check_legal_hold must block resource actions
    with pytest.raises(HTTPException) as exc_info:
        await check_legal_hold(session, str(project.id), ["mem_any"])
    assert exc_info.value.status_code == 423
    assert "project is under legal hold" in exc_info.value.detail

    # apply_retention must be aborted with 0 affected count
    ctx = ProjectContext(project_id=project.id)
    ret_res = await apply_retention(
        body=RetentionInput(resource_type="episode", older_than_days=1, action="archive"),
        project=ctx,
        db=session,
    )
    assert ret_res.affected_count == 0


# 5. MCP server memory_feedback and memory_forget execution
async def test_mcp_feedback_and_forget(session: AsyncSession, project: Project):
    ep = AgentMemoryEpisode(
        id="mem_mcp_target",
        project_id=project.id,
        domain="engineering",
        type="custom",
        title="MCP Test",
        goal="Goal",
        problem_signature="mcp-sig",
        status="open",
        confidence=0.5,
    )
    session.add(ep)
    await session.commit()

    # memory_feedback: confirm
    fb_res = await execute_tool(
        name="memory_feedback",
        arguments={
            "memory_id": ep.id,
            "kind": "confirm",
            "idempotency_key": "idemp_fb_1",
        },
        project_id=str(project.id),
        db=session,
    )
    assert fb_res.get("status") == "open"
    assert fb_res.get("confidence") == 0.6

    # memory_forget: archive
    fg_res = await execute_tool(
        name="memory_forget",
        arguments={
            "memory_id": ep.id,
            "mode": "archive",
            "idempotency_key": "idemp_fg_1",
        },
        project_id=str(project.id),
        db=session,
    )
    assert fg_res.get("deleted") is True
    assert fg_res.get("mode") == "archive"
    await session.refresh(ep)
    assert ep.status == "archived"


# 6. Cross-project import ID collision avoidance
async def test_cross_project_import_collision(
    session: AsyncSession, project: Project, api_key: ApiKey
):
    client = TestClient(app)

    # Create project 2
    proj2 = Project(id=uuid.uuid4(), name="Target Project")
    key_prefix = "proj2_key_prefix"  # 16 chars
    key_hash = hashlib.sha256((key_prefix + "test").encode()).hexdigest()
    key2 = ApiKey(
        id=uuid.uuid4(),
        project_id=proj2.id,
        name="Key 2",
        key_hash=key_hash,
        key_prefix=key_prefix,
    )
    # Episode existing in project 1
    ep1 = AgentMemoryEpisode(
        id="mem_shared_id_123",
        project_id=project.id,
        domain="custom",
        title="Original",
        goal="Original goal",
        problem_signature="sig",
    )
    session.add_all([proj2, key2, ep1])
    await session.commit()

    # Import export data with the same ID into project 2
    import_payload = {
        "owner_email": "admin@example.com",
        "data": {
            "episodes": [
                {
                    "id": "mem_shared_id_123",
                    "title": "Imported title",
                    "goal": "Imported goal",
                    "problem_signature": "sig",
                    "attempts": [{"id": "att_shared_id", "hypothesis": "hyp"}],
                }
            ]
        },
    }
    headers = {
        "X-API-Key": key2.key_prefix + "test",
        "X-Project-ID": str(proj2.id),
    }
    res = client.post(f"/v1/projects/{proj2.id}/import", json=import_payload, headers=headers)
    assert res.status_code == 200
    assert res.json()["episodes_imported"] == 1

    # Verify both episodes exist in database without PK collision
    episodes = list(await session.scalars(select(AgentMemoryEpisode)))
    assert len(episodes) == 2
    proj2_eps = [e for e in episodes if str(e.project_id) == str(proj2.id)]
    assert len(proj2_eps) == 1
    assert proj2_eps[0].id != "mem_shared_id_123"  # Remapped!


# 7. Duplicate document upload state preservation
async def test_duplicate_document_upload_state(
    session: AsyncSession, project: Project, api_key: ApiKey
):
    client = TestClient(app)
    headers = {
        "X-API-Key": api_key.key_prefix + "test",
        "X-Project-ID": str(project.id),
    }

    # Setup dataset and indexed document
    ds = Dataset(
        id="ds_upload_test",
        project_id=project.id,
        name="Upload Test",
        status=DatasetStatus.ACTIVE,
    )
    content = b"plain text content for testing duplicate upload"
    digest = hashlib.sha256(content).hexdigest()

    doc = Document(
        id="doc_indexed_1",
        project_id=project.id,
        dataset_id=ds.id,
        filename="test.txt",
        mime_type="text/plain",
        size_bytes=len(content),
        content_hash=digest,
        object_key="test_key",
        graph_stage="complete",
        status=DocumentStatus.INDEXED,
    )
    session.add_all([ds, doc])
    await session.commit()

    # Upload duplicate file
    res = client.post(
        f"/v1/datasets/{ds.id}/documents",
        files={"file": ("test.txt", content, "text/plain")},
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["id"] == "doc_indexed_1"
    assert data["status"] == "indexed"
    assert data["duplicate"] is True

    # Ensure status remained INDEXED
    await session.refresh(doc)
    assert doc.status == DocumentStatus.INDEXED


# 8. Codebase index-directory sensitive path rejection
async def test_codebase_sensitive_path_rejection(
    session: AsyncSession, project: Project, api_key: ApiKey
):
    client = TestClient(app)
    headers = {
        "X-API-Key": api_key.key_prefix + "test",
        "X-Project-ID": str(project.id),
    }

    res = client.post(
        "/v1/codebase/index-directory",
        json={"directory_path": "/etc"},
        headers=headers,
    )
    assert res.status_code == 400
    assert "forbidden" in res.json()["detail"].lower()

    res = client.post(
        "/v1/codebase/index-directory",
        json={"directory_path": "/root"},
        headers=headers,
    )
    assert res.status_code == 400
    assert "forbidden" in res.json()["detail"].lower()


# 9. Fallback search preserves problem_signature, repository, environment filters
async def test_search_fallback_preserves_filters():
    mock_db = AsyncMock()
    executed_statements = []

    async def mock_execute(stmt):
        executed_statements.append(stmt)
        res = MagicMock()
        res.all.return_value = []
        return res

    mock_db.execute = mock_execute
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    mock_db.scalars = AsyncMock(return_value=scalars_mock)

    ctx = ProjectContext(project_id=uuid.uuid4())
    await fetch_search_results(
        db=mock_db,
        project=ctx,
        q="test query",
        problem_signature="sig-test",
        repository="my-repo",
        environment="staging",
        include_inactive=False,
        limit=5,
    )

    assert len(executed_statements) == 2  # 1st: primary FTS, 2nd: fallback ILIKE
    fallback_sql = str(executed_statements[1].compile(compile_kwargs={"literal_binds": True}))
    assert "sig-test" in fallback_sql
    assert "my-repo" in fallback_sql
    assert "staging" in fallback_sql


# 10. Export / Import preserves episode type, content, confidence, and version
async def test_export_import_preserves_memory_fields(
    session: AsyncSession, project: Project, api_key: ApiKey
):
    client = TestClient(app)
    headers = {
        "X-API-Key": api_key.key_prefix + "test",
        "X-Project-ID": str(project.id),
    }

    # Create episode with custom fields
    ep = AgentMemoryEpisode(
        id=f"mem_{uuid.uuid4().hex[:12]}",
        project_id=project.id,
        domain="engineering",
        type="bugfix",
        title="Test Bugfix Memory",
        goal="Preserve all fields across export/import",
        problem_signature="sig-preserve-fields",
        content={"solution": "fix applied", "status": "resolved"},
        confidence=0.88,
        version=3,
        status="open",
    )
    session.add(ep)
    await session.commit()

    # Export project
    export_res = client.get(
        f"/v1/projects/{project.id}/export",
        headers=headers,
    )
    assert export_res.status_code == 200
    export_data = export_res.json()
    episodes = export_data.get("episodes", [])
    matching = [e for e in episodes if e.get("id") == ep.id]
    assert len(matching) == 1
    exported_ep = matching[0]
    assert exported_ep["type"] == "bugfix"
    assert exported_ep["content"] == {"solution": "fix applied", "status": "resolved"}
    assert exported_ep["confidence"] == 0.88
    assert exported_ep["version"] == 3

    # Import into a new project
    proj2 = Project(id=uuid.uuid4(), name="Project 2")
    full_key2 = "test_prefix_1234_secret_key"
    key2 = ApiKey(
        id=uuid.uuid4(),
        project_id=proj2.id,
        name="Key 2",
        key_prefix=full_key2[:16],
        key_hash=hashlib.sha256(full_key2.encode()).hexdigest(),
    )
    session.add_all([proj2, key2])
    await session.commit()

    headers2 = {
        "X-API-Key": full_key2,
        "X-Project-ID": str(proj2.id),
    }
    import_res = client.post(
        f"/v1/projects/{proj2.id}/import",
        json={"data": export_data, "owner_email": "test@example.com"},
        headers=headers2,
    )
    assert import_res.status_code == 200
    assert import_res.json()["episodes_imported"] >= 1

    imported_ep = await session.scalar(
        select(AgentMemoryEpisode).where(
            AgentMemoryEpisode.project_id == proj2.id,
            AgentMemoryEpisode.problem_signature == "sig-preserve-fields",
        )
    )
    assert imported_ep is not None
    assert imported_ep.type == "bugfix"
    assert imported_ep.content == {"solution": "fix applied", "status": "resolved"}
    assert imported_ep.confidence == 0.88
    assert imported_ep.version == 3


# 11. Idempotency check scoped by operation
async def test_idempotency_scoped_by_operation(session: AsyncSession, project: Project):
    from app.idempotency import check_idempotency, store_idempotency

    key = f"idem_{uuid.uuid4().hex}"
    await store_idempotency(
        session,
        key=key,
        project_id=project.id,
        operation="memory.feedback",
        resource_id="res_123",
        result_data={"status": "ok"},
    )
    await session.commit()

    # Different operation must return None
    res_forget = await check_idempotency(session, key, project.id, "memory.forget")
    assert res_forget is None

    # Matching operation returns the resource_id
    res_feedback = await check_idempotency(session, key, project.id, "memory.feedback")
    assert res_feedback == "res_123"


# 12. MCP idempotency replay and confidence validation
async def test_mcp_idempotency_and_confidence_validation(
    session: AsyncSession, project: Project
):
    ep1 = AgentMemoryEpisode(
        id=f"mem_{uuid.uuid4().hex[:12]}",
        project_id=project.id,
        domain="engineering",
        type="bugfix",
        title="Ep 1",
        goal="g1",
        problem_signature="sig-1",
        confidence=0.5,
        version=1,
        status="open",
    )
    ep2 = AgentMemoryEpisode(
        id=f"mem_{uuid.uuid4().hex[:12]}",
        project_id=project.id,
        domain="engineering",
        type="bugfix",
        title="Ep 2",
        goal="g2",
        problem_signature="sig-2",
        confidence=0.5,
        version=1,
        status="open",
    )
    session.add_all([ep1, ep2])
    await session.commit()

    # Feedback with key on ep1
    idem_key = f"idem_{uuid.uuid4().hex}"
    res1 = await execute_tool(
        "memory_feedback",
        {"memory_id": ep1.id, "kind": "confirm", "idempotency_key": idem_key},
        str(project.id),
        session,
    )
    assert res1.get("memory_id") == ep1.id

    # Replay same key with DIFFERENT memory_id (ep2) -> must reject
    res2 = await execute_tool(
        "memory_feedback",
        {"memory_id": ep2.id, "kind": "confirm", "idempotency_key": idem_key},
        str(project.id),
        session,
    )
    assert "error" in res2
    assert "idempotency key was used for a different memory" in res2["error"]

    # Forget with key on ep1
    forget_key = f"forget_{uuid.uuid4().hex}"
    fres1 = await execute_tool(
        "memory_forget",
        {"memory_id": ep1.id, "mode": "archive", "idempotency_key": forget_key},
        str(project.id),
        session,
    )
    assert fres1.get("deleted") is True

    # Replay forget key on ep2 -> must reject
    fres2 = await execute_tool(
        "memory_forget",
        {"memory_id": ep2.id, "mode": "archive", "idempotency_key": forget_key},
        str(project.id),
        session,
    )
    assert "error" in fres2
    assert "idempotency key was used for a different memory" in fres2["error"]

    # Invalid confidence validation on memory_feedback
    err_str = await execute_tool(
        "memory_feedback",
        {"memory_id": ep2.id, "kind": "confirm", "confidence": "not-a-number"},
        str(project.id),
        session,
    )
    assert "error" in err_str
    assert "confidence must be a number" in err_str["error"]

    err_range = await execute_tool(
        "memory_feedback",
        {"memory_id": ep2.id, "kind": "confirm", "confidence": 1.5},
        str(project.id),
        session,
    )
    assert "error" in err_range
    assert "finite number between 0 and 1" in err_range["error"]

    # Invalid confidence on memory_commit
    commit_err = await execute_tool(
        "memory_commit",
        {"type": "custom", "content": {"key": "val"}, "confidence": -0.1},
        str(project.id),
        session,
    )
    assert "error" in commit_err
    assert "finite number between 0 and 1" in commit_err["error"]


# 13. Codebase index-directory allowlist check
async def test_codebase_index_directory_allowlist(
    session: AsyncSession, project: Project, api_key: ApiKey, tmp_path: Path
):
    from app.config import get_settings

    allowed_dir = tmp_path / "allowed_codebase"
    allowed_dir.mkdir()
    outside_dir = tmp_path / "outside_codebase"
    outside_dir.mkdir()

    settings = get_settings()
    orig_root = settings.codebase_index_root
    try:
        settings.codebase_index_root = str(allowed_dir)
        client = TestClient(app)
        headers = {
            "X-API-Key": api_key.key_prefix + "test",
            "X-Project-ID": str(project.id),
        }

        res = client.post(
            "/v1/codebase/index-directory",
            json={"directory_path": str(outside_dir)},
            headers=headers,
        )
        assert res.status_code == 400
        assert "within the configured codebase index root" in res.json()["detail"].lower()
    finally:
        settings.codebase_index_root = orig_root
