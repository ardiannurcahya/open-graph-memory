# Plugin Contracts and Registry

`open_graph_contracts` is independent from FastAPI, SQLAlchemy, Celery, Neo4j, and S3 clients. External providers can depend on bounded contract surface without receiving application state.

## Contracts

Runtime-checkable protocols:

- `Extractor`
- `Parser`
- `Chunker`
- `ObjectStore`
- `GraphStore`
- `GraphRetriever`

Package also exports version metadata, capability declarations, bounded `PluginConfig`, redacted `SecretValue`, explicit `PluginRegistry`, and structured registration/construction errors.

## Registry

Registry loads built-ins explicitly through `app.plugin_registry.register_builtin_plugins()`. Factories construct extractors and graph stores through typed helpers. Runtime does not discover arbitrary Python entry points or dynamically import plugin packages.

Repeated identical registration is idempotent. Conflicting registration for same capability/name raises `PluginValidationError`.

## Configuration Boundary

Plugin factories receive one `PluginConfig`. They do not receive `Settings`, runtime objects, database sessions, or unrestricted service clients. Secrets use `SecretValue`; string and representation output redact raw value.

## Compatibility and Conformance

Contract starts at `1.0.0`. Compatible plugin keeps same major and satisfies required minor/patch version. Breaking protocol changes require major bump.

Run protocol runtime-checkability, metadata, error taxonomy, bounded config, registry construction, and lifecycle conformance before integration.
