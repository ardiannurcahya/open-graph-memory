# Operations Runbook

## Deploy

1. Build images in CI, scan them, and record commit SHA plus immutable image digests.
2. Verify recent off-host backup and tested restore procedure.
3. Render production Compose config; confirm every application service uses an image and no production service builds locally.
4. Run migration preflight. Use backward-compatible expand/contract migrations.
5. Pull recorded image references, run migration explicitly, start services, then verify `/api/ready`, `/api/metrics`, dashboard, upload, query, and memory smoke tests.
6. Watch error rate, readiness, queue depth, memory, swap, disk, and OOM events.

## Rollback

1. Stop traffic and writers if data compatibility is uncertain.
2. Restore prior recorded image references; never roll back using mutable `latest`.
3. Do not downgrade database blindly. Prefer forward fix. Restore verified backup only when schema/data rollback is required.
4. Run readiness and smoke gates before reopening traffic.

## Dependency Outage

- **Neo4j:** Hybrid retrieval should fall back. Inspect graph outbox/leases; restart Neo4j; reconcile projection after recovery.
- **Qdrant:** Document queries lose vector retrieval. Keep ingestion paused if indexing cannot persist. Rebuild projection after service recovery.
- **Redis:** Workers and dispatcher cannot deliver jobs. Restore Redis, then inspect queued/outbox state; durable PostgreSQL outboxes remain authority.
- **PostgreSQL:** Stop all writers. Recover/restore database first. Do not promote Qdrant or Neo4j as authority.
- **Object storage:** Stop ingestion/deletion. Recover bucket or provider access, verify object hashes, then resume.

## Stuck Jobs and Outboxes

1. Identify job, project, dataset, document, attempt, lease expiry, and last error.
2. Confirm dependency health and worker queue routing.
3. Let expired leases reconcile through normal path. Avoid direct row edits.
4. Retry only idempotent operation after root cause fixed.
5. Escalate repeated failures; preserve trace IDs and structured logs.

## Capacity and 2 GB VPS

Configured limits are not measured support. Sum of service limits can exceed 2 GB, and builds must not run on host. Monitor RSS, swap, disk I/O, queue latency, p95 query latency, OOM kills, and container restarts. Reduce concurrency to 1. Use external S3 when possible. If sustained swap or OOM appears, increase RAM or split services.

## Alerts

Alert on readiness failure, backup age >26h, disk >80%, memory >85%, swap growth, container restart loop, PostgreSQL connection failures, queue age, dead-lettered outbox rows, query 5xx rate, p95 latency breach, and projection reconciliation drift. Route warning and critical alerts to owned channels with tested escalation.

## Secret Rotation

Rotate admin/project keys, database, object storage, Neo4j, Qdrant, and provider credentials independently. Issue new credential, deploy consumers, verify, revoke old credential, and audit logs. Never commit `.env`; rotate immediately if exposure is suspected.
