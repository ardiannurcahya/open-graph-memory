# Security and Final Audit

Audit date: final hardening branch. Scope: API, worker, web, Compose, CI, SDK, docs, and operational scripts.

## Controls Verified

- Project API keys and project IDs gate tenant resources; cross-project identifiers return `404`.
- Upload size/type/signature checks, stable object keys, hashes, duplicate behavior, and streaming path exist.
- PostgreSQL remains authoritative; Neo4j is bounded projection without arbitrary Cypher endpoints.
- Durable outboxes, retries, leases, idempotency, reconciliation, and cleanup paths have tests.
- Containers run bounded production resources; API/worker images use non-root users.
- Structured application logs, readiness, liveness, metrics, log rotation, backup/restore, and runbooks exist.
- CI runs lint, typing, tests, Compose validation, image builds, runtime gate, dependency audit, filesystem scan, and web audit.

## Residual Risks

- Third-party container images and GitHub Actions use version tags rather than audited commit/digest pins in some places. Pinning requires verified upstream digests; never invent hashes.
- Production secrets use environment files by default. Prefer Docker secrets or external secret manager.
- Metrics endpoint is unauthenticated inside API routing. Restrict it at network/reverse-proxy layer in public deployments.
- 2 GB VPS profile is unmeasured and may exceed RAM under ingestion/build/load.
- No claim of battle-tested traffic, external penetration test, or completed disaster-recovery drill.

## Release Decision

Suitable as portfolio and near-production prototype after gates pass. Production adoption requires immutable image/action pinning with verified hashes, external monitoring and alert routing, encrypted off-host backups, restore drill, resource/load test, secret manager, provider-specific validation, and independent security review.
