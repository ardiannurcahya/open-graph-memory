"""Generic explicit plugin registry with compatibility validation.

No entry-point loading, no dynamic imports.  Plugins must be explicitly
registered via register().  Construction is idempotent — the same kind/name
combination always returns the same cached instance within a registry.

The registry validates:
  1. The registered factory's metadata declares the correct capability.
  2. The registered factory's contract version is compatible with the
     required version for that capability.
  3. The constructed instance satisfies the runtime-checkable protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from open_graph_contracts.errors import (
    IncompatiblePluginError,
    PluginConstructionError,
    PluginNotRegisteredError,
    PluginValidationError,
)
from open_graph_contracts.metadata import (
    Capability,
    PluginMetadata,
    PluginSpec,
    PluginVersion,
)

# Required contract versions for each capability.
# Bumped only on breaking protocol changes; minor bumps add optional members.
_REQUIRED_VERSIONS: dict[Capability, PluginVersion] = {
    Capability.EXTRACTION: PluginVersion(1, 0),
    Capability.PARSER: PluginVersion(1, 0),
    Capability.CHUNKER: PluginVersion(1, 0),
    Capability.OBJECT_STORE: PluginVersion(1, 0),
    Capability.GRAPH_STORE: PluginVersion(1, 0),
    Capability.GRAPH_RETRIEVER: PluginVersion(1, 0),
}


class PluginFactory(Protocol):
    """Callable protocol for plugin factory functions."""

    def __call__(self, **kwargs: Any) -> Any: ...


@dataclass
class PluginEntry:
    """A registered plugin entry containing metadata, factory, and cached instance."""

    metadata: PluginMetadata
    factory: PluginFactory
    protocol: type[Any] | None = None
    _instance: Any = field(default=None, repr=False)

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def spec(self) -> PluginSpec:
        return self.metadata.spec

    def construct(self, **kwargs: Any) -> Any:
        """Construct (or return cached) plugin instance."""
        if self._instance is not None and not kwargs:
            return self._instance
        try:
            instance = self.factory(**kwargs)
        except Exception as exc:
            raise PluginConstructionError(
                f"failed to construct plugin '{self.metadata.name}'",
                plugin_name=self.metadata.name,
                cause=exc,
            ) from exc
        if self.protocol is not None and not isinstance(instance, self.protocol):
            raise PluginValidationError(
                f"plugin '{self.metadata.name}' does not satisfy {self.protocol.__name__}",
                plugin_name=self.metadata.name,
            )
        if not kwargs:
            self._instance = instance
        return instance


class PluginRegistry:
    """Generic explicit registry for plugin discovery and construction."""

    def __init__(self) -> None:
        self._entries: dict[tuple[Capability, str], PluginEntry] = {}

    def register(
        self,
        metadata: PluginMetadata,
        factory: PluginFactory,
        *,
        protocol: type[Any] | None = None,
    ) -> None:
        """Register a plugin factory under its capability and name.

        Validates that:
          - The metadata capability has a required version.
          - The metadata contract version is compatible with the required version.
          - The metadata name is not already registered for that capability.
        """
        required = _REQUIRED_VERSIONS.get(metadata.capability)
        if required is None:
            raise PluginValidationError(
                f"unknown capability: {metadata.capability}",
                plugin_name=metadata.name,
            )
        if not metadata.capabilities.supports(metadata.capability):
            raise PluginValidationError(
                f"plugin '{metadata.name}' does not declare {metadata.capability.value}",
                plugin_name=metadata.name,
            )
        if not metadata.contract_version.is_compatible_with(required):
            raise IncompatiblePluginError(
                f"plugin '{metadata.name}' contract {metadata.contract_version} "
                f"is incompatible with required {required} for "
                f"{metadata.capability.value}",
                plugin_name=metadata.name,
            )
        key = (metadata.capability, metadata.name)
        if key in self._entries:
            existing = self._entries[key]
            if (
                existing.metadata == metadata
                and existing.factory is factory
                and existing.protocol is protocol
            ):
                return
            raise PluginValidationError(
                f"plugin '{metadata.name}' already registered for "
                f"{metadata.capability.value}",
                plugin_name=metadata.name,
            )
        entry = PluginEntry(
            metadata=metadata,
            factory=factory,
            protocol=protocol,
            _instance=None,
        )
        self._entries[key] = entry

    def get_entry(self, capability: Capability, name: str) -> PluginEntry:
        """Return the registered PluginEntry or raise PluginNotRegisteredError."""
        key = (capability, name)
        entry = self._entries.get(key)
        if entry is None:
            raise PluginNotRegisteredError(
                f"no plugin registered for {capability.value}/{name}",
                plugin_name=name,
            )
        return entry

    def create(self, capability: Capability, name: str, **kwargs: Any) -> Any:
        """Construct and return a plugin instance by capability and name."""
        return self.get_entry(capability, name).construct(**kwargs)

    def list_names(self, capability: Capability) -> list[str]:
        """Return sorted names of plugins registered for the given capability."""
        return sorted(name for cap, name in self._entries if cap == capability)

    def list_capabilities(self) -> list[Capability]:
        """Return capabilities that have at least one registered plugin."""
        return sorted({cap for cap, _ in self._entries})

    def is_registered(self, capability: Capability, name: str) -> bool:
        return (capability, name) in self._entries

    def clear(self) -> None:
        """Remove all registered plugins and cached instances."""
        self._entries.clear()

    def validate_instance(
        self, capability: Capability, instance: object, protocol: type[Any]
    ) -> None:
        """Validate that an instance satisfies a runtime-checkable protocol."""
        if not isinstance(instance, protocol):
            raise PluginValidationError(
                f"instance does not satisfy protocol {protocol.__name__} "
                f"for {capability.value}",
            )


# ---------------------------------------------------------------------------
# Module-level singleton registry
# ---------------------------------------------------------------------------

_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Return the module-level singleton PluginRegistry."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def _reset_registry() -> None:
    """Reset the singleton registry (for testing)."""
    global _registry
    if _registry is not None:
        _registry.clear()
    _registry = None
