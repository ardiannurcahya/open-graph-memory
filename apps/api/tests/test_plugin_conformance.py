
from __future__ import annotations

from io import BytesIO

import pytest
from app.plugin_registry import (
    create_extractor,
    create_object_store,
    register_builtin_plugins,
)
from open_graph_contracts import Capability, PluginConfig, SecretValue


def test_builtin_registry_declares_expected_plugins() -> None:
    registry = register_builtin_plugins()
    assert registry.list_names(Capability.EXTRACTION) == ["deterministic", "nlp", "openai"]
    assert registry.list_names(Capability.OBJECT_STORE) == ["s3"]
    assert registry.list_names(Capability.GRAPH_STORE) == ["neo4j"]


def test_nlp_factory_accepts_model_without_secret() -> None:
    extractor = create_extractor("nlp", PluginConfig({"model": "local-nlp-v1"}))

    assert extractor.extract("Alice Nguyen works at Acme Labs.").relations[0].type == "WORKS_AT"


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
