import json
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ProjectContext, require_project
from app.config import get_settings
from app.dependencies import get_session
from app.graph_store import GraphStore
from app.models import Chunk, Dataset, MemoryFact, MemoryFactStatus, QueryLog
from app.providers import ChatProvider, ChatResult, DeterministicProvider, EmbeddingProvider, Usage
from app.retrieval import GraphEvidence, bounded_graph_search, fuse_hits
from app.runtime import get_chat_provider, get_embedding_provider, get_graph_store, get_vector_store
from app.vector_store import VectorHit, VectorStore

router = APIRouter(prefix="/v1", tags=["query"])


class QueryRequest(BaseModel):
    dataset_id: str
    query: str = Field(min_length=1, max_length=10_000)
    mode: Literal["vector_only", "graph_only", "hybrid"] = "vector_only"
    top_k: int = Field(default=5, ge=1, le=50)
    graph_depth: int | None = Field(default=None, ge=1, le=2)
    graph_fanout: int | None = Field(default=None, ge=1, le=100)
    graph_timeout_ms: int | None = Field(default=None, ge=1, le=10_000)
    fusion: Literal["rrf", "weighted"] | None = None
    memory_user_id: str | None = None
    memory_agent_id: str | None = None
    memory_session_id: str | None = None
    memory_top_k: int = Field(default=0, ge=0, le=20)


class Citation(BaseModel):
    index: int
    chunk_id: str
    document_id: str
    score: float
    text: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    retrieval_trace: dict[str, object]
    usage: dict[str, int | float]


def build_context(hits: list[VectorHit], memory_facts: list[MemoryFact] | None = None) -> str:
    evidence = "\n\n".join(
        f"[{i}] chunk_id={hit.id} document_id={hit.payload.get('document_id')}\n"
        f"{hit.payload.get('text', '')}"
        for i, hit in enumerate(hits, 1)
    )
    memory = ""
    if memory_facts:
        memory = (
            "\n\nMemory facts for personalization only; do not cite them as evidence:\n"
            + "\n".join(
                f"- {fact.content} (scope={fact.scope}, id={fact.id})" for fact in memory_facts
            )
        )
    return (
        "Answer only from the evidence. Cite every supported factual claim using exact markers "
        "like [1]. Use only evidence indexes listed below. Do not use parentheses, Unicode "
        "brackets, source names, or indexes outside that range. If evidence cannot answer the "
        "question, reply exactly: I cannot answer from the supplied evidence.\n\nEvidence:\n"
        + evidence
        + memory
    )


async def safe_provider_call[T](operation: Callable[[], Awaitable[T]]) -> T:
    try:
        return await operation()
    except httpx.TimeoutException:
        raise HTTPException(504, "provider request timed out") from None
    except httpx.HTTPError:
        raise HTTPException(502, "provider request failed") from None


def citation_indexes(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"\[(\d+)]", text)}


def citations_are_valid(text: str, hit_count: int) -> bool:
    referenced = citation_indexes(text)
    refused = "cannot answer from the supplied evidence" in text.lower()
    return not (
        referenced - set(range(1, hit_count + 1))
        or (not refused and (hit_count == 0 or not referenced))
    )


async def chat_with_citation_repair(
    chat: ChatProvider,
    messages: list[dict[str, str]],
    model: str,
    hit_count: int,
) -> tuple[ChatResult, set[int]]:
    first = await safe_provider_call(lambda: chat.chat(messages, model))
    if citations_are_valid(first.text, hit_count):
        return first, citation_indexes(first.text)
    valid_markers = ", ".join(f"[{index}]" for index in range(1, hit_count + 1)) or "none"
    repaired = await safe_provider_call(
        lambda: chat.chat(
            [
                *messages,
                {"role": "assistant", "content": first.text},
                {
                    "role": "user",
                    "content": (
                        "Repair citation formatting only and return the complete answer. "
                        f"Valid citation markers are: {valid_markers}. Use only those exact "
                        "markers, do not add claims, and cite every supported factual claim. "
                        "If evidence is insufficient, reply exactly: "
                        "I cannot answer from the supplied evidence."
                    ),
                },
            ],
            model,
        )
    )
    if not citations_are_valid(repaired.text, hit_count):
        raise HTTPException(502, "provider returned invalid or missing citations")
    return (
        ChatResult(
            repaired.text,
            Usage(
                prompt_tokens=first.usage.prompt_tokens + repaired.usage.prompt_tokens,
                completion_tokens=first.usage.completion_tokens + repaired.usage.completion_tokens,
                estimated_cost_usd=(
                    first.usage.estimated_cost_usd + repaired.usage.estimated_cost_usd
                ),
            ),
        ),
        citation_indexes(repaired.text),
    )


