# OpenGraphMemory

OpenGraphMemory is a self-hosted platform for ingesting documents, extracting evidence-backed knowledge graphs, exploring graph structure, and accessing structured graph APIs.

## Features

- Project-isolated datasets and documents.
- Streaming uploads with size, type, signature, and duplicate validation.
- Durable parsing, chunking, graph extraction, cleanup, retry, and reconciliation jobs.
- PostgreSQL-authoritative entities, relations, evidence, extraction runs, reviews, and community analytics.
- Temporal PostgreSQL graph records with current and historical fact queries.
- Bounded entity search, neighbors, paths, subgraphs, evidence, and graph inspection APIs.
- Interactive Graph Playground with community levels, filters, relation evidence, and raw JSON.
- Async Python SDK for dataset, document, and structured graph operations.
- Explicit extractor, parser, chunker, and object-store plugin contracts.

![OpenGraphMemory radial knowledge graph showing extracted entities and semantic relations](docs/assets/graph-explorer.png)

## Architecture

```text
Browser -> Caddy -> FastAPI -> PostgreSQL
                         |-> S3-compatible object storage
                         `-> Redis -> ARQ worker

Upload -> parse -> chunk -> extract entities/relations/evidence
       -> persist authoritative temporal graph records
       -> refresh hierarchical community analytics
```

- **PostgreSQL:** authoritative projects, datasets, documents, chunks, graph records, evidence, reviews, jobs, outboxes, and analytics.
- **S3-compatible object storage:** authoritative uploaded source documents.
- **Redis:** transient ARQ queue.
- **FastAPI:** authenticated dataset, document, and structured graph API.
- **React/Vite:** dataset management and Graph Playground.

## Requirements

Local stack: Docker Engine, Docker Compose v2, and at least 4 GB free RAM.

Host development: Python 3.12+, `uv`, Node.js 22+, and npm.

## Quick Start

```sh
git clone https://github.com/ardiannurcahya/open-graph-memory.git
cd open-graph-memory
cp .env.example .env
```

Replace every `change-me` value in `.env`, then start stack:

```sh
docker compose -f deployments/docker-compose.yml config --quiet
docker compose -f deployments/docker-compose.yml up -d
curl -fsS http://localhost:3000/api/health
curl -fsS http://localhost:3000/api/ready
```

Open:

- Dashboard and Graph Playground: `http://localhost:3000`
- OpenAPI: `http://localhost:3000/api/docs`
- Metrics: `http://localhost:3000/api/metrics`

Stop without deleting data:

```sh
docker compose -f deployments/docker-compose.yml down
```

Delete local volumes only when data loss is intended:

```sh
docker compose -f deployments/docker-compose.yml down -v
```

## Configuration

Important variables:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL application and migration connection |
| `REDIS_URL` | ARQ queue |
| `ADMIN_API_KEY` | Project-creation credential |
| `S3_ENDPOINT_URL` | S3-compatible endpoint |
| `S3_ACCESS_KEY` | Object-storage access key |
| `S3_SECRET_KEY` | Object-storage secret key |
| `GRAPH_EXTRACTOR_PROVIDER` | `deterministic`, `nlp`, or `openai` |
| `GRAPH_EXTRACTOR_MODEL` | Extraction model identifier |
| `OPENAI_GRAPH_EXTRACTOR_BASE_URL` | OpenAI-compatible extraction endpoint |
| `OPENAI_API_KEY` | Extraction provider credential |

Deterministic and local NLP extraction need no external model credentials. NLP extraction recognizes conservative explicit active-sentence relations without co-occurrence edges. Production requires OpenAI-compatible graph extraction over HTTPS. See [Service and Provider Configuration](docs/service-configuration.md).

Never commit `.env` or credentials.

## Structured Graph API

Project resources require:

```text
X-Project-Id: <project-id>
X-Api-Key: <project-api-key>
```

Typical flow:

1. Create project with admin credentials.
2. Create dataset and upload document.
3. Wait for ingestion and graph extraction to complete.
4. Search entities or inspect dataset graph.
5. Traverse neighbors, paths, or bounded subgraphs.
6. Inspect source evidence and review relation assertions.
7. Refresh community analytics when graph changes.

Core endpoints:

