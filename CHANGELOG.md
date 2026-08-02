# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
