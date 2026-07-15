# Production Deployment

Use 64-bit Linux with Docker Compose. Build images in CI, never on constrained production host. Current limits target small hosts but **2 GB capacity is not validated**; combined service limits can exceed physical RAM during ingestion, projection, restore, or startup.

## Prerequisites

- Unique secrets; production `.env` permission `0600`, excluded from backups and Git.
- 2 GB swap minimum for experimental small-host profile; monitored disk, memory, swap, and OOM events.
- Encrypted off-host backup and tested restore path.
- Immutable application image references/digests recorded with Git SHA and Alembic revision.
- TLS hostname and external alert routing.

## Render and Deploy

GitHub Actions builds and publishes multi-architecture (`linux/amd64`, `linux/arm64`) GHCR images on `main`. Pull released images on host; do not build source there.

```sh
cp .env.example .env
# Replace all change-me values. Set GHCR_NAMESPACE=ardiannurcahya and IMAGE_TAG=latest for local image pull.
docker compose -f deployments/docker-compose.yml -f deployments/docker-compose.prod.yml config --quiet
scripts/backup.sh
docker compose -f deployments/docker-compose.yml -f deployments/docker-compose.prod.yml pull
docker compose -f deployments/docker-compose.yml -f deployments/docker-compose.prod.yml run --rm migrate
docker compose -f deployments/docker-compose.yml -f deployments/docker-compose.prod.yml up -d --no-build
curl -fsS http://localhost:3000/api/ready
```

For local image pull, set `GHCR_NAMESPACE=ardiannurcahya`, `IMAGE_TAG=latest`, then run `docker compose -f deployments/docker-compose.yml -f deployments/docker-compose.prod.yml pull` followed by `docker compose -f deployments/docker-compose.yml -f deployments/docker-compose.prod.yml up -d --no-build`. Do not build source on host. Pin immutable tag or digest for production rollout.

Production override sets one API process, Celery concurrency 1 by default, app image references, restart policy, memory/PID limits, health checks, graceful stop periods, and JSON log rotation. `graph-worker`, `community-worker`, and `dispatcher` use worker image and do not build on host.

For external S3-compatible storage, set S3 variables and include `deployments/docker-compose.external-s3.yml`; local RustFS services become profile-disabled. Use provider-native bucket versioning/export.

See [Service and Provider Configuration](service-configuration.md) for service inventory,
supported local/cloud replacements, exact environment variables, provider examples, and
preflight checks. Compatibility labels there distinguish environment-only replacements
from integrations that require a registered plugin or code change.

## Authority and Recovery

Back up PostgreSQL and object storage. Redis is transient. Qdrant and Neo4j are rebuildable projections. Run `scripts/backup.sh`, encrypt result, copy off-host, alert on backup age, and drill `scripts/restore.sh` in isolation. See `docs/runbooks/backup-restore.md`.

## Observability

- `/api/health`: liveness only.
- `/api/ready`: PostgreSQL, Redis, Qdrant, Neo4j, and object-storage checks.
- `/api/metrics`: Prometheus text metrics; restrict network access.
- Caddy emits JSON access logs; Docker rotates service logs.

Alert on readiness, backup age, disk, RAM/swap, OOM/restarts, queue age, dead letters, 5xx rate, latency, and projection drift. For Community GraphRAG, also check analytics refresh, `community-worker`/dispatcher health, report-job failures or expired leases, and source-chunk citations for global queries. See `docs/runbooks/operations.md` and [Community GraphRAG](community-graphrag.md).

## Upgrade and Rollback

Use explicit migration stage after verified backup. Prefer backward-compatible expand/contract migrations. Record old/new image digests. Roll back images by prior digest; never assume database downgrade is safe. Prefer forward fix or verified backup restore. Run upload, query, graph, memory, and readiness smoke tests before reopening traffic.

## Security

Terminate TLS through Caddy or trusted ingress. Add HSTS only after valid HTTPS deployment. Prefer Docker secrets/external secret manager over environment files. Rotate each service credential independently. Keep databases and metrics off public interfaces.
