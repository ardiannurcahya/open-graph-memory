# Operations Runbook

## Deploy

1. Build and scan images in CI; record Git SHA and immutable image digests.
2. Verify recent off-host backup and tested restore procedure.
3. Render production Compose config; confirm application services use images, not local builds.
4. Run migration preflight and explicit migration stage.
5. Start services; verify readiness, metrics, dashboard, upload, graph extraction, evidence, and Graph Playground.
6. Watch errors, readiness, queue depth, graph jobs, projection drift, RAM, swap, disk, and OOM events.

## Rollback

1. Stop traffic and writers when data compatibility is uncertain.
2. Restore prior immutable image references.
3. Do not downgrade database blindly. Prefer forward fix; restore verified backup only when schema/data rollback is required.
4. Run readiness and graph smoke checks before reopening traffic.

## Dependency Outage

- **Neo4j:** Structured PostgreSQL graph reads remain available where supported. Restart Neo4j, then reconcile rebuildable projection.
- **Redis:** Workers and dispatcher stop delivering work. Restore Redis, then inspect PostgreSQL jobs and outboxes.
- **PostgreSQL:** Stop writers and recover database first. Never promote Neo4j to authority.
- **Object storage:** Stop ingestion/deletion. Recover bucket access, verify objects, then resume.

## Stuck Jobs and Outboxes

1. Identify job, project, dataset, document, attempt, lease expiry, and last error.
2. Confirm dependency health and worker queue routing.
3. Let expired leases reconcile through normal path; avoid direct row edits.
4. Retry idempotent operation only after root cause is fixed.
5. Preserve trace IDs and structured logs for repeated failures.

## Capacity

Configured limits are not measured support. Builds must not run on constrained host. Monitor RSS, swap, disk I/O, queue latency, graph API latency, OOM kills, and restarts. Reduce concurrency to 1 when needed; increase RAM or split services when swap or OOM persists.

## Alerts and Secrets

Alert on readiness failure, stale backup, disk/RAM pressure, swap growth, restart loops, PostgreSQL failures, queue age, dead-lettered outboxes, graph job failures, API 5xx/latency, and projection drift.

Rotate admin/project, database, object-storage, Neo4j, and extraction-provider credentials independently. Deploy new credential, verify consumers, revoke old credential, and audit logs. Never commit `.env`.
