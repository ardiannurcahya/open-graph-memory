# Plugin Contracts & Registry

M6 introduces a small public contracts package: `open_graph_contracts`. It is intentionally independent from FastAPI, SQLAlchemy, Celery, Qdrant, Neo4j, and S3 clients so external providers can depend on the contract surface without receiving unrestricted application state.

## Contract Surface

`open_graph_contracts` exports runtime-checkable protocols for:

- `EmbeddingProvider`
- `ChatProvider`
- `Extractor`
- `Parser`
- `Chunker`
- `ObjectStore`
- `VectorStore`
- `GraphStore`
- `GraphRetriever`

The package also exports:

- `PluginVersion` and `PluginMetadata` for versioned contracts
- `Capability` and `PluginCapabilities` for capability declarations
- `PluginConfig` and `SecretValue` for bounded configuration
- `PluginRegistry` for explicit registration and factory construction
- structured errors such as `PluginNotRegisteredError`, `IncompatiblePluginError`, and `PluginConstructionError`

## Registry Model

The registry is explicit by design. M6 does not load arbitrary Python entry points or dynamically import plugin code at startup. Built-ins are registered by `app.plugin_registry.register_builtin_plugins()` and then constructed through typed helper functions such as `create_embedding()`, `create_chat()`, `create_vector_store()`, and `create_graph_store()`.

Repeated registration of the same metadata/factory/protocol tuple is idempotent. Conflicting registration for the same capability/name raises `PluginValidationError`.

## Configuration Boundary

Plugin factories receive a single `PluginConfig` object. They do not receive `Settings`, `Runtime`, database sessions, or unrestricted service clients. Secrets are passed through `SecretValue`, whose `repr()` and `str()` do not reveal raw secret values.

Example:

```python
from open_graph_contracts import Capability, PluginConfig, SecretValue
from app.plugin_registry import create_embedding

provider = create_embedding(
    "openai",
    PluginConfig(
        {"base_url": "https://api.example/v1", "dimensions": 1536},
        {"api_key": SecretValue("...")},
    ),
)
```

## Compatibility

The contract version starts at `1.0.0`. A plugin is compatible when it has the same major version and a minor version greater than or equal to the required contract. Breaking protocol changes require a major version bump.

## Conformance

The repository includes focused tests for protocol runtime-checkability, metadata, error taxonomy, bounded config, built-in registry construction, and SDK transport models. External plugins should copy the example plugin test pattern and validate against the public protocols before integration.
