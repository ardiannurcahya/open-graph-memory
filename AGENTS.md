# OpenGraphMemory Agent Notes

## Layout

- Root Python project uses `uv` and Python 3.12+. Root `pyproject.toml` supplies import paths for `apps/api`, `packages/core/src`, `packages/contracts/src`, and `packages/sdk/src`; run Python commands from repo root.
- FastAPI entrypoint: `apps/api/app/main.py` (`uvicorn app.main:app`). ARQ worker: `arq app.arq_worker.WorkerSettings`.
- `apps/web` is separate Vite/React project, not npm workspace. Run all npm commands there. Vite dev server proxies `/api` to `http://localhost:8000`, stripping `/api`.
- PostgreSQL and S3-compatible storage are authoritative. Graph records and traversal queries use PostgreSQL.
- Public plugin contracts live in `packages/contracts`; SDK in `packages/sdk`. Built-in plugins use explicit registration in `apps/api/app/plugin_registry.py`; no dynamic entry-point discovery.

## Commands

- Install Python dev deps: `uv sync --frozen --group dev`.
- Install web deps: `cd apps/web && npm ci --no-audit --no-fund`.
- Full gate, fixed order: `scripts/check.sh` runs lint, tests, then build.
- Python checks: `uv run ruff check .`, `uv run mypy`, `uv run pytest`.
- Focus Python test: `uv run pytest apps/api/tests/test_config.py::test_name -q`.
- Web checks from `apps/web`: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`.
- Focus web test: `npx vitest run src/App.test.tsx -t "test name"` from `apps/web`.
- Compose syntax check: `docker compose -f deployments/docker-compose.yml config --quiet`.

## Runtime And Data

- Local stack needs Docker Compose v2 and 4 GB RAM. Copy `.env.example` to `.env`, replace all `change-me` values, then `docker compose -f deployments/docker-compose.yml up -d`.
- `migrate` and `bucket-init` must complete before API and workers start. Run migrations through `scripts/migrate.sh`; Alembic has `target_metadata = None`, so author migrations by hand.
- `scripts/runtime-gate.sh` overwrites `.env`, builds stack, uses `RUNTIME_GATE_PORT` or `39091`, then destroys volumes. Treat it as destructive, expensive vertical test.
- Runtime gates present: `scripts/runtime-gate.sh`, `scripts/m1-runtime-gate.sh`, `scripts/m3-runtime-gate.sh`, `scripts/m4-runtime-gate.sh`.
- Deterministic extractor needs no model credentials. Production validation requires `GRAPH_EXTRACTOR_PROVIDER=openai`, HTTPS provider URL, and non-placeholder secrets.

## Contracts And Tests

- Plugin factories receive only `PluginConfig`; pass secrets as `SecretValue`, never runtime, settings, sessions, or clients.
- Root pytest config supplies paths and async mode; no shared `conftest.py`.
- Web tests run in jsdom. Mock `@xyflow/react` for canvas/SVG tests; mock `sigma`, `graphology`, and ForceAtlas2 for graph renderer tests because jsdom lacks WebGL.
- Evaluation golden files are versioned baselines. Add new version; never edit published golden fixture.

## Safety

- Never commit `.env`, credentials, provider responses, volumes, or private content.
- `scripts/security-gate.sh` rejects tracked or untracked `.env`, `*.tsbuildinfo`, generated `apps/web/vite.config.{js,d.ts}`, plus GitHub/AWS token patterns.
- If locked web install fails, run `npm cache verify` then retry `npm ci`; do not replace it with unlocked install.
