"""Request and response schemas for the agent memory API."""

from typing import Literal

from pydantic import BaseModel, Field

Domain = Literal["engineering", "trading", "research", "operations", "custom"]


MemoryType = Literal[
    "bugfix",
    "decision",
    "preference",
    "procedure",
    "research",
    "trading",
    "learning",
    "fact",
    "custom",
]


EpisodeStatus = Literal["open", "active", "degraded", "superseded", "rejected", "archived"]


OutcomeStatus = Literal["success", "failed", "partial", "cancelled"]


VerifierKind = Literal["ci", "runtime", "test", "build", "self_report", "custom"]


class EvidenceInput(BaseModel):
    reference: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class EpisodeInput(BaseModel):
    domain: Domain
    type: MemoryType = "custom"
    title: str = Field(min_length=1, max_length=255)
    goal: str = Field(min_length=1)
    problem_signature: str = Field(min_length=1, max_length=512)
    scope: dict[str, object] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    content: dict[str, object] | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: list[EvidenceInput] = Field(default_factory=list)
    idempotency_key: str | None = Field(default=None, max_length=255)


class AttemptInput(BaseModel):
    hypothesis: str = Field(min_length=1)
    actions: list[object] = Field(default_factory=list)
    result: Literal["success", "failed", "partial"]
    notes: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class VerifierInput(BaseModel):
    kind: VerifierKind
    name: str = Field(min_length=1, max_length=255)
    status: str = Field(min_length=1, max_length=32)
    command: str | None = None
    artifact_uri: str | None = None
    metrics: dict[str, object] = Field(default_factory=dict)


class OutcomeInput(BaseModel):
    status: OutcomeStatus
    summary: str = Field(min_length=1)
    lesson: str | None = None
    verifiers: list[VerifierInput] = Field(default_factory=list)
    metrics: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    pattern_key: str | None = Field(default=None, max_length=255)


class FeedbackInput(BaseModel):
    score: int = Field(ge=-1, le=1)


class ConfidenceFeedbackInput(BaseModel):
    kind: Literal["confirm", "reject", "correct", "supersede", "merge", "stale", "verified"]
    content: dict[str, object] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    target_id: str | None = None


class SupersedeInput(BaseModel):
    superseding_episode_id: str


class PatternSupersedeInput(BaseModel):
    superseding_pattern_key: str = Field(min_length=1, max_length=255)


class AttemptView(AttemptInput):
    id: str
    sequence: int


class EpisodeView(BaseModel):
    id: str
    project_id: str
    domain: Domain
    type: str
    title: str
    goal: str
    problem_signature: str
    scope: dict[str, object]
    tags: list[str]
    metadata: dict[str, object]
    content: dict[str, object] | None
    confidence: float
    version: int
    root_id: str | None
    status: EpisodeStatus
    feedback_score: int
    superseded_by_id: str | None
    attempts: list[AttemptView] = Field(default_factory=list)


class PatternView(BaseModel):
    pattern_key: str
    verified_outcomes: int
    weighted_successes: float
    weighted_total: float
    confidence: float
    promoted: bool


class OutcomeView(BaseModel):
    id: str
    status: OutcomeStatus
    pattern: PatternView


class SearchResult(BaseModel):
    episode: EpisodeView
    pattern: PatternView | None
    recommended_actions: list[object]
    lesson: str | None
    scope_match: bool


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class MemoryGraphNode(BaseModel):
    id: str
    type: Literal["episode", "attempt", "outcome", "pattern", "verifier", "evidence"]
    label: str
    status: str | None = None
    domain: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class MemoryGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: Literal[
        "has_attempt", "has_outcome", "matches_pattern", "verified_by", "has_evidence", "supersedes"
    ]


class MemoryGraphView(BaseModel):
    nodes: list[MemoryGraphNode]
    edges: list[MemoryGraphEdge]
    stats: dict[str, int]
