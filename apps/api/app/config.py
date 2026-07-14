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
    s3_endpoint_url: str = "http://rustfs:9000"
    s3_access_key: str = "opengraphrag"
    s3_secret_key: SecretStr = SecretStr("change-me-object-secret")
    s3_bucket: str = "opengraphrag"
    s3_region: str = "us-east-1"
    s3_force_path_style: bool = True
    neo4j_url: str = "http://neo4j:7474"
    neo4j_auth: SecretStr = SecretStr("neo4j/change-me-now")
    readiness_timeout_seconds: float = 2
    admin_api_key: SecretStr = SecretStr("change-me-admin-key")
    upload_max_bytes: int = 25 * 1024 * 1024
    upload_spool_max_bytes: int = 1024 * 1024
    outbox_poll_seconds: float = 1
    embedding_provider: str = "deterministic"
    chat_provider: str = "deterministic"
    graph_extractor_provider: str = "deterministic"
    embedding_model: str = "deterministic-embedding-v1"
    chat_model: str = "deterministic-chat-v1"
    graph_extractor_model: str = "deterministic-graph-v1"
    graph_extractor_version: str = "graph-extractor-v1"
    graph_extractor_prompt_version: str = "graph-v1"
    graph_extractor_timeout_seconds: float = 300
    graph_extractor_parallelism: int = 1
    provider_version: str = "v1"
    embedding_dimensions: int = 64
    openai_base_url: str = "https://api.openai.com/v1"
    openai_embedding_base_url: str | None = None
    openai_chat_base_url: str | None = None
    openai_graph_extractor_base_url: str | None = None
    openai_api_key: SecretStr = SecretStr("")
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: SecretStr = SecretStr("")
    qdrant_collection: str = "chunks"
    retrieval_fusion: str = "rrf"
    retrieval_rrf_k: int = 60
    retrieval_vector_weight: float = 0.5
    retrieval_graph_weight: float = 0.5
    retrieval_graph_max_depth: int = 2
    retrieval_graph_seed_limit: int = 8
    retrieval_graph_fanout: int = 10
    retrieval_graph_timeout_ms: int = 2_000

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        if self.upload_max_bytes < 1 or self.upload_spool_max_bytes < 1:
            raise ValueError("upload limits must be positive")
        valid = {"deterministic", "openai"}
        if {self.embedding_provider, self.chat_provider, self.graph_extractor_provider} - valid:
            raise ValueError("providers must be deterministic or openai")
        if self.embedding_dimensions < 1 or self.outbox_poll_seconds <= 0:
            raise ValueError("dimensions and outbox polling interval must be positive")
        if self.retrieval_fusion not in {"rrf", "weighted"}:
            raise ValueError("RETRIEVAL_FUSION must be rrf or weighted")
        if self.retrieval_rrf_k < 1 or self.retrieval_graph_max_depth not in {1, 2}:
            raise ValueError("retrieval RRF and graph depth limits are invalid")
        if self.retrieval_graph_seed_limit < 1 or self.retrieval_graph_fanout < 1:
            raise ValueError("graph seed and fanout limits must be positive")
        if (
            self.retrieval_graph_timeout_ms < 1
            or self.graph_extractor_timeout_seconds < 1
            or self.graph_extractor_parallelism < 1
        ):
            raise ValueError("graph settings must be positive")
        if (
            "openai" in {self.embedding_provider, self.chat_provider, self.graph_extractor_provider}
            and not self.openai_api_key.get_secret_value()
        ):
            raise ValueError("OPENAI_API_KEY is required for OpenAI providers")
        if self.app_env.lower() not in {"production", "prod"}:
            return self
        if self.graph_extractor_provider != "openai":
            raise ValueError("GRAPH_EXTRACTOR_PROVIDER must be openai in production")
        provider_urls = {
            "OPENAI_EMBEDDING_BASE_URL": self.embedding_base_url,
            "OPENAI_CHAT_BASE_URL": self.chat_base_url,
            "OPENAI_GRAPH_EXTRACTOR_BASE_URL": self.graph_extractor_base_url,
        }
        for name, value in provider_urls.items():
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
    def embedding_base_url(self) -> str:
        return self.openai_embedding_base_url or self.openai_base_url

    @property
    def chat_base_url(self) -> str:
        return self.openai_chat_base_url or self.openai_base_url

    @property
    def graph_extractor_base_url(self) -> str:
        return self.openai_graph_extractor_base_url or self.openai_base_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
