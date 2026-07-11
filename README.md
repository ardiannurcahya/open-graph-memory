# OpenGraphRAG

Open-source, self-hosted GraphRAG and future agent-memory infrastructure. Milestone 0 provides the runnable API, worker, web shell, and local dependencies.

## Start

```sh
cp .env.example .env
# Replace every change-me value.
docker compose -f deployments/docker-compose.yml config
docker compose -f deployments/docker-compose.yml up -d
```

Open `http://localhost:3000`; liveness is `/api/health`, readiness is `/api/ready`, and OpenAPI is `/api/docs`. See `docs/quickstart.md` and `docs/deployment.md`.
