"""Focused tests for the open_graph_contracts package.

Covers error taxonomy, config/secret boundaries, metadata,
registry behavior, protocol runtime-checkability, and import compatibility.
"""

from __future__ import annotations

import pytest
from open_graph_contracts import (
    Capability,
    ConfigError,
    IncompatiblePluginError,
    PluginCapabilities,
    PluginConfig,
    PluginConstructionError,
    PluginEntry,
    PluginError,
    PluginFactory,
    PluginMetadata,
    PluginNotRegisteredError,
    PluginRegistry,
    PluginRuntimeError,
    PluginSpec,
    PluginValidationError,
    PluginVersion,
    SecretAccessError,
    SecretValue,
    get_registry,
)
from open_graph_contracts.registry import _reset_registry

# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "exc_cls",
    [
        ConfigError,
        PluginValidationError,
        PluginNotRegisteredError,
        IncompatiblePluginError,
        PluginConstructionError,
        PluginRuntimeError,
        SecretAccessError,
    ],
)
def test_all_errors_derive_from_plugin_error(exc_cls: type[Exception]) -> None:
    assert issubclass(exc_cls, PluginError)


def test_plugin_error_stores_plugin_name() -> None:
    err = PluginNotRegisteredError("missing", plugin_name="my-plugin")
    assert err.plugin_name == "my-plugin"
    assert "missing" in str(err)


def test_plugin_error_plugin_name_defaults_none() -> None:
    err = PluginError("boom")
    assert err.plugin_name is None


def test_construction_error_stores_cause() -> None:
    original = ValueError("bad arg")
    err = PluginConstructionError("factory failed", plugin_name="x", cause=original)
    assert err.cause is original
    assert err.plugin_name == "x"


def test_construction_error_cause_defaults_none() -> None:
    err = PluginConstructionError("factory failed")
    assert err.cause is None


def test_errors_can_be_raised_and_caught_as_base() -> None:
    with pytest.raises(PluginError):
        raise ConfigError("bad config")


# ---------------------------------------------------------------------------
# Config / SecretValue
# ---------------------------------------------------------------------------

def test_secret_value_repr_does_not_leak() -> None:
    sv = SecretValue("super-secret-token")
    assert "super-secret-token" not in repr(sv)
    assert "super-secret-token" not in str(sv)


def test_secret_value_get_returns_raw() -> None:
    sv = SecretValue("abc123")
    assert sv.get() == "abc123"


def test_secret_value_bool() -> None:
    assert bool(SecretValue("x"))
    assert not bool(SecretValue(""))


def test_secret_value_equality_and_hash() -> None:
    a = SecretValue("xyz")
    b = SecretValue("xyz")
    c = SecretValue("different")
    assert a == b
    assert a != c
    assert hash(a) == hash(b)


def test_plugin_config_get_with_default() -> None:
    cfg = PluginConfig({"a": 1})
    assert cfg.get("a") == 1
    assert cfg.get("missing") is None
    assert cfg.get("missing", "fallback") == "fallback"


def test_plugin_config_require_missing_raises() -> None:
    cfg = PluginConfig({})
    with pytest.raises(ConfigError, match="required config key missing: x"):
        cfg.require("x")


def test_plugin_config_require_returns_value() -> None:
    cfg = PluginConfig({"k": "v"})
    assert cfg.require("k") == "v"


def test_plugin_config_with_overrides() -> None:
    cfg = PluginConfig({"a": 1, "b": 2})
    merged = cfg.with_overrides(b=3, c=4)
    assert merged.get("a") == 1
    assert merged.get("b") == 3
    assert merged.get("c") == 4
    # Original is unchanged (frozen dataclass).
    assert cfg.get("b") == 2


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_plugin_version_str() -> None:
    assert str(PluginVersion(1, 2, 3)) == "1.2.3"


def test_plugin_version_compatible_same_major() -> None:
    v1_0 = PluginVersion(1, 0)
    v1_2 = PluginVersion(1, 2)
    v1_2_1 = PluginVersion(1, 2, 1)
    assert v1_2.is_compatible_with(v1_0)
    assert v1_2_1.is_compatible_with(v1_2)
    assert v1_0.is_compatible_with(v1_0)


