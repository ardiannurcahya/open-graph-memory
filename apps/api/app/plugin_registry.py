"""Explicit registration and bounded construction of built-in application plugins."""

from typing import cast

from open_graph_contracts import (
    Capability,
    Extractor,
    ObjectStore,
    PluginCapabilities,
    PluginConfig,
    PluginMetadata,
    PluginRegistry,
    PluginSpec,
    PluginVersion,
    get_registry,
)
from open_graph_core.extraction import (
    DeterministicExtractor,
    NlpExtractor,
    OpenAICompatibleExtractor,
)

from app.storage import S3ObjectStore

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


def _number(config: PluginConfig, key: str, default: float) -> float:
    value = config.get(key, default)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError(f"config key '{key}' must be a number")
    return float(value)


def _deterministic_extractor_factory(**kwargs: object) -> DeterministicExtractor:
    _config(kwargs)
    return DeterministicExtractor()


def _nlp_extractor_factory(**kwargs: object) -> NlpExtractor:
    config = _config(kwargs)
    model = config.get("model", "nlp-graph-v1")
    if not isinstance(model, str):
        raise TypeError("config key 'model' must be a string")
    return NlpExtractor(model=model)


def _openai_extractor_factory(**kwargs: object) -> OpenAICompatibleExtractor:
    config = _config(kwargs)
    return OpenAICompatibleExtractor(
        base_url=_string(config, "base_url"),
        api_key=config.require_secret("api_key").get(),
        model=_string(config, "model"),
        prompt_version=_string(config, "prompt_version"),
        timeout=_number(config, "timeout", 30.0),
    )


def _s3_factory(**kwargs: object) -> S3ObjectStore:
    return S3ObjectStore.from_plugin_config(_config(kwargs))


def register_builtin_plugins(registry: PluginRegistry | None = None) -> PluginRegistry:
    """Register the fixed built-in set; repeated calls are intentionally harmless."""
    target = registry or get_registry()
    registrations = (
        (Capability.EXTRACTION, "deterministic", _deterministic_extractor_factory, Extractor),
        (Capability.EXTRACTION, "nlp", _nlp_extractor_factory, Extractor),
        (Capability.EXTRACTION, "openai", _openai_extractor_factory, Extractor),
        (Capability.OBJECT_STORE, "s3", _s3_factory, ObjectStore),
    )
    for capability, name, factory, protocol in registrations:
        target.register(_metadata(name, capability), factory, protocol=protocol)
    return target


def create_extractor(name: str, config: PluginConfig) -> Extractor:
    return cast(
        Extractor, register_builtin_plugins().create(Capability.EXTRACTION, name, config=config)
    )


def create_object_store(config: PluginConfig) -> ObjectStore:
    return cast(
        ObjectStore, register_builtin_plugins().create(Capability.OBJECT_STORE, "s3", config=config)
    )
