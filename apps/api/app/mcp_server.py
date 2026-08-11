"""MCP Streamable HTTP server for agent integration."""

import hashlib
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session
from app.models import AgentMemoryEpisode, ApiKey
from app.redaction import sanitize_input

router = APIRouter(prefix="/mcp", tags=["mcp"])

MCP_SESSION_HEADER = "Mcp-Session-Id"
MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None


class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: Any = None
    error: dict[str, Any] | None = None


class MCPTool(BaseModel):
    name: str
    description: str
    inputSchema: dict[str, Any]


MCP_TOOLS: list[MCPTool] = [
    MCPTool(
        name="memory_observe",
        description="Persist one immutable, redacted evidence episode.",
        inputSchema={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": [
                        "observation",
                        "message",
                        "command",
                        "command_output",
                        "file",
                        "code",
                        "tool_call",
                        "tool_result",
                        "error",
                        "event",
                    ],
                },
                "observation": {
                    "type": "object",
                    "description": "JSON evidence",
                },
                "metadata": {"type": "object"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["kind", "observation", "idempotency_key"],
        },
    ),
    MCPTool(
        name="memory_commit",
        description="Commit a typed durable memory supported by episode evidence.",
        inputSchema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": [
                        "bugfix",
                        "decision",
                        "preference",
                        "procedure",
                        "research",
                        "trading",
                        "learning",
                        "fact",
                        "custom",
                    ],
                },
                "content": {"type": "object"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "episodes": {
                    "type": "array",
                    "items": {"type": "object"},
                },
                "idempotency_key": {"type": "string"},
            },
            "required": [
                "type",
                "content",
                "confidence",
                "episodes",
                "idempotency_key",
            ],
        },
    ),
    MCPTool(
        name="memory_recall",
        description="Recall bounded, explainable memory capsules.",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "exact": {"type": "object"},
                "entity_key": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
    ),
    MCPTool(
        name="memory_feedback",
        description=("Confirm, reject, correct, merge, supersede, stale, or verify a memory."),
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": [
                        "confirm",
                        "reject",
                        "correct",
                        "supersede",
                        "merge",
                        "stale",
                        "verified",
                    ],
                },
                "content": {"type": "object"},
                "confidence": {"type": "number"},
                "target_id": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["memory_id", "kind", "idempotency_key"],
        },
    ),
    MCPTool(
        name="memory_forget",
        description=("Archive or invalidate by default; hard delete requires explicit mode."),
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["archive", "invalidate", "hard_delete"],
                },
                "idempotency_key": {"type": "string"},
            },
            "required": ["memory_id"],
        },
    ),
    MCPTool(
        name="memory_inspect",
        description="Read bounded memory provenance and ranking explanation.",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "include_inactive": {"type": "boolean"},
            },
            "required": ["memory_id"],
        },
    ),
]


async def _authenticate(db: AsyncSession, x_api_key: str, x_project_id: str) -> None:
    digest = hashlib.sha256(x_api_key.encode()).hexdigest()
    key = await db.scalar(
        select(ApiKey).where(
            ApiKey.project_id == x_project_id,
            ApiKey.key_prefix == x_api_key[:16],
            ApiKey.key_hash == digest,
            ApiKey.revoked_at.is_(None),
        )
    )
    if not key:
        raise HTTPException(401, "invalid API key")