```text
GET  /v1/datasets/{dataset_id}/graph
GET  /v1/datasets/{dataset_id}/entities/search?q={text}
GET  /v1/entities/{entity_id}
GET  /v1/entities/{entity_id}/neighbors
GET  /v1/datasets/{dataset_id}/graph/path
GET  /v1/datasets/{dataset_id}/graph/subgraph
GET  /v1/evidence/{evidence_id}
PATCH /v1/relations/{relation_id}/review
POST /v1/datasets/{dataset_id}/analytics/refresh
GET  /v1/datasets/{dataset_id}/graph/explorer
```

Use OpenAPI at `/api/docs` for complete schemas, bounds, and parameters. See [Graph extraction](docs/graph-extraction.md) and [Hierarchical community analytics](docs/community-graphrag.md).

## Graph Playground

Open `http://localhost:3000`, enter project credentials, and select dataset. Playground provides:

- force-directed graph inspection with labels, filters, and community colors;
- detail, thematic, and overview community levels;
- entity search and bounded neighbor traversal;
- path and subgraph tools;
- relation evidence and raw JSON inspection;
- analytics refresh and node inspector.

See [Dashboard and Graph Playground](docs/dashboard.md).

## Python SDK

SDK source lives in `packages/sdk`. Install development dependencies with `uv sync --frozen --group dev`.

SDK covers project, dataset, document, and structured graph operations. See [Python SDK](docs/sdk-python.md).

## Provider Plugins

Public contracts live in `packages/contracts`. Implement required protocol, register provider explicitly through application plugin registry, then run conformance tests. Dynamic package entry-point discovery is not enabled.

See [Plugin system](docs/plugin-system.md).

## Development

```sh
uv sync --frozen --group dev
uv run ruff check .
uv run mypy
uv run pytest
```

Web gates:

```sh
cd apps/web
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Full local gate: `scripts/check.sh`. Runtime gates create and destroy their own resources; run them only on CI or machines with enough RAM.

## Operations

- `GET /api/health`: process liveness.
- `GET /api/ready`: PostgreSQL, Redis, and object-storage readiness.
- `GET /api/metrics`: Prometheus metrics; restrict public access.
- Back up PostgreSQL and object storage. Redis is transient; PostgreSQL outboxes republish pending work.
- Run migrations as explicit release step after verified backup.
- Monitor readiness, queues, graph jobs, latency, RAM, swap, disk, and restarts.

Production procedure: [Deployment](docs/deployment.md). Operations: [runbook](docs/runbooks/operations.md). Backup and restore: [runbook](docs/runbooks/backup-restore.md).

## Troubleshooting

API healthy but not ready:

```sh
curl -s http://localhost:3000/api/ready
docker compose -f deployments/docker-compose.yml ps
docker compose -f deployments/docker-compose.yml logs api postgres redis rustfs
```

Document or graph job stuck:

```sh
docker compose -f deployments/docker-compose.yml logs worker
```

Inspect PostgreSQL job/outbox state and dependency readiness before retrying. Expired leases are reconciled by the worker maintenance loop.

## Documentation

- [Local quickstart](docs/quickstart.md)
- [Architecture](docs/architecture.md)
- [Dataset upload](docs/dataset-upload.md)
- [Graph extraction](docs/graph-extraction.md)
- [Hierarchical community analytics](docs/community-graphrag.md)
- [Dashboard and Graph Playground](docs/dashboard.md)
- [Structured Graph Python SDK](docs/sdk-python.md)
- [Plugin system](docs/plugin-system.md)
- [Service configuration](docs/service-configuration.md)
- [Deployment](docs/deployment.md)
- [Operations runbook](docs/runbooks/operations.md)
- [Backup/restore runbook](docs/runbooks/backup-restore.md)
- [Security audit](docs/security-final-audit.md)

## Current Limitations

- Analytics refresh is synchronous and bounded to 5,000 entities and 20,000 relations per dataset.
- Dynamic plugin entry-point discovery is not enabled.
- JavaScript/TypeScript SDK is not provided.
- Small-VPS limits are targets, not measured capacity guarantees.
- Production use requires load tests, restore drills, external monitoring, secret management, and environment-specific security review.

## License

See repository license file if present.
