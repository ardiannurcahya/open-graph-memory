from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://opengraphrag:opengraphrag@postgres:5432/opengraphrag"
    redis_url: str = "redis://redis:6379/0"
    qdrant_url: str = "http://qdrant:6333"
    neo4j_url: str = "http://neo4j:7474"
    neo4j_auth: SecretStr = SecretStr("neo4j/change-me-now")
    s3_endpoint_url: str = "http://rustfs:9000"
    s3_bucket: str = "opengraphrag"
    s3_access_key: str = "opengraphrag"
    s3_secret_key: SecretStr = SecretStr("change-me-now")
    admin_api_key: SecretStr = SecretStr("change-me-now")
    readiness_timeout_seconds: float = 3.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
