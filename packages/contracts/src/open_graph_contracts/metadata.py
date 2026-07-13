"""Versioned plugin metadata and capability declarations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Capability(StrEnum):
    """Plugin capability kinds for interface categorization."""

    EMBEDDING = "embedding"
    CHAT = "chat"
    EXTRACTION = "extraction"
    PARSER = "parser"
    CHUNKER = "chunker"
    OBJECT_STORE = "object_store"
    VECTOR_STORE = "vector_store"
    GRAPH_STORE = "graph_store"
    GRAPH_RETRIEVER = "graph_retriever"


@dataclass(frozen=True)
class PluginVersion:
    """Semantic version for a plugin contract interface."""

    major: int
    minor: int
    patch: int = 0

    def __post_init__(self) -> None:
        if self.major < 0 or self.minor < 0 or self.patch < 0:
            raise ValueError("version components must be non-negative")

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def is_compatible_with(self, required: PluginVersion) -> bool:
        """Return True when self satisfies the required version (same major, >= minor)."""
        return self.major == required.major and (
            self.minor > required.minor
            or (self.minor == required.minor and self.patch >= required.patch)
        )


@dataclass(frozen=True)
class PluginCapabilities:
    """Declared capabilities of a plugin implementation."""

    capabilities: frozenset[Capability] = field(default_factory=frozenset)

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True)
class PluginSpec:
    """Immutable specification for a plugin contract interface."""

    capability: Capability
    contract_version: PluginVersion

    @property
    def key(self) -> str:
        return f"{self.capability.value}:{self.contract_version}"


@dataclass(frozen=True)
class PluginMetadata:
    """Versioned metadata describing a plugin and its contract conformance."""

    name: str
    version: str
    spec: PluginSpec
    capabilities: PluginCapabilities
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("plugin name must not be empty")
        if not self.version or not self.version.strip():
            raise ValueError("plugin version must not be empty")

    @property
    def capability(self) -> Capability:
        return self.spec.capability

    @property
    def contract_version(self) -> PluginVersion:
        return self.spec.contract_version
