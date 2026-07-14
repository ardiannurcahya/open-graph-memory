# AGENTS.md

## Repo shape

- Python project uses `uv`; root `pyproject.toml` sets pytest `pythonpath` for `apps/api`, `packages/core/src`, `packages/contracts/src`, and `packages/sdk/src`.
- API entrypoint: `apps/api/app/main.py` (`uvicorn app.main:app`). Worker entrypoint: `apps/worker/worker/main.py` re-exports `app.worker.celery_app`.
- Web app lives in `apps/web` and is independent npm workspace-less Vite/React project; run npm commands from `apps/web`.
- Authoritative stores are PostgreSQL plus S3-compatible object storage; Qdrant vectors and Neo4j graph are rebuildable projections.

## Commands

- Install Python deps: `uv sync --frozen --group dev`.
- Install web deps: `cd apps/web && npm ci --no-audit --no-fund` (CI uses npm `11.6.2`; Dockerfile uses npm `12.0.1`).
- Full local gate: `scripts/check.sh` → runs `scripts/lint.sh`, `scripts/test.sh`, then `scripts/build.sh`.
- Python gates: `uv run ruff check .`, `uv run mypy`, `uv run pytest`.
- Single Python test: `uv run pytest apps/api/tests/test_config.py -q` or `uv run pytest apps/api/tests/test_config.py::test_name -q`.
- Web gates from `apps/web`: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`.
- Single web test: `cd apps/web && npx vitest run src/App.test.tsx -t "test name"`.
- Compose config check: `docker compose -f deployments/docker-compose.yml config --quiet`.
- Local stack: copy `.env.example` to `.env`, replace every `change-me`, then `docker compose -f deployments/docker-compose.yml up -d`.

## Runtime and migrations

- Compose service dependency order includes `migrate` and `bucket-init`; API waits on both, workers wait on migrate/bucket init.
- Migration command in container: `docker compose -f deployments/docker-compose.yml exec api alembic upgrade head`; `scripts/migrate.sh` wraps this.
- Alembic config is under `apps/api`; `apps/api/migrations/env.py` reads `DATABASE_URL` and has `target_metadata = None`, so migrations are hand-authored.
- `scripts/runtime-gate.sh` overwrites `.env` from `.env.example`, uses `WEB_PORT=${RUNTIME_GATE_PORT:-39091}`, builds stack, runs migrate and bucket-init, then destroys volumes on exit.

## Providers and plugins

- Deterministic providers are default and need no external model credentials; OpenAI-compatible providers can split `OPENAI_EMBEDDING_BASE_URL`, `OPENAI_CHAT_BASE_URL`, and `OPENAI_GRAPH_EXTRACTOR_BASE_URL`, each falling back to `OPENAI_BASE_URL` when unset.
- Production validation requires `GRAPH_EXTRACTOR_PROVIDER=openai`, HTTPS provider base URLs, and non-placeholder secrets.
- Plugin registry is explicit only. Do not add dynamic entry-point discovery unless changing design; built-ins register through `app.plugin_registry.register_builtin_plugins()` and construct via `create_embedding`, `create_chat`, `create_vector_store`, `create_graph_store`.
- Plugin factories receive `PluginConfig` only, not `Settings`, `Runtime`, DB sessions, or service clients; secrets must use `SecretValue`.

## Tests and evaluation quirks

- No pytest `conftest.py`; tests rely on root pytest `pythonpath` and mostly deterministic providers.
- Web tests run in jsdom with `apps/web/src/test/setup.ts`; `App.test.tsx` mocks `@xyflow/react` because SVG/canvas breaks in jsdom.
- Runtime gates are expensive Docker vertical slices and create/destroy their own resources: `scripts/runtime-gate.sh`, `scripts/m1-runtime-gate.sh`, `scripts/m2-runtime-gate.sh`, `scripts/m3-runtime-gate.sh`, `scripts/m4-runtime-gate.sh`.
- Evaluation golden files are versioned; do not mutate a published golden baseline. Add new version instead.

## Security and generated files

- Never commit `.env`, credentials, provider responses, volumes, or private content.
- `scripts/security-gate.sh` fails on tracked/untracked `.env`, `*.tsbuildinfo`, generated `apps/web/vite.config.{js,d.ts}`, and credential-shaped GitHub/AWS tokens.
- If `npm ci` fails, README says retry `npm cache verify` then `npm ci`; do not replace with unlocked install.
