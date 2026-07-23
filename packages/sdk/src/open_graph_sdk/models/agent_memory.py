from typing import Any, Literal

from pydantic import BaseModel, Field

Domain = Literal["engineering", "trading", "research", "operations", "custom"]
EpisodeStatus = Literal["open", "active", "degraded", "superseded", "rejected"]
OutcomeStatus = Literal["success", "failed", "partial", "cancelled"]


class AgentMemoryEvidence(BaseModel):
    reference: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentMemoryAttempt(BaseModel):
    id: str
    sequence: int
    hypothesis: str
    actions: list[Any] = Field(default_factory=list)
    result: Literal["success", "failed", "partial"]
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentMemoryEpisode(BaseModel):
    id: str
    project_id: str
    domain: Domain
    title: str
    goal: str
    problem_signature: str
    scope: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: EpisodeStatus
    feedback_score: int
    superseded_by_id: str | None = None
    attempts: list[AgentMemoryAttempt] = Field(default_factory=list)


class AgentMemoryVerifier(BaseModel):
    kind: Literal["ci", "runtime", "test", "build", "self_report", "custom"]
    name: str
    status: str
    command: str | None = None
    artifact_uri: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class AgentMemoryPattern(BaseModel):
    pattern_key: str
    verified_outcomes: int
    weighted_successes: float
    weighted_total: float
    confidence: float
    promoted: bool


class AgentMemoryOutcome(BaseModel):
    id: str
    status: OutcomeStatus
    pattern: AgentMemoryPattern


class AgentMemorySearchResult(BaseModel):
    episode: AgentMemoryEpisode
    pattern: AgentMemoryPattern | None = None
    recommended_actions: list[Any] = Field(default_factory=list)
    lesson: str | None = None
    scope_match: bool


class AgentMemorySearchResponse(BaseModel):
    query: str
    results: list[AgentMemorySearchResult]