def test_plugin_version_incompatible_different_major() -> None:
    assert not PluginVersion(2, 0).is_compatible_with(PluginVersion(1, 0))


def test_plugin_version_incompatible_lower_minor() -> None:
    assert not PluginVersion(1, 0).is_compatible_with(PluginVersion(1, 2))


def test_plugin_capabilities_supports() -> None:
    caps = PluginCapabilities(frozenset({Capability.GRAPH_STORE}))
    assert caps.supports(Capability.GRAPH_STORE)
    assert not caps.supports(Capability.EXTRACTION)


def test_plugin_spec_key() -> None:
    spec = PluginSpec(capability=Capability.EXTRACTION, contract_version=PluginVersion(1, 0))
    assert spec.key == "extraction:1.0.0"


def test_plugin_metadata_properties() -> None:
    meta = PluginMetadata(
        name="test",
        version="0.1.0",
        spec=PluginSpec(capability=Capability.GRAPH_STORE, contract_version=PluginVersion(1, 0)),
        capabilities=PluginCapabilities(frozenset({Capability.GRAPH_STORE})),
    )
    assert meta.capability is Capability.GRAPH_STORE
    assert meta.contract_version == PluginVersion(1, 0)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _meta(name: str, cap: Capability, version: PluginVersion | None = None) -> PluginMetadata:
    return PluginMetadata(
        name=name,
        version="1.0.0",
        spec=PluginSpec(capability=cap, contract_version=version or PluginVersion(1, 0)),
        capabilities=PluginCapabilities(frozenset({cap})),
    )


def _factory(**kwargs: object) -> object:
    return object()


def test_registry_register_and_create() -> None:
    reg = PluginRegistry()
    meta = _meta("p1", Capability.GRAPH_STORE)
    reg.register(meta, _factory)
    instance = reg.create(Capability.GRAPH_STORE, "p1")
    assert instance is not None


def test_registry_identical_registration_is_idempotent() -> None:
    reg = PluginRegistry()
    meta = _meta("p1", Capability.GRAPH_STORE)
    reg.register(meta, _factory)
    reg.register(meta, _factory)
    assert reg.list_names(Capability.GRAPH_STORE) == ["p1"]


def test_registry_conflicting_registration_raises() -> None:
    reg = PluginRegistry()
    meta = _meta("p1", Capability.GRAPH_STORE)
    reg.register(meta, _factory)

    def other_factory(**kwargs: object) -> object:
        return object()

    with pytest.raises(PluginValidationError, match="already registered"):
        reg.register(meta, other_factory)


def test_registry_not_registered_raises() -> None:
    reg = PluginRegistry()
    with pytest.raises(PluginNotRegisteredError):
        reg.create(Capability.GRAPH_STORE, "nope")


def test_registry_incompatible_version_raises() -> None:
    reg = PluginRegistry()
    meta = _meta("p2", Capability.GRAPH_STORE, PluginVersion(2, 0))
    with pytest.raises(IncompatiblePluginError, match="incompatible"):
        reg.register(meta, _factory)


def test_registry_caching_without_kwargs() -> None:
    reg = PluginRegistry()
    reg.register(_meta("cached", Capability.GRAPH_STORE), _factory)
    first = reg.create(Capability.GRAPH_STORE, "cached")
    second = reg.create(Capability.GRAPH_STORE, "cached")
    assert first is second


def test_registry_no_cache_with_kwargs() -> None:
    reg = PluginRegistry()
    reg.register(_meta("fresh", Capability.GRAPH_STORE), _factory)
    first = reg.create(Capability.GRAPH_STORE, "fresh", key="a")
    second = reg.create(Capability.GRAPH_STORE, "fresh", key="b")
    assert first is not second


def test_registry_factory_exception_wrapped() -> None:
    def bad_factory(**kwargs: object) -> object:
        raise ValueError("boom")

    reg = PluginRegistry()
    reg.register(_meta("bad", Capability.GRAPH_STORE), bad_factory)
    with pytest.raises(PluginConstructionError, match="failed to construct") as exc_info:
        reg.create(Capability.GRAPH_STORE, "bad")
    assert exc_info.value.cause is not None


