
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ClientConfig:
    base_url: str
    api_key: str
    project_id: str | None = None
    timeout: float = 30.0
    admin_key: str | None = None

    @classmethod
    def from_env(cls) -> ClientConfig:
        return cls(
            base_url=os.environ.get("OGM_BASE_URL", "http://localhost:8000"),
            api_key=os.environ.get("OGM_API_KEY", ""),
            project_id=os.environ.get("OGM_PROJECT_ID") or None,
            admin_key=os.environ.get("OGM_ADMIN_KEY") or None,
        )
