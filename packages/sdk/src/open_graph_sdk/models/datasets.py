
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatasetCreate(BaseModel):
    name: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    metadata: dict[str, Any] | None = None


class Dataset(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    project_id: str
    name: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str
    error_message: str | None = None
