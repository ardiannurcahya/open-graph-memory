"""Public plugin contracts for Open Graph Memory.

This package defines versioned protocols, error taxonomy, config boundaries,
and a generic explicit registry for plugin discovery and construction.
It is intentionally lightweight — no entry-point loading, no dynamic imports.
"""

from open_graph_contracts.config import ConfigScalar, ConfigValue, PluginConfig, SecretValue
from open_graph_contracts.errors import (
    ConfigError,
    IncompatiblePluginError,
    PluginConstructionError,
    PluginError,
    PluginNotRegisteredError,
    PluginRuntimeError,
    PluginValidationError,
    SecretAccessError,
)
from open_graph_contracts.metadata import (
    Capability,
    PluginCapabilities,
    PluginMetadata,
    PluginSpec,
    PluginVersion,
)
from open_graph_contracts.protocols import (
    ChatProvider,
    Chunker,
    EmbeddingProvider,
    Extractor,
    GraphRetriever,
    GraphStore,
    ObjectStore,
    Parser,
    VectorStore,
)
from open_graph_contracts.registry import (
    PluginEntry,
    PluginFactory,
    PluginRegistry,
    get_registry,
)

__all__ = [
    # Metadata
    "Capability",
    "PluginCapabilities",
    "PluginMetadata",
    "PluginSpec",
    "PluginVersion",
    # Config
    "ConfigScalar",
    "ConfigValue",
    "PluginConfig",
    "SecretValue",
    # Errors
    "ConfigError",
    "IncompatiblePluginError",
    "PluginConstructionError",
    "PluginError",
    "PluginNotRegisteredError",
    "PluginRuntimeError",
    "PluginValidationError",
    "SecretAccessError",
    # Protocols
    "ChatProvider",
    "Chunker",
    "EmbeddingProvider",
    "Extractor",
    "GraphRetriever",
    "GraphStore",
    "ObjectStore",
    "Parser",
    "VectorStore",
    # Registry
    "PluginEntry",
    "PluginFactory",
    "PluginRegistry",
    "get_registry",
]
