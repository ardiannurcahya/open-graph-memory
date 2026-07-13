from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryScope = Literal["user", "agent", "session"]
MessageRole = Literal["system", "user", "assistant", "tool"]


class MemoryUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    project_id: str
    external_id: str
    display_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryAgent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    project_id: str
    name: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySession(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    project_id: str
    user_id: str
    agent_id: str
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    archived_at: datetime | None = None


class MemoryMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    project_id: str
    session_id: str
    role: MessageRole
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MemoryFact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    project_id: str
    user_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    scope: MemoryScope
    subject: str
    predicate: str
    value: str
    content: str
    confidence: int
    status: str
    supersedes_id: str | None = None
    source_message_id: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    valid_from: datetime
    valid_until: datetime | None = None
    deleted_at: datetime | None = None


class MemorySearchHit(MemoryFact):
    score: float
    matched_terms: list[str] = Field(default_factory=list)


class MemoryMessageBatch(BaseModel):
    messages: list[MemoryMessage]
    facts: list[MemoryFact]
