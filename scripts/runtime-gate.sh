#!/bin/sh
set -eu
compose='docker compose --env-file .env -f deployments/docker-compose.yml'
cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    $compose ps -a || true
    $compose logs --no-color migrate api worker || true
  fi
  $compose down -v --remove-orphans
  exit "$status"
}
trap cleanup EXIT INT TERM
cp .env.example .env
export WEB_PORT="${RUNTIME_GATE_PORT:-39091}"
$compose up -d --build
$compose run --rm bucket-init
$compose run --rm bucket-init
$compose exec -T worker arq --check app.arq_worker.WorkerSettings
curl -fsS http://localhost:${WEB_PORT:-3000}/api/health
curl -fsS http://localhost:${WEB_PORT:-3000}/api/ready
index=$(curl -fsS http://localhost:${WEB_PORT:-3000}/)
fallback=$(curl -fsS http://localhost:${WEB_PORT:-3000}/deep/spa/route)
[ "$index" = "$fallback" ]
