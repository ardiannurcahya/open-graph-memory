# Local Quickstart

Requirements: Docker Compose v2, or Python 3.12 with uv and Node 22 for host development.

1. Copy `.env.example` to `.env` and replace placeholder secrets.
2. Run `docker compose -f deployments/docker-compose.yml up -d`. The idempotent `bucket-init` creates the private bucket.
3. Run `docker compose -f deployments/docker-compose.yml exec api alembic upgrade head`.
4. Check `curl -fsS localhost:3000/api/health` and inspect `localhost:3000/api/ready`.
5. Stop with `docker compose -f deployments/docker-compose.yml down`; add `-v` only when intentionally deleting data.

Host checks are available through `scripts/lint.sh`, `scripts/test.sh`, and `scripts/build.sh`.
Dataset CRUD, upload constraints, examples, and the runtime gate are documented in [Dataset and document upload](dataset-upload.md).

## Graph extraction

After documents reach `indexed`, the durable graph job moves `graph_stage` from `queued` through `extracting` to `complete`. Inspect the bounded graph at `GET /api/v1/datasets/{dataset_id}/graph`; API keys and project headers remain required. The deterministic end-to-end graph gate uses no external model credentials: run `scripts/m3-runtime-gate.sh`. The M4 gate runs the real hybrid retrieval vertical slice with all retrieval modes: run `scripts/m4-runtime-gate.sh`. Both gates destroy only their own Compose volumes and write ignored reports under `artifacts/`. See [Graph extraction](graph-extraction.md), [hybrid retrieval](hybrid-retrieval.md), and [evaluation](../evaluation/README.md) for fixture semantics and thresholds.

## Dashboard, SDK, plugins, and memory

Dashboard at `http://localhost:3000` covers upload, datasets, query modes, citations, graph paths, and traces; citations show available `Page N`, `Record N`, and `Part N` source locations. See [dashboard](dashboard.md). Python SDK usage lives in [SDK docs](sdk-python.md). Provider boundaries and conformance tests live in [plugin docs](plugin-system.md). Agent Memory Preview API, scope/lifecycle, query personalization, and evaluator live in [memory docs](agent-memory-preview.md).

```sh
uv run python evaluation/memory_evaluator.py
```

Production operations, backup/restore, metrics, alerts, and unvalidated small-VPS limits are documented in [deployment](deployment.md) and [runbooks](runbooks/operations.md).