def memory_terms(text: str) -> set[str]:
    return {token.lower() for token in DeterministicProvider._tokens(text) if len(token) > 2}


async def memory_hits(db: AsyncSession, project_id: object, body: QueryRequest) -> list[MemoryFact]:
    if body.memory_top_k <= 0:
        return []
    stmt = select(MemoryFact).where(
        MemoryFact.project_id == project_id,
        MemoryFact.status == MemoryFactStatus.ACTIVE,
    )
    filters = []
    if body.memory_user_id:
        filters.append(MemoryFact.user_id == body.memory_user_id)
    if body.memory_agent_id:
        filters.append(MemoryFact.agent_id == body.memory_agent_id)
    if body.memory_session_id:
        filters.append(MemoryFact.session_id == body.memory_session_id)
    if filters:
        stmt = stmt.where(or_(*filters))
    rows = list(await db.scalars(stmt.order_by(MemoryFact.created_at.desc()).limit(200)))
    terms = memory_terms(body.query)
    scored = [
        (len([term for term in terms if term in fact.content.lower()]), fact) for fact in rows
    ]
    return [
        fact for score, fact in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0
    ][: body.memory_top_k]


def entity_candidates(text: str) -> list[str]:
    candidates = {token.lower() for token in DeterministicProvider._tokens(text) if len(token) > 2}
    return sorted(candidates)[:8]


async def authoritative_hits(
    db: AsyncSession, project_id: object, dataset_id: str, raw: list[VectorHit]
) -> list[VectorHit]:
    if not raw:
        return []
    raw_ids = {hit.id for hit in raw}
    chunks = (
        await db.scalars(
            select(Chunk).where(
                Chunk.id.in_(raw_ids),
                Chunk.project_id == project_id,
                Chunk.dataset_id == dataset_id,
            )
        )
    ).all()
    by_id = {chunk.id: chunk for chunk in chunks}
    return [
        VectorHit(
            hit.id,
            hit.score,
            {"document_id": by_id[hit.id].document_id, "text": by_id[hit.id].text},
        )
        for hit in raw
        if hit.id in by_id
    ]


@router.post("/query", response_model=QueryResponse)
async def query(
    body: QueryRequest,
    context: Annotated[ProjectContext, Depends(require_project)],
    db: Annotated[AsyncSession, Depends(get_session)],
    embeddings: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    chat: Annotated[ChatProvider, Depends(get_chat_provider)],
    vectors: Annotated[VectorStore, Depends(get_vector_store)],
    graph: Annotated[GraphStore, Depends(get_graph_store)],
) -> QueryResponse:
    return await execute_query(body, context, db, embeddings, chat, vectors, graph)


