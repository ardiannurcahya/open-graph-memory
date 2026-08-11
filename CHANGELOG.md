# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] - 2026-08-11

### Added

- **Codebase Knowledge Graph & AST Ingestion**:
  - Continuous codebase AST symbol parsing across Python, TypeScript, Go, and Rust via tree-sitter.
  - Endpoints for batch ingestion (`POST /v1/codebase/ingest`), single-file live sync (`POST /v1/codebase/sync-file`), and directory indexing (`POST /v1/codebase/index-directory`).
  - Automatic Louvain hierarchical community detection on parsed codebase call-graphs and relationships.
- **Agent Memory Workspace**:
  - Interactive Agent Memory 2D graph view with domain filters, status chips, camera controls, legend, and connected node isolation.
  - Glassmorphism inspector drawer displaying episode telemetry, attempts, triggers, outcomes, feedback scores, and pattern supersession chains.
- **Documentation**:
  - Realistic token efficiency and agent economics benchmark documentation in `README.md`.

### Changed

- **UI/UX Consistency**:
  - Redesigned `AgentMemoryPage.tsx` to unify layout, top floating toolbar, and controls with `GraphPage.tsx`.
  - Harmonized Dark/Light theme text contrast, tool selector styling, and canvas rendering.
  - Migrated `ThemeControl.tsx` to an accessible segmented control with full test harness compatibility.

### Fixed

- **Type Safety & Linting**:
  - Eliminated all TypeScript `any` types in `SigmaGraphCanvas.tsx` and `AgentMemoryPage.tsx` with strongly typed node and canvas settings interfaces.
  - Formatted API schemas and code extractor modules to satisfy Ruff linting and line-length constraints (`<= 100` chars).
  - Added explicit `default=None` field definitions in Pydantic models for strict `mypy` type checking.
- **CI / CD & Deployments**:
  - Restored missing container configurations (`deployments/Caddyfile` and `deployments/rustfs/bootstrap.sh`).
  - Corrected `scripts/check-release.py` to validate active deployment compose files.
  - Resolved frontend unit test selectors and assertions across all 11 Vitest test suites.

---

## [0.1.0] - 2026-08-02

### Added

- PostgreSQL-native bounded graph traversal with project, dataset, temporal, review-state, evidence, fanout, depth, and provenance constraints.
- Persistent Agent Memory pattern supersession integrity and migration coverage.
- Cross-layer regression coverage for graph retrieval, database TLS, Agent Memory, browser authentication storage, and frontend routing.

### Changed

- Production deployment examples default to immutable `v0.1.0` first-party images instead of `latest`.
- GHCR publishes release images from `v*` tags together with immutable commit-SHA tags.
- Agent Memory search batching and audit storage now avoid N+1 access and full sensitive response snapshots.
- Browser credentials use failure-tolerant session storage and clear stale admin/project credentials when contexts change.

### Fixed

- Graph retrieval now returns the public retrieval contract instead of leaking ORM rows or silently degrading on type errors.
- Traversal excludes cross-tenant, cross-dataset, expired, superseded, rejected, and unsupported graph subjects.
- Multi-frontier paths retain the actual matched relation endpoint.
- Agent Memory supersession locks both source and replacement patterns and prevents cycles.
- PostgreSQL TLS is configurable rather than forcibly disabled.
- Frontend tests no longer eagerly require WebGL/Sigma in jsdom.

### Security

- Admin keys are no longer persisted in browser local storage.
- Production image references are versioned; operators can further pin GHCR digests for immutable rollouts.
