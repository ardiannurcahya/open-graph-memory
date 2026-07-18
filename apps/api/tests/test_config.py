import pytest
from app.config import Settings
from open_graph_core.ids import new_id
from pydantic import ValidationError

PRODUCTION_URLS = {
    "openai_base_url": "https://default.example/v1",
    "openai_graph_extractor_base_url": "https://extractor.example/v1",
}


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
            **PRODUCTION_URLS,
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
        **PRODUCTION_URLS,
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
            openai_base_url="https://default.example/v1",
            openai_graph_extractor_base_url="http://localhost:8000/v1",
        )


def test_graph_extractor_base_url_can_be_split() -> None:
    settings = Settings(
        openai_base_url="https://default.example/v1",
        openai_graph_extractor_base_url="https://extractor.example/v1",
    )
    assert settings.graph_extractor_base_url == "https://extractor.example/v1"


def test_vector_embedding_and_chat_settings_are_removed() -> None:
    obsolete = {
        "embedding_provider",
        "chat_provider",
        "embedding_model",
        "chat_model",
        "openai_embedding_base_url",
        "openai_chat_base_url",
        "embedding_dimensions",
        "qdrant_url",
        "qdrant_api_key",
        "qdrant_collection",
        "retrieval_fusion",
        "retrieval_rrf_k",
        "retrieval_vector_weight",
        "retrieval_graph_weight",
    }
    assert obsolete.isdisjoint(Settings.model_fields)


def test_graph_extractor_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="graph settings"):
        Settings(graph_extractor_timeout_seconds=0)


def test_graph_extractor_parallelism_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="graph settings"):
        Settings(graph_extractor_parallelism=0)


def test_nlp_graph_extractor_requires_no_openai_key() -> None:
    settings = Settings(graph_extractor_provider="nlp", openai_api_key="")

    assert settings.graph_extractor_provider == "nlp"


@pytest.mark.parametrize("pdf_parser", ["pypdf", "liteparse"])
def test_pdf_parser_backends_are_explicit(pdf_parser: str) -> None:
    assert Settings(pdf_parser=pdf_parser).pdf_parser == pdf_parser


def test_unknown_pdf_parser_is_rejected() -> None:
    with pytest.raises(ValidationError, match="PDF parser"):
        Settings(pdf_parser="automatic")


@pytest.mark.parametrize("ocr_mode", ["auto", "always", "disabled"])
def test_liteparse_ocr_modes_are_bounded(ocr_mode: str) -> None:
    assert Settings(liteparse_ocr_mode=ocr_mode).liteparse_ocr_mode == ocr_mode


def test_invalid_liteparse_settings_are_rejected() -> None:
    with pytest.raises(ValidationError, match="OCR mode"):
        Settings(liteparse_ocr_mode="sometimes")
    with pytest.raises(ValidationError, match="page limit"):
        Settings(liteparse_max_pages=0)
    with pytest.raises(ValidationError, match="image mode"):
        Settings(liteparse_image_mode="placeholder")
