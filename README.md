# OpenGraphRAG

Open-source, self-hosted GraphRAG and agent-memory platform prototype. System combines document ingestion, vector retrieval, knowledge-graph projection, hybrid retrieval, trace exploration, provider contracts, Python SDK, and scoped agent memory.

## Current Status

| Area | Status |
|---|---|
| M0 Foundation | Complete |
| M1 Dataset & Upload | Complete |
| M2 Vector RAG | Complete |
| M3 Graph Construction | Complete |
| M4 Hybrid Graph Retrieval | Complete |
| M5 Dashboard & Trace Explorer | Complete |
| M6 Plugin Contracts & Python SDK | Complete |
| Agent Memory | Preview complete |
| Production hardening | Operational baseline complete; real traffic and 2 GB VPS capacity remain unvalidated |

## Architecture

PostgreSQL and object storage are authoritative. Qdrant and Neo4j are rebuildable vector and graph projections. Redis/Celery run durable ingestion, graph projection, cleanup, retries, and leases. FastAPI exposes project-isolated APIs. Web dashboard provides upload, retrieval-mode selection, citations, graph paths, and trace inspection.

Memory Preview stores users, agents, sessions, messages, facts, provenance, temporal validity, deletion state, and supersession chains in PostgreSQL. Memory retrieval can personalize queries but never masquerades as document citation evidence.

## Start Locally

```sh
cp .env.example .env
# Replace every change-me value.
docker compose -f deployments/docker-compose.yml config
docker compose -f deployments/docker-compose.yml up -d
```

Open `http://localhost:3000`. API liveness: `/api/health`; readiness: `/api/ready`; OpenAPI: `/api/docs`; Prometheus metrics: `/api/metrics`.

## Main Capabilities

- Streaming document upload, duplicate handling, object storage, tenant isolation.
- Chunking, embeddings, Qdrant search, grounded answers, citations, refusal behavior.
- Entity/relation extraction, evidence provenance, PostgreSQL authority, Neo4j projection.
- `vector_only`, `graph_only`, and `hybrid` retrieval with bounded traversal and fallback.
- RRF/weighted fusion, query traces, graph paths, latency and evidence inspection.
- Dashboard for datasets, upload, query playground, citations, graph and trace exploration.
- Provider contracts for embedding, chat, extraction, storage, vector and graph stores.
- Async Python SDK and plugin conformance tests.
- Scoped Agent Memory Preview with lifecycle, provenance, conflict resolution, and search.
- Backup/restore scripts, metrics, deployment guidance, alert rules, runbooks, and security gates.

## Quality Gates

```sh
uv sync --frozen --extra dev
uv run ruff check .
uv run mypy
uv run pytest
uv run python evaluation/memory_evaluator.py
cd apps/web && npm ci && npm run lint && npm run typecheck && npm test && npm run build
```

Real Compose gates live under `scripts/*-runtime-gate.sh`. Run them in CI or a host with enough RAM. Do not run full stack builds on a constrained production VPS.

## Operations

```sh
scripts/backup.sh
RESTORE_CONFIRM=RESTORE scripts/restore.sh backups/<timestamp>
```

Backups contain authoritative PostgreSQL and local object-storage data. Encrypt and copy them off-host. Qdrant and Neo4j remain rebuildable. Read `docs/runbooks/backup-restore.md` before restoration.

## Documentation

- [Quickstart](docs/quickstart.md)
- [Vector RAG](docs/vector-rag.md)
- [Graph extraction](docs/graph-extraction.md)
- [Hybrid retrieval](docs/hybrid-retrieval.md)
- [Dashboard](docs/dashboard.md)
- [Plugin system](docs/plugin-system.md)
- [Python SDK](docs/sdk-python.md)
- [Agent Memory Preview](docs/agent-memory-preview.md)
- [Deployment](docs/deployment.md)
- [Operations runbook](docs/runbooks/operations.md)
- [Backup/restore runbook](docs/runbooks/backup-restore.md)
- [Security and final audit](docs/security-final-audit.md)
- [Evaluation](evaluation/README.md)

## Production Boundary

Project is portfolio-ready and operationally documented. It is not battle-tested production software. Current small-VPS limits are configuration targets, not measured capacity guarantees. Before production use: run restore drills, load/resource tests, full runtime gates, provider-specific failure tests, external monitoring, alert routing, secret rotation, and independent security review.
