# Small VPS Deployment

Use a 64-bit Linux host with Docker Compose. The limits target a 2 GB RAM host with 2 GB swap, but this profile is an unvalidated Milestone 0 starting point, not a measured capacity claim. Neo4j, Qdrant, PostgreSQL, and builds can exceed it under ingestion; monitor memory, swap, disk, and OOM events and increase resources before production traffic. Build images in GHCR, never on the VPS. Copy `.env.example`, use unique secrets, set `GHCR_NAMESPACE` to the image owner and `IMAGE_TAG` to an immutable release tag or digest-compatible tag, and set a public `CADDY_SITE_ADDRESS`, then run:

```sh
docker compose -f deployments/docker-compose.yml -f deployments/docker-compose.prod.yml pull
docker compose -f deployments/docker-compose.yml -f deployments/docker-compose.prod.yml up -d
```

The production override uses one Uvicorn process, Celery concurrency 1, memory limits, health checks, and persistent volumes. Configure Docker daemon log rotation (`max-size: 10m`, `max-file: 3`). For external object storage, set S3 variables and include `deployments/docker-compose.external-s3.yml`; local RustFS services are then profile-disabled. Back up PostgreSQL and the S3 bucket; Qdrant and Neo4j are rebuildable. Terminate TLS through Caddy using a hostname.