async def execute_query(
    body: QueryRequest,
    context: ProjectContext,
    db: AsyncSession,
    embeddings: EmbeddingProvider,
    chat: ChatProvider,
    vectors: VectorStore,
    graph: GraphStore,
) -> QueryResponse:
    dataset = await db.scalar(
        select(Dataset).where(
            Dataset.id == body.dataset_id, Dataset.project_id == context.project_id
        )
    )
    if dataset is None:
        raise HTTPException(404, "dataset not found")
    started, trace_id, settings = time.perf_counter(), str(uuid4()), get_settings()
    vector = (
        await safe_provider_call(lambda: embeddings.embed([body.query], settings.embedding_model))
    )[0]
    vector_raw = await vectors.search(
        vector, str(context.project_id), body.dataset_id, max(body.top_k, 50)
    )
    vector_hits = await authoritative_hits(db, context.project_id, body.dataset_id, vector_raw)
    graph_evidence: list[GraphEvidence] = []
    graph_state: dict[str, object] = {"status": "not_requested"}
    graph_hits: list[VectorHit] = []
    if body.mode != "vector_only":
        graph_evidence, graph_state = await bounded_graph_search(
            graph,
            body.graph_timeout_ms or settings.retrieval_graph_timeout_ms,
            str(context.project_id),
            body.dataset_id,
            [hit.id for hit in vector_hits],
            entity_candidates(body.query),
            body.graph_depth or settings.retrieval_graph_max_depth,
            body.graph_fanout or settings.retrieval_graph_fanout,
            settings.retrieval_graph_seed_limit,
        )
        scores = {item.chunk_id: item.score for item in graph_evidence}
        graph_hits = await authoritative_hits(
            db,
            context.project_id,
            body.dataset_id,
            [VectorHit(chunk_id, score, {}) for chunk_id, score in scores.items()],
        )
    fusion: list[dict[str, object]]
    if body.mode == "vector_only":
        hits, fusion = vector_hits, []
    elif body.mode == "graph_only":
        hits, fusion = (
            (vector_hits, []) if graph_state.get("status") == "fallback" else (graph_hits, [])
        )
    else:
        hits, fusion = fuse_hits(
            vector_hits,
            graph_hits,
            body.fusion or settings.retrieval_fusion,
            settings.retrieval_rrf_k,
            settings.retrieval_vector_weight,
            settings.retrieval_graph_weight,
        )
    hits = hits[: body.top_k]
    memories = await memory_hits(db, context.project_id, body)
    result, referenced = await chat_with_citation_repair(
        chat,
        [
            {"role": "system", "content": build_context(hits, memories)},
            {"role": "user", "content": body.query},
        ],
        settings.chat_model,
        len(hits),
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    trace: dict[str, object] = {
        "trace_id": trace_id,
        "mode": body.mode,
        "channel_candidates": {
            "vector": [{"chunk_id": hit.id, "score": hit.score} for hit in vector_hits],
            "graph": [{"chunk_id": hit.id, "score": hit.score} for hit in graph_hits],
        },
        "fusion": fusion,
        "graph": {
            **graph_state,
            "paths": [
                {
                    "chunk_id": item.chunk_id,
                    "path": list(item.path),
                    "relation_ids": list(item.relation_ids),
                    "evidence_chunk_ids": list(item.evidence_chunk_ids),
                }
                for item in graph_evidence
            ],
        },
        "chunk_ids": [hit.id for hit in hits],
        "scores": [hit.score for hit in hits],
        "memory": {
            "fact_ids": [fact.id for fact in memories],
            "scopes": [fact.scope for fact in memories],
            "source_message_ids": [fact.source_message_id for fact in memories],
        },
        "latency_ms": latency_ms,
    }
    usage: dict[str, int | float] = {
        "prompt_tokens": result.usage.prompt_tokens,
        "completion_tokens": result.usage.completion_tokens,
        "total_tokens": result.usage.prompt_tokens + result.usage.completion_tokens,
        "estimated_cost_usd": result.usage.estimated_cost_usd,
    }
    db.add(
        QueryLog(
            id=str(uuid4()),
            trace_id=trace_id,
            project_id=context.project_id,
            dataset_id=body.dataset_id,
            query=body.query,
            answer=result.text,
            status="succeeded",
            provider=chat.name,
            model=settings.chat_model,
            provider_version=settings.provider_version,
            retrieval_trace=trace,
            usage=usage,
            latency_ms=int(latency_ms),
            error_code=None,
            error_message=None,
        )
    )
    await db.commit()
    return QueryResponse(
        answer=result.text,
        citations=[
            Citation(
                index=i,
                chunk_id=hit.id,
                document_id=str(hit.payload["document_id"]),
                score=hit.score,
                text=str(hit.payload["text"]),
            )
            for i, hit in enumerate(hits, 1)
            if i in referenced
        ],
        retrieval_trace=trace,
        usage=usage,
    )


def stream_event(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def answer_segments(answer: str) -> list[str]:
    return [match.group(0) for match in re.finditer(r"\S+\s*", answer)] or [""]


@router.post("/query/stream")
async def query_stream(
    body: QueryRequest,
    context: Annotated[ProjectContext, Depends(require_project)],
    db: Annotated[AsyncSession, Depends(get_session)],
    embeddings: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    chat: Annotated[ChatProvider, Depends(get_chat_provider)],
    vectors: Annotated[VectorStore, Depends(get_vector_store)],
    graph: Annotated[GraphStore, Depends(get_graph_store)],
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        try:
            yield stream_event("status", {"stage": "retrieving"})
            dataset = await db.scalar(
                select(Dataset).where(
                    Dataset.id == body.dataset_id, Dataset.project_id == context.project_id
                )
            )
            if dataset is None:
                raise HTTPException(404, "dataset not found")
            started, trace_id, settings = time.perf_counter(), str(uuid4()), get_settings()
            vector = (
                await safe_provider_call(
                    lambda: embeddings.embed([body.query], settings.embedding_model)
                )
            )[0]
            vector_raw = await vectors.search(
                vector, str(context.project_id), body.dataset_id, max(body.top_k, 50)
            )
            vector_hits = await authoritative_hits(
                db, context.project_id, body.dataset_id, vector_raw
            )
            graph_evidence: list[GraphEvidence] = []
            graph_state: dict[str, object] = {"status": "not_requested"}
            graph_hits: list[VectorHit] = []
            if body.mode != "vector_only":
                graph_evidence, graph_state = await bounded_graph_search(
                    graph,
                    body.graph_timeout_ms or settings.retrieval_graph_timeout_ms,
                    str(context.project_id),
                    body.dataset_id,
                    [hit.id for hit in vector_hits],
                    entity_candidates(body.query),
                    body.graph_depth or settings.retrieval_graph_max_depth,
                    body.graph_fanout or settings.retrieval_graph_fanout,
                    settings.retrieval_graph_seed_limit,
                )
                scores = {item.chunk_id: item.score for item in graph_evidence}
                graph_hits = await authoritative_hits(
                    db,
                    context.project_id,
                    body.dataset_id,
                    [VectorHit(chunk_id, score, {}) for chunk_id, score in scores.items()],
                )
            fusion: list[dict[str, object]]
            if body.mode == "vector_only":
                hits, fusion = vector_hits, []
            elif body.mode == "graph_only":
                hits, fusion = (
                    (vector_hits, [])
                    if graph_state.get("status") == "fallback"
                    else (graph_hits, [])
                )
            else:
                hits, fusion = fuse_hits(
                    vector_hits,
                    graph_hits,
                    body.fusion or settings.retrieval_fusion,
                    settings.retrieval_rrf_k,
                    settings.retrieval_vector_weight,
                    settings.retrieval_graph_weight,
                )
            hits = hits[: body.top_k]
            memories = await memory_hits(db, context.project_id, body)
            messages = [
                {"role": "system", "content": build_context(hits, memories)},
                {"role": "user", "content": body.query},
            ]
            yield stream_event("status", {"stage": "generating"})
            answer = ""
            async for segment in chat.stream_chat(messages, settings.chat_model):
                answer += segment
                yield stream_event("token", {"text": segment})
            referenced = citation_indexes(answer)
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            trace: dict[str, object] = {
                "trace_id": trace_id,
                "mode": body.mode,
                "channel_candidates": {
                    "vector": [{"chunk_id": hit.id, "score": hit.score} for hit in vector_hits],
                    "graph": [{"chunk_id": hit.id, "score": hit.score} for hit in graph_hits],
                },
                "fusion": fusion,
                "graph": {
                    **graph_state,
                    "paths": [
                        {
                            "chunk_id": item.chunk_id,
                            "path": list(item.path),
                            "relation_ids": list(item.relation_ids),
                            "evidence_chunk_ids": list(item.evidence_chunk_ids),
                        }
                        for item in graph_evidence
                    ],
                },
                "chunk_ids": [hit.id for hit in hits],
                "scores": [hit.score for hit in hits],
                "memory": {
                    "fact_ids": [fact.id for fact in memories],
                    "scopes": [fact.scope for fact in memories],
                    "source_message_ids": [fact.source_message_id for fact in memories],
                },
                "latency_ms": latency_ms,
            }
            usage = {
                "prompt_tokens": 0,
                "completion_tokens": len(answer.split()),
                "total_tokens": len(answer.split()),
                "estimated_cost_usd": 0.0,
            }
            response = QueryResponse(
                answer=answer,
                citations=[
                    Citation(
                        index=i,
                        chunk_id=hit.id,
                        document_id=str(hit.payload["document_id"]),
                        score=hit.score,
                        text=str(hit.payload["text"]),
                    )
                    for i, hit in enumerate(hits, 1)
                    if i in referenced
                ],
                retrieval_trace=trace,
                usage=usage,
            )
            yield stream_event("complete", response.model_dump(mode="json"))
        except HTTPException as exc:
            yield stream_event("error", {"message": str(exc.detail), "status": exc.status_code})
        except Exception:
            yield stream_event("error", {"message": "query stream failed", "status": 500})

    return StreamingResponse(events(), media_type="text/event-stream")
