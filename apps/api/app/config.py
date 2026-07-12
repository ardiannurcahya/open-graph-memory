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
    qdrant_url: str = "http://qdrant:6333"
    neo4j_url: str = "http://neo4j:7474"
    neo4j_auth: SecretStr = SecretStr("neo4j/change-me-neo4j")
    s3_endpoint_url: str = "http://rustfs:9000"
    s3_access_key: str = "opengraphrag"
    s3_secret_key: SecretStr = SecretStr("change-me-s3-secret")
    s3_bucket: str = "opengraphrag"
    s3_region: str = "us-east-1"
    admin_api_key: SecretStr = SecretStr("change-me-admin-api-key")
    readiness_timeout_seconds: float = 2.0
    upload_max_bytes: int = 25 * 1024 * 1024
    upload_spool_max_bytes: int = 1024 * 1024

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        if self.upload_max_bytes < 1 or self.upload_spool_max_bytes < 1:
            raise ValueError("upload limits must be positive")
        if self.app_env.lower() not in {"production", "prod"}:
            return self

        values = {
            "ADMIN_API_KEY": self.admin_api_key.get_secret_value(),
            "S3_SECRET_KEY": self.s3_secret_key.get_secret_value(),
            "NEO4J_AUTH": self.neo4j_auth.get_secret_value(),
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
