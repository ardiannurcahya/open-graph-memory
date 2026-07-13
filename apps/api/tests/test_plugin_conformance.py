
from __future__ import annotations

from io import BytesIO

import pytest
from app.plugin_registry import (
    create_chat,
    create_embedding,
    create_object_store,
    provider_config,
    register_builtin_plugins,
)
from open_graph_contracts import Capability, PluginConfig, SecretValue


@pytest.mark.asyncio
async def test_deterministic_embedding_conformance() -> None:
    provider = create_embedding("deterministic", PluginConfig({"dimensions": 4}))
    assert provider.name
    assert provider.dimensions == 4
    assert await provider.embed([], "ignored") == []
    vectors = await provider.embed(["alpha", "beta"], "ignored")
    assert len(vectors) == 2
    assert all(len(vector) == 4 for vector in vectors)
    assert vectors == await provider.embed(["alpha", "beta"], "ignored")


@pytest.mark.asyncio
async def test_deterministic_chat_conformance() -> None:
    provider = create_chat("deterministic", PluginConfig({"dimensions": 4}))
    result = await provider.chat([{"role": "user", "content": "hello"}], "ignored")
    assert result.text
    assert result.usage.prompt_tokens >= 0
    assert result.usage.completion_tokens >= 0


def test_builtin_registry_declares_expected_plugins() -> None:
    registry = register_builtin_plugins()
    assert registry.list_names(Capability.EMBEDDING) == ["deterministic", "openai"]
    assert registry.list_names(Capability.CHAT) == ["deterministic", "openai"]
    assert registry.list_names(Capability.EXTRACTION) == ["deterministic", "openai"]
    assert registry.list_names(Capability.OBJECT_STORE) == ["s3"]
    assert registry.list_names(Capability.VECTOR_STORE) == ["qdrant"]
    assert registry.list_names(Capability.GRAPH_STORE) == ["neo4j"]


def test_provider_config_keeps_secret_out_of_repr() -> None:
    config = provider_config("https://provider.example/v1", "secret-token", 8)
    assert "secret-token" not in repr(config)
    assert config.require_secret("api_key").get() == "secret-token"


def test_s3_factory_accepts_bounded_plugin_config() -> None:
    # Construction only: no network call is made until upload/download/delete.
    store = create_object_store(
        PluginConfig(
            {
                "endpoint_url": "http://localhost:9000",
                "region": "us-east-1",
                "bucket": "ogm-test",
                "access_key": "access",
            },
            {"secret_key": SecretValue("secret")},
        )
    )
    assert hasattr(store, "upload")
    assert hasattr(store, "download")
    assert hasattr(store, "delete")


class InMemoryObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def upload(self, key: str, stream: object, content_type: str) -> None:
        assert content_type
        assert isinstance(stream, BytesIO)
        self.objects[key] = stream.read()

    async def download(self, key: str) -> bytes:
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


@pytest.mark.asyncio
async def test_object_store_conformance_roundtrip() -> None:
    store = InMemoryObjectStore()
    await store.upload("doc.txt", BytesIO(b"hello"), "text/plain")
    assert await store.download("doc.txt") == b"hello"
    await store.delete("doc.txt")
    await store.delete("doc.txt")
    assert store.objects == {}
