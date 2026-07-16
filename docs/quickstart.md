# Local Quickstart

Requirements: Docker Compose v2, or Python 3.12 with `uv` and Node 22 for host development.

1. Copy `.env.example` to `.env`; replace placeholder secrets.
2. Run `docker compose -f deployments/docker-compose.yml up -d`.
3. Check `curl -fsS localhost:3000/api/health` and `curl -fsS localhost:3000/api/ready`.
4. Open `http://localhost:3000`, create/select dataset, and upload document.
5. Wait for ingestion and graph extraction to complete.
6. Open Graph Playground to search entities, traverse graph, inspect evidence, and refresh analytics.
7. Stop with `docker compose -f deployments/docker-compose.yml down`; add `-v` only when intentionally deleting local data.

Host checks: `scripts/lint.sh`, `scripts/test.sh`, and `scripts/build.sh`.

See [dataset upload](dataset-upload.md), [graph extraction](graph-extraction.md), [Graph Playground](dashboard.md), [Python SDK](sdk-python.md), and [plugin contracts](plugin-system.md). Production operations live in [deployment](deployment.md) and [operations runbook](runbooks/operations.md).