async def handle_mcp_request(
    request: MCPRequest,
    project_id: str,
    db: AsyncSession,
) -> MCPResponse:
    if request.method == "initialize":
        return MCPResponse(
            id=request.id,
            result={
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "ogm-mcp", "version": "1.0.0"},
            },
        )

    if request.method == "tools/list":
        return MCPResponse(
            id=request.id,
            result={"tools": [tool.model_dump() for tool in MCP_TOOLS]},
        )

    if request.method == "tools/call":
        tool_name = request.params.get("name") if request.params else None
        arguments = request.params.get("arguments", {}) if request.params else {}

        if not tool_name:
            return MCPResponse(
                id=request.id,
                error={"code": -32602, "message": "missing tool name"},
            )

        result = await execute_tool(tool_name, arguments, project_id, db)
        return MCPResponse(id=request.id, result=result)

    if request.method == "resources/list":
        return MCPResponse(
            id=request.id,
            result={
                "resources": [
                    {
                        "uri": "ogm://project/profile",
                        "name": "Project profile",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": "ogm://project/memories/recent?limit=20",
                        "name": "Recent memories",
                        "mimeType": "application/json",
                    },
                ]
            },
        )

    return MCPResponse(
        id=request.id,
        error={
            "code": -32601,
            "message": f"method not found: {request.method}",
        },
    )


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    project_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    from open_graph_core.ids import uuid7

    from app.idempotency import check_idempotency, store_idempotency
    from app.memory_types import validate_typed_content

    if name == "memory_observe":
        idempotency_key = arguments.get("idempotency_key")
        if idempotency_key:
            existing_id = await check_idempotency(db, idempotency_key, project_id, "episode.create")
            if existing_id:
                existing = await db.get(AgentMemoryEpisode, existing_id)
                if existing:
                    return {"episode_id": existing.id, "status": "created"}

        metadata = sanitize_input(arguments.get("metadata", {}))
        content = sanitize_input(arguments.get("observation", {}))

        episode = AgentMemoryEpisode(
            id=f"mem_{uuid7()}",
            project_id=project_id,
            domain="engineering",
            type="custom",
            title=arguments.get("kind", "observation"),
            goal="MCP observation",
            problem_signature=arguments.get("kind", "observation"),
            metadata_=metadata,
            content=content,
            confidence=0.5,
            version=1,
            status="open",
        )
        db.add(episode)

        if idempotency_key:
            await store_idempotency(
                db,
                idempotency_key,
                project_id,
                "episode.create",
                episode.id,
                {"id": episode.id, "type": episode.type},
            )

        await db.commit()
        return {"episode_id": episode.id, "status": "created"}

    if name == "memory_commit":
        validate_typed_content(arguments["type"], arguments["content"])
        content = sanitize_input(arguments["content"])
        metadata = sanitize_input(arguments.get("metadata", {}))

        idempotency_key = arguments.get("idempotency_key")
        if idempotency_key:
            existing_id = await check_idempotency(db, idempotency_key, project_id, "episode.create")
            if existing_id:
                existing = await db.get(AgentMemoryEpisode, existing_id)
                if existing:
                    return {"episode_id": existing.id, "status": "created"}

        episode = AgentMemoryEpisode(
            id=f"mem_{uuid7()}",
            project_id=project_id,
            domain="custom",
            type=arguments["type"],
            title=f"MCP commit: {arguments['type']}",
            goal="MCP committed memory",
            problem_signature=arguments["type"],
            metadata_=metadata,
            content=content,
            confidence=arguments.get("confidence", 0.5),
            version=1,
            status="open",
        )
        db.add(episode)

        if idempotency_key:
            await store_idempotency(
                db,
                idempotency_key,
                project_id,
                "episode.create",
                episode.id,
                {"id": episode.id, "type": episode.type},
            )

        await db.commit()
        return {"episode_id": episode.id, "status": "created"}

    if name == "memory_recall":
        query = select(AgentMemoryEpisode).where(AgentMemoryEpisode.project_id == project_id)
        limit = arguments.get("limit", 10)
        episodes = list(await db.scalars(query.limit(limit)))
        return {
            "memories": [
                {
                    "id": ep.id,
                    "type": ep.type,
                    "title": ep.title,
                    "content": ep.content,
                    "confidence": ep.confidence,
                    "status": ep.status,
                }
                for ep in episodes
            ]
        }

    if name == "memory_inspect":
        memory_id = arguments.get("memory_id")
        ep_obj = await db.get(AgentMemoryEpisode, memory_id)
        if not ep_obj or str(ep_obj.project_id) != project_id:
            return {"error": "memory not found"}
        return {
            "id": ep_obj.id,
            "type": ep_obj.type,
            "title": ep_obj.title,
            "content": ep_obj.content,
            "confidence": ep_obj.confidence,
            "status": ep_obj.status,
            "version": ep_obj.version,
        }

    return {"error": f"unknown tool: {name}"}


@router.post("")
async def mcp_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_session),  # noqa: B008
    mcp_session_id: str | None = Header(None, alias=MCP_SESSION_HEADER),
    x_api_key: str = Header(...),
    x_project_id: str = Header(...),
) -> Response:
    await _authenticate(db, x_api_key, x_project_id)

    body = await request.json()
    mcp_request = MCPRequest(**body)

    if not mcp_session_id:
        mcp_session_id = str(uuid4())

    response = await handle_mcp_request(mcp_request, x_project_id, db)

    return Response(
        content=response.model_dump_json(),
        media_type="application/json",
        headers={MCP_SESSION_HEADER: mcp_session_id},
    )
