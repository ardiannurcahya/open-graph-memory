#!/bin/sh
set -eu

FIXTURES=${M4_FIXTURES:-evaluation/m4_golden/fixture-v1.1.json}
COMPOSE='docker compose --env-file .env -f deployments/docker-compose.yml'
export WEB_PORT="${M4_RUNTIME_PORT:-39095}"

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    $COMPOSE logs --no-color api worker graph-worker dispatcher neo4j >&2 || true
  fi
  $COMPOSE down -v --remove-orphans
  exit "$status"
}
trap cleanup EXIT INT TERM
[ -f .env ] || cp .env.example .env
if [ -z "${ADMIN_API_KEY:-}" ]; then
  ADMIN_API_KEY=$(awk -F= '$1 == "ADMIN_API_KEY" {sub(/^[^=]*=/, ""); print; exit}' .env)
  export ADMIN_API_KEY
fi
[ -n "$ADMIN_API_KEY" ] || { echo "ADMIN_API_KEY is required" >&2; exit 1; }
$COMPOSE down -v --remove-orphans
$COMPOSE up -d --build
uv run python evaluation/m4_runtime_gate.py \
  --base-url "http://localhost:$WEB_PORT/api" \
  --compose-file deployments/docker-compose.yml \
  --fixtures "$FIXTURES"
