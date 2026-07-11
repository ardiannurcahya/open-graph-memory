# Local Quickstart

Requirements: Docker Compose v2, or Python 3.12 with uv and Node 22 for host development.

1. Copy `.env.example` to `.env` and replace placeholder secrets.
2. Run `docker compose -f deployments/docker-compose.yml up -d`. The idempotent `bucket-init` creates the private bucket.
3. Run `docker compose -f deployments/docker-compose.yml exec api alembic upgrade head`.
4. Check `curl -fsS localhost:3000/api/health` and inspect `localhost:3000/api/ready`.
5. Stop with `docker compose -f deployments/docker-compose.yml down`; add `-v` only when intentionally deleting data.

Host checks are available through `scripts/lint.sh`, `scripts/test.sh`, and `scripts/build.sh`.
