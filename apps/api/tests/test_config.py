import pytest
from app.config import Settings
from open_graph_core.ids import new_id
from pydantic import ValidationError


def test_prefixed_uuid7() -> None:
    value = new_id("ds")
    assert value.startswith("ds_") and value.split("_", 1)[1][14] == "7"


def test_unknown_prefix() -> None:
    with pytest.raises(ValueError):
        new_id("user")


def test_production_rejects_placeholder_credentials() -> None:
    with pytest.raises(ValidationError, match="ADMIN_API_KEY"):
        Settings(
            app_env="production",
            admin_api_key="change-me-admin-key",
            s3_secret_key="a-secure-object-secret",
            neo4j_auth="neo4j/a-secure-neo4j-password",
            database_url="postgresql+asyncpg://user:a-secure-db-password@postgres/db",
            graph_extractor_provider="openai",
            graph_extractor_model="gpt-4o-mini",
            openai_api_key="a-secure-openai-api-key",
        )


def test_production_accepts_consistent_credentials() -> None:
    settings = Settings(
        app_env="production",
        admin_api_key="a-secure-admin-api-key",
        s3_secret_key="a-secure-object-secret",
        neo4j_auth="neo4j/a-secure-neo4j-password",
        database_url="postgresql+asyncpg://user:a-secure-db-password@postgres/db",
        graph_extractor_provider="openai",
        graph_extractor_model="gpt-4o-mini",
        openai_api_key="a-secure-openai-api-key",
    )
    assert settings.app_env == "production"


def test_production_requires_openai_graph_extractor() -> None:
    with pytest.raises(ValidationError, match="GRAPH_EXTRACTOR_PROVIDER"):
        Settings(
            app_env="production",
            admin_api_key="a-secure-admin-api-key",
            s3_secret_key="a-secure-object-secret",
            neo4j_auth="neo4j/a-secure-neo4j-password",
            database_url="postgresql+asyncpg://user:a-secure-db-password@postgres/db",
            graph_extractor_provider="deterministic",
        )


def test_production_rejects_insecure_graph_endpoint() -> None:
    with pytest.raises(ValidationError, match="OPENAI_GRAPH_EXTRACTOR_BASE_URL"):
        Settings(
            app_env="production",
            admin_api_key="a-secure-admin-api-key",
            s3_secret_key="a-secure-object-secret",
            neo4j_auth="neo4j/a-secure-neo4j-password",
            database_url="postgresql+asyncpg://user:a-secure-db-password@postgres/db",
            graph_extractor_provider="openai",
            graph_extractor_model="gpt-4o-mini",
            openai_api_key="a-secure-openai-api-key",
            openai_graph_extractor_base_url="http://localhost:8000/v1",
        )


def test_provider_base_urls_can_be_split() -> None:
    settings = Settings(
        openai_base_url="https://default.example/v1",
        openai_embedding_base_url="https://embeddings.example/v1",
        openai_chat_base_url="https://chat.example/v1",
        openai_graph_extractor_base_url="https://extractor.example/v1",
    )
    assert settings.embedding_base_url == "https://embeddings.example/v1"
    assert settings.chat_base_url == "https://chat.example/v1"
    assert settings.graph_extractor_base_url == "https://extractor.example/v1"
