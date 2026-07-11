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
        )


def test_production_accepts_consistent_credentials() -> None:
    settings = Settings(
        app_env="production",
        admin_api_key="a-secure-admin-api-key",
        s3_secret_key="a-secure-object-secret",
        neo4j_auth="neo4j/a-secure-neo4j-password",
        database_url="postgresql+asyncpg://user:a-secure-db-password@postgres/db",
    )
    assert settings.app_env == "production"
