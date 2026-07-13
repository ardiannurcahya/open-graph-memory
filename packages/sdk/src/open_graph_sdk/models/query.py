from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from open_graph_sdk.models.common import FusionMethod, QueryMode


class Citation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    index: int
    chunk_id: str
    document_id: str
    score: float
    text: str


class Usage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class RetrievalTrace(BaseModel):
    model_config = ConfigDict(extra="allow")

    trace_id: str | None = None
    mode: str | None = None
    latency_ms: float | None = None
    chunk_ids: list[str] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)


class QueryRequest(BaseModel):
    dataset_id: str
    query: str
    mode: QueryMode = QueryMode.VECTOR_ONLY
    top_k: int = 5
    graph_depth: int | None = None
    graph_fanout: int | None = None
    graph_timeout_ms: int | None = None
    fusion: FusionMethod | None = None
    memory_user_id: str | None = None
    memory_agent_id: str | None = None
    memory_session_id: str | None = None
    memory_top_k: int = 0


class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answer: str
    citations: list[Citation]
    retrieval_trace: RetrievalTrace | dict[str, Any]
    usage: Usage | dict[str, Any]
