"""Bounded configuration and secret boundary for plugin construction.

PluginConfig holds non-secret configuration values that are safe to log.
SecretValue wraps credential material so it is never accidentally exposed
in repr, logs, or error messages.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TypeAlias, TypeVar, cast

from open_graph_contracts.errors import ConfigError

ConfigScalar: TypeAlias = str | int | float | bool | None  # noqa: UP040
ConfigValue: TypeAlias = ConfigScalar | tuple["ConfigValue", ...]  # noqa: UP040
_T = TypeVar("_T")


@dataclass(frozen=True)
class SecretValue:
    """Opaque wrapper for credential material — never exposed in repr or str."""

    _value: str

    def __repr__(self) -> str:
        return "SecretValue(***)"

    def __str__(self) -> str:
        return "***"

    def get(self) -> str:
        """Return the underlying secret value."""
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SecretValue):
            return NotImplemented
        return self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)


@dataclass(frozen=True)
class PluginConfig:
    """Non-secret configuration values for plugin construction.

    All values stored here must be safe to log and display in error messages.
    Secret credentials must be stored as SecretValue instances.
    """

    values: Mapping[str, ConfigValue] = field(default_factory=dict)
    secrets: Mapping[str, SecretValue] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        values = dict(self.values)
        secrets = dict(self.secrets)
        if any(not isinstance(key, str) or not key for key in (*values, *secrets)):
            raise ConfigError("config keys must be non-empty strings")
        if values.keys() & secrets.keys():
            raise ConfigError("config and secret keys must be distinct")
        for key, value in values.items():
            if not _is_config_value(value):
                raise ConfigError(f"unsupported config value for key: {key}")
        if any(not isinstance(value, SecretValue) for value in secrets.values()):
            raise ConfigError("secret values must be SecretValue instances")
        object.__setattr__(self, "values", MappingProxyType(values))
        object.__setattr__(self, "secrets", MappingProxyType(secrets))

    def get(self, key: str, default: _T | None = None) -> ConfigValue | _T | None:
        return self.values.get(key, default)

    def require(self, key: str) -> ConfigValue:
        if key not in self.values:
            raise ConfigError(f"required config key missing: {key}")
        return self.values[key]

    def require_secret(self, key: str) -> SecretValue:
        if key not in self.secrets:
            raise ConfigError(f"required secret key missing: {key}")
        return self.secrets[key]

    def with_overrides(self, **overrides: ConfigValue) -> PluginConfig:
        merged = {**self.values, **overrides}
        return PluginConfig(merged, self.secrets)


def _is_config_value(value: object) -> bool:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, tuple):
        return all(_is_config_value(item) for item in cast(tuple[object, ...], value))
    return False