def test_registry_list_names() -> None:
    reg = PluginRegistry()
    reg.register(_meta("zeta", Capability.GRAPH_STORE), _factory)
    reg.register(_meta("alpha", Capability.GRAPH_STORE), _factory)
    reg.register(_meta("beta", Capability.EXTRACTION), _factory)
    assert reg.list_names(Capability.GRAPH_STORE) == ["alpha", "zeta"]
    assert reg.list_names(Capability.EXTRACTION) == ["beta"]


def test_registry_list_capabilities() -> None:
    reg = PluginRegistry()
    reg.register(_meta("a", Capability.GRAPH_STORE), _factory)
    reg.register(_meta("b", Capability.EXTRACTION), _factory)
    caps = reg.list_capabilities()
    assert Capability.GRAPH_STORE in caps
    assert Capability.EXTRACTION in caps


def test_registry_is_registered() -> None:
    reg = PluginRegistry()
    reg.register(_meta("x", Capability.GRAPH_STORE), _factory)
    assert reg.is_registered(Capability.GRAPH_STORE, "x")
    assert not reg.is_registered(Capability.GRAPH_STORE, "y")


def test_registry_clear() -> None:
    reg = PluginRegistry()
    reg.register(_meta("x", Capability.GRAPH_STORE), _factory)
    reg.clear()
    assert not reg.is_registered(Capability.GRAPH_STORE, "x")
    with pytest.raises(PluginNotRegisteredError):
        reg.create(Capability.GRAPH_STORE, "x")


def test_registry_get_entry() -> None:
    reg = PluginRegistry()
    meta = _meta("entry", Capability.GRAPH_STORE)
    reg.register(meta, _factory)
    entry = reg.get_entry(Capability.GRAPH_STORE, "entry")
    assert isinstance(entry, PluginEntry)
    assert entry.name == "entry"
    assert entry.spec.capability is Capability.GRAPH_STORE


def test_registry_singleton() -> None:
    _reset_registry()
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2


def test_registry_reset() -> None:
    r = get_registry()
    r.register(_meta("temp", Capability.GRAPH_STORE), _factory)
    _reset_registry()
    fresh = get_registry()
    assert not fresh.is_registered(Capability.GRAPH_STORE, "temp")


# ---------------------------------------------------------------------------
# Protocols are runtime-checkable
# ---------------------------------------------------------------------------

def test_protocols_are_runtime_checkable() -> None:
    from open_graph_contracts.protocols import (
        Chunker,
        Extractor,
        GraphRetriever,
        GraphStore,
        ObjectStore,
        Parser,
    )

    for proto in (Extractor, Parser, Chunker, ObjectStore, GraphStore, GraphRetriever):
        assert hasattr(proto, "__protocol_attrs__"), f"{proto.__name__} not a Protocol"


def test_extractor_protocol_isinstance() -> None:
    from open_graph_contracts.protocols import Extractor as ContractExtractor

    class FakeExtractor:
        def extract(self, text: str) -> object:
            return object()

    assert isinstance(FakeExtractor(), ContractExtractor)


def test_protocol_isinstance_rejects_non_compliant() -> None:
    from open_graph_contracts.protocols import Extractor as ContractExtractor

    class MissingMethods:
        name = "fake"

    assert not isinstance(MissingMethods(), ContractExtractor)


# ---------------------------------------------------------------------------
# Import compatibility — old paths still work
# ---------------------------------------------------------------------------

def test_old_graph_store_imports_valid() -> None:
    from app.graph_store import GraphStore, Neo4jGraphStore
    assert Neo4jGraphStore is not None
    assert GraphStore is not None


def test_old_extraction_imports_valid() -> None:
    from open_graph_core.extraction import (
        DeterministicExtractor,
        Extraction,
        Extractor,
        OpenAICompatibleExtractor,
    )
    assert DeterministicExtractor is not None
    assert OpenAICompatibleExtractor is not None
    assert Extraction is not None
    assert Extractor is not None


def test_contracts_all_exports_importable() -> None:
    import open_graph_contracts

    for name in open_graph_contracts.__all__:
        assert hasattr(open_graph_contracts, name), f"{name} missing from open_graph_contracts"


def test_plugin_factory_is_protocol() -> None:
    # PluginFactory is a Protocol — just verify it's importable and usable as a type.
    assert PluginFactory is not None
