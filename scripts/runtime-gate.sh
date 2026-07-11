#!/bin/sh
set -eu
compose='docker compose --env-file .env -f deployments/docker-compose.yml'
cleanup() { $compose down -v --remove-orphans; }
trap cleanup EXIT INT TERM
cp .env.example .env
export WEB_PORT="${RUNTIME_GATE_PORT:-39091}"
$compose up -d --build
$compose run --rm migrate
$compose run --rm bucket-init
$compose run --rm bucket-init
$compose exec -T worker celery -A worker.main.celery_app inspect ping --timeout 10
curl -fsS http://localhost:${WEB_PORT:-3000}/api/health
curl -fsS http://localhost:${WEB_PORT:-3000}/api/ready
index=$(curl -fsS http://localhost:${WEB_PORT:-3000}/)
fallback=$(curl -fsS http://localhost:${WEB_PORT:-3000}/deep/spa/route)
[ "$index" = "$fallback" ]
