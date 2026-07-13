"""Structured plugin error taxonomy.

All plugin-related errors derive from PluginError.  The hierarchy is:

    PluginError
    ├── ConfigError
    ├── PluginValidationError
    ├── PluginNotRegisteredError
    ├── IncompatiblePluginError
    ├── PluginConstructionError
    ├── PluginRuntimeError
    └── SecretAccessError
"""

from __future__ import annotations


class PluginError(Exception):
    """Base class for all plugin-related errors."""

    def __init__(self, message: str, *, plugin_name: str | None = None) -> None:
        super().__init__(message)
        self.plugin_name = plugin_name


class ConfigError(PluginError):
    """Raised when plugin configuration is invalid or missing required keys."""


class PluginValidationError(PluginError):
    """Raised when a registered plugin fails protocol/capability validation."""


class PluginNotRegisteredError(PluginError):
    """Raised when no plugin is registered for a requested capability/kind."""


class IncompatiblePluginError(PluginError):
    """Raised when a plugin's contract version is incompatible with the required version."""


class PluginConstructionError(PluginError):
    """Raised when a factory fails to construct a plugin instance."""

    def __init__(
        self, message: str, *, plugin_name: str | None = None, cause: Exception | None = None
    ) -> None:
        super().__init__(message, plugin_name=plugin_name)
        self.cause = cause


class PluginRuntimeError(PluginError):
    """Raised when a plugin operation fails at runtime."""


class SecretAccessError(PluginError):
    """Raised when an attempt is made to access secrets in an unsafe context."""
