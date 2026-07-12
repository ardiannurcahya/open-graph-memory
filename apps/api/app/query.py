import re
import time
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ProjectContext, require_project
from app.config import get_settings
from app.dependencies import get_session
from app.models import Chunk, Dataset, QueryLog
from app.providers import ChatProvider, DeterministicProvider, EmbeddingProvider
from app.runtime import get_chat_provider, get_embedding_provider, get_vector_store
from app.vector_store import VectorHit, VectorStore

router = APIRouter(prefix="/v1", tags=["query"])


class QueryRequest(BaseModel):
    dataset_id: str
    query: str = Field(min_length=1, max_length=10_000)
    mode: str = "vector_only"
    top_k: int = Field(default=5, ge=1, le=50)


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


def build_context(hits: list[VectorHit]) -> str:
    evidence = "\n\n".join(
        f"[{i}] chunk_id={hit.id} document_id={hit.payload.get('document_id')}\n"
        f"{hit.payload.get('text', '')}"
        for i, hit in enumerate(hits, 1)
    )
    return "Answer only from the evidence and cite claims with [n].\n\nEvidence:\n" + evidence


@router.post("/query", response_model=QueryResponse)
async def query(
    body: QueryRequest,
    context: Annotated[ProjectContext, Depends(require_project)],
    db: Annotated[AsyncSession, Depends(get_session)],
    embeddings: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    chat: Annotated[ChatProvider, Depends(get_chat_provider)],
    vectors: Annotated[VectorStore, Depends(get_vector_store)],
) -> QueryResponse:
    if body.mode != "vector_only":
        raise HTTPException(422, "only vector_only mode is supported")
    dataset = await db.scalar(
        select(Dataset).where(
            Dataset.id == body.dataset_id, Dataset.project_id == context.project_id
        )
    )
    if dataset is None:
        raise HTTPException(404, "dataset not found")
    started = time.perf_counter()
    settings = get_settings()
    trace_id = str(uuid4())
    vector = (await embeddings.embed([body.query], settings.embedding_model))[0]
    # Retrieve a wider candidate set, then apply deterministic lexical reranking.
    # Dense hashing is deliberately inexpensive and collision-prone; reranking
    # preserves Qdrant retrieval while making exact domain vocabulary decisive.
    candidate_k = max(body.top_k, 50)
    raw_hits = await vectors.search(vector, str(context.project_id), body.dataset_id, candidate_k)
    hit_by_id = {hit.id: hit for hit in raw_hits}
    chunks = (
        await db.scalars(
            select(Chunk).where(
                Chunk.id.in_(hit_by_id),
                Chunk.project_id == context.project_id,
                Chunk.dataset_id == body.dataset_id,
            )
        )
    ).all()
    # PostgreSQL is authoritative; Qdrant payload text and scope are never trusted.
    hits = [
        VectorHit(
            chunk.id,
            hit_by_id[chunk.id].score,
            {"document_id": chunk.document_id, "text": chunk.text},
        )
        for chunk in chunks
        if chunk.id in hit_by_id
    ]
    query_terms = set(DeterministicProvider._tokens(body.query))
    stopwords = {
        "a", "an", "and", "are", "can", "do", "does", "for", "from", "how",
        "is", "of", "the", "to", "what", "where", "which",
    }
    query_terms -= stopwords

    def relevance(hit: VectorHit) -> tuple[float, float]:
        text_terms = set(DeterministicProvider._tokens(str(hit.payload.get("text", ""))))
        overlap = len(query_terms & text_terms) / max(1, len(query_terms))
        return overlap, hit.score

    hits.sort(key=relevance, reverse=True)
    hits = hits[: body.top_k]
    result = await chat.chat(
        [
            {"role": "system", "content": build_context(hits)},
            {"role": "user", "content": body.query},
        ],
        settings.chat_model,
    )
    referenced = {int(value) for value in re.findall(r"\[(\d+)]", result.text)}
    refused = "cannot answer from the supplied evidence" in result.text.lower()
    invalid_citations = referenced - set(range(1, len(hits) + 1))
    if invalid_citations or (not refused and (not hits or not referenced)):
        db.add(
            QueryLog(
                id=str(uuid4()),
                trace_id=trace_id,
                project_id=context.project_id,
                dataset_id=body.dataset_id,
                query=body.query,
                answer=None,
                status="failed",
                provider=chat.name,
                model=settings.chat_model,
                provider_version=settings.provider_version,
                retrieval_trace={
                    "chunk_ids": [hit.id for hit in hits],
                    "scores": [hit.score for hit in hits],
                    "stages": ["embed", "vector_search", "postgres_resolve", "citation_validation"],
                },
                usage={},
                latency_ms=int((time.perf_counter() - started) * 1000),
                error_code="invalid_citations",
                error_message="provider output lacked valid supplied evidence citations",
            )
        )
        await db.commit()
        raise HTTPException(502, "provider returned invalid or missing citations")
    citations = [
        Citation(
            index=i,
            chunk_id=hit.id,
            document_id=str(hit.payload.get("document_id", "")),
            score=hit.score,
            text=str(hit.payload.get("text", "")),
        )
        for i, hit in enumerate(hits, 1)
        if i in referenced
    ]
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    usage: dict[str, int | float] = {
        "prompt_tokens": result.usage.prompt_tokens,
        "completion_tokens": result.usage.completion_tokens,
        "total_tokens": result.usage.prompt_tokens + result.usage.completion_tokens,
        "estimated_cost_usd": result.usage.estimated_cost_usd,
    }
    trace: dict[str, object] = {
        "trace_id": trace_id,
        "mode": body.mode,
        "top_k": body.top_k,
        "retrieved": len(hits),
        "chunk_ids": [hit.id for hit in hits],
        "scores": [hit.score for hit in hits],
        "stages": ["embed", "vector_search", "postgres_resolve", "chat", "citation_validation"],
        "latency_ms": latency_ms,
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
        citations=citations,
        retrieval_trace=trace,
        usage=usage,
    )
