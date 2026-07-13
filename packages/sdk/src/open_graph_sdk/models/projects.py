
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ProjectCreated(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    api_key: str
