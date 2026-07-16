from functools import lru_cache
from urllib.parse import urlparse

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDERS = ("change-me", "changeme", "replace_me", "example", "placeholder")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = (
        "postgresql+asyncpg://opengraphrag:change-me-postgres@postgres:5432/opengraphrag"
    )
    redis_url: str = "redis://redis:6379/0"
    admin_api_key: SecretStr = SecretStr("change-me-admin-api-key")
    s3_endpoint_url: str = "http://rustfs:9000"
    s3_access_key: str = "opengraphrag"
    s3_secret_key: SecretStr = SecretStr("change-me-s3-secret")
    s3_bucket: str = "opengraphrag"
    s3_region: str = "us-east-1"
    s3_force_path_style: bool = True
    openai_base_url: str = "https://api.openai.com/v1"
    openai_graph_extractor_base_url: str = ""
    openai_api_key: SecretStr = SecretStr("")
    graph_extractor_provider: str = "deterministic"
    graph_extractor_model: str = "deterministic-graph-v1"
    graph_extractor_version: str = "graph-extractor-v1"
    graph_extractor_prompt_version: str = "graph-v1"
    graph_extractor_timeout_seconds: int = 300
    graph_extractor_parallelism: int = 1
    provider_version: str = "v1"
    neo4j_url: str = "http://neo4j:7474"
    neo4j_auth: SecretStr = SecretStr("neo4j/change-me-neo4j")
    upload_max_bytes: int = 50_000_000
    upload_spool_max_bytes: int = 1_000_000
    outbox_poll_seconds: int = 10
    indexing_stale_seconds: int = 900
    retrieval_graph_max_depth: int = 1
    retrieval_graph_seed_limit: int = 10
    retrieval_graph_fanout: int = 10
    retrieval_graph_timeout_ms: int = 1000
    readiness_timeout_seconds: int = 2

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        if self.upload_max_bytes < 1 or self.upload_spool_max_bytes < 1:
            raise ValueError("upload limits must be positive")
        if self.graph_extractor_provider not in {"deterministic", "nlp", "openai"}:
            raise ValueError("graph extractor provider must be deterministic, nlp, or openai")
        if self.outbox_poll_seconds <= 0 or self.indexing_stale_seconds <= 0:
            raise ValueError("outbox polling interval must be positive")
        if self.graph_extractor_timeout_seconds < 1 or self.graph_extractor_parallelism < 1:
            raise ValueError("graph settings must be positive")
        if self.graph_extractor_provider == "openai" and not self.openai_api_key.get_secret_value():
            raise ValueError("OPENAI_API_KEY is required for OpenAI graph extraction")
        if self.app_env.lower() not in {"production", "prod"}:
            return self
        if self.graph_extractor_provider != "openai":
            raise ValueError("GRAPH_EXTRACTOR_PROVIDER must be openai in production")
        for name, value in {
            "OPENAI_GRAPH_EXTRACTOR_BASE_URL": self.graph_extractor_base_url,
        }.items():
            if urlparse(value).scheme != "https":
                raise ValueError(f"{name} must use https in production")
        values = {
            "ADMIN_API_KEY": self.admin_api_key.get_secret_value(),
            "S3_SECRET_KEY": self.s3_secret_key.get_secret_value(),
            "NEO4J_AUTH": self.neo4j_auth.get_secret_value(),
            "OPENAI_API_KEY": self.openai_api_key.get_secret_value(),
        }
        for name, value in values.items():
            if len(value) < 16 or any(marker in value.lower() for marker in _PLACEHOLDERS):
                raise ValueError(f"{name} must be a non-placeholder production secret")
        db = urlparse(self.database_url.replace("postgresql+asyncpg", "postgresql", 1))
        if not db.password or any(marker in db.password.lower() for marker in _PLACEHOLDERS):
            raise ValueError("DATABASE_URL must contain a non-placeholder password")
        user, separator, password = values["NEO4J_AUTH"].partition("/")
        if not separator or not user or not password:
            raise ValueError("NEO4J_AUTH must be formatted as user/password")
        return self

    @property
    def graph_extractor_base_url(self) -> str:
        return self.openai_graph_extractor_base_url or self.openai_base_url

@lru_cache
def get_settings() -> Settings:
    return Settings()
