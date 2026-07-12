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

## Graph Review API

All graph endpoints require `X-Project-Id` and `X-Api-Key`; identifiers from another project are deliberately returned as `404`. PostgreSQL is the authoritative source for graph metadata, review state, runs, jobs, and citations. Neo4j is bootstrapped during API startup only as the derived graph projection.

- `GET /api/v1/entities/{entity_id}` and `/neighbors?limit=1..100` inspect an entity and bounded relations.
- `GET /api/v1/datasets/{dataset_id}/graph?limit=1..200&depth=0..1` returns a bounded subgraph and total counts. Empty datasets return empty node and relation lists.
- `GET /api/v1/evidence/{evidence_id}`, `/graph-runs/{run_id}`, and `/graph-jobs/{job_id}` expose evidence citations and extraction status.
- `PATCH /api/v1/relations/{relation_id}/review` accepts `{"review_state":"approved"}` or `{"review_state":"rejected"}`. Only an unreviewed or needs-review relation may receive a terminal decision.

Graph responses retain `dataset_id`, `document_id`, and `chunk_id` citations. Limits and depth are validated by the API; no endpoint accepts arbitrary Cypher.
