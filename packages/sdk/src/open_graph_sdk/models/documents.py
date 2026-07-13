
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Document(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    project_id: str
    dataset_id: str
    filename: str
    mime_type: str
    size_bytes: int
    content_hash: str
    object_key: str
    status: str
    error_message: str | None = None
    duplicate: bool = False
    created_at: datetime
    updated_at: datetime
