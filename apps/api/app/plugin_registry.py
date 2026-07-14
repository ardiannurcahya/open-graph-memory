"""Explicit registration and bounded construction of built-in application plugins."""

from typing import cast

from open_graph_contracts import (
    Capability,
    ChatProvider,
    EmbeddingProvider,
    Extractor,
    GraphStore,
    ObjectStore,
    PluginCapabilities,
    PluginConfig,
    PluginMetadata,
    PluginRegistry,
    PluginSpec,
    PluginVersion,
    SecretValue,
    VectorStore,
    get_registry,
)
from open_graph_core.extraction import DeterministicExtractor, OpenAICompatibleExtractor
from qdrant_client import AsyncQdrantClient

from app.graph_store import GraphStore as AppGraphStore
from app.graph_store import Neo4jGraphStore
from app.providers import (
    ChatProvider as AppChatProvider,
)
from app.providers import (
    DeterministicProvider,
    OpenAIChatProvider,
    OpenAIEmbeddingProvider,
)
from app.providers import (
    EmbeddingProvider as AppEmbeddingProvider,
)
from app.storage import S3ObjectStore
from app.vector_store import QdrantVectorStore

_CONTRACT = PluginVersion(1, 0)
_VERSION = "0.1.0"


def _metadata(name: str, capability: Capability) -> PluginMetadata:
    return PluginMetadata(
        name=name,
        version=_VERSION,
        spec=PluginSpec(capability, _CONTRACT),
        capabilities=PluginCapabilities(frozenset({capability})),
        description="Built-in Open Graph Memory implementation",
    )


def _config(kwargs: dict[str, object]) -> PluginConfig:
    config = kwargs.get("config")
    if len(kwargs) != 1 or not isinstance(config, PluginConfig):
        raise TypeError("built-in plugin factories require only a PluginConfig named 'config'")
    return config


def _string(config: PluginConfig, key: str) -> str:
    value = config.require(key)
    if not isinstance(value, str):
        raise TypeError(f"config key '{key}' must be a string")
    return value


def _integer(config: PluginConfig, key: str) -> int:
    value = config.require(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"config key '{key}' must be an integer")
    return value


def _number(config: PluginConfig, key: str, default: float) -> float:
    value = config.get(key, default)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError(f"config key '{key}' must be a number")
    return float(value)


def _deterministic_factory(**kwargs: object) -> DeterministicProvider:
    return DeterministicProvider(_integer(_config(kwargs), "dimensions"))


def _openai_embedding_factory(**kwargs: object) -> OpenAIEmbeddingProvider:
    config = _config(kwargs)
    return OpenAIEmbeddingProvider(
        _string(config, "base_url"),
        config.require_secret("api_key").get(),
        _integer(config, "dimensions"),
    )


def _openai_chat_factory(**kwargs: object) -> OpenAIChatProvider:
    config = _config(kwargs)
    return OpenAIChatProvider(_string(config, "base_url"), config.require_secret("api_key").get())


def _deterministic_extractor_factory(**kwargs: object) -> DeterministicExtractor:
    _config(kwargs)
    return DeterministicExtractor()


def _openai_extractor_factory(**kwargs: object) -> OpenAICompatibleExtractor:
    config = _config(kwargs)
    return OpenAICompatibleExtractor(
        base_url=_string(config, "base_url"),
        api_key=config.require_secret("api_key").get(),
        model=_string(config, "model"),
        prompt_version=_string(config, "prompt_version"),
        timeout=_number(config, "timeout", 30.0),
    )


def _qdrant_factory(**kwargs: object) -> QdrantVectorStore:
    config = _config(kwargs)
    secret = config.secrets.get("api_key")
    client = AsyncQdrantClient(
        url=_string(config, "url"), api_key=secret.get() or None if secret is not None else None
    )
    return QdrantVectorStore(client, _string(config, "collection"), _integer(config, "dimensions"))


def _neo4j_factory(**kwargs: object) -> Neo4jGraphStore:
    config = _config(kwargs)
    return Neo4jGraphStore(_string(config, "url"), config.require_secret("auth").get())


def _s3_factory(**kwargs: object) -> S3ObjectStore:
    return S3ObjectStore.from_plugin_config(_config(kwargs))


def register_builtin_plugins(registry: PluginRegistry | None = None) -> PluginRegistry:
    """Register the fixed built-in set; repeated calls are intentionally harmless."""
    target = registry or get_registry()
    registrations = (
        (Capability.EMBEDDING, "deterministic", _deterministic_factory, EmbeddingProvider),
        (Capability.EMBEDDING, "openai", _openai_embedding_factory, EmbeddingProvider),
        (Capability.CHAT, "deterministic", _deterministic_factory, ChatProvider),
        (Capability.CHAT, "openai", _openai_chat_factory, ChatProvider),
        (Capability.EXTRACTION, "deterministic", _deterministic_extractor_factory, Extractor),
        (Capability.EXTRACTION, "openai", _openai_extractor_factory, Extractor),
        (Capability.OBJECT_STORE, "s3", _s3_factory, ObjectStore),
        (Capability.VECTOR_STORE, "qdrant", _qdrant_factory, VectorStore),
        (Capability.GRAPH_STORE, "neo4j", _neo4j_factory, GraphStore),
    )
    for capability, name, factory, protocol in registrations:
        target.register(_metadata(name, capability), factory, protocol=protocol)
    return target


def provider_config(base_url: str, api_key: str, dimensions: int) -> PluginConfig:
    return PluginConfig(
        {"base_url": base_url, "dimensions": dimensions}, {"api_key": SecretValue(api_key)}
    )


def create_embedding(name: str, config: PluginConfig) -> AppEmbeddingProvider:
    return cast(
        AppEmbeddingProvider,
        register_builtin_plugins().create(Capability.EMBEDDING, name, config=config),
    )


def create_chat(name: str, config: PluginConfig) -> AppChatProvider:
    return cast(
        AppChatProvider, register_builtin_plugins().create(Capability.CHAT, name, config=config)
    )


def create_extractor(name: str, config: PluginConfig) -> Extractor:
    return cast(
        Extractor, register_builtin_plugins().create(Capability.EXTRACTION, name, config=config)
    )


def create_object_store(config: PluginConfig) -> ObjectStore:
    return cast(
        ObjectStore, register_builtin_plugins().create(Capability.OBJECT_STORE, "s3", config=config)
    )


def create_vector_store(config: PluginConfig) -> QdrantVectorStore:
    return cast(
        QdrantVectorStore,
        register_builtin_plugins().create(Capability.VECTOR_STORE, "qdrant", config=config),
    )


def create_graph_store(config: PluginConfig) -> AppGraphStore:
    return cast(
        AppGraphStore,
        register_builtin_plugins().create(Capability.GRAPH_STORE, "neo4j", config=config),
    )
