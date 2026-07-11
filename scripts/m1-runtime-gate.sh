#!/bin/sh
set -eu
compose='docker compose --env-file .env -f deployments/docker-compose.yml'
cleanup() { $compose down -v --remove-orphans; }
trap cleanup EXIT INT TERM
[ -f .env ] || cp .env.example .env
export WEB_PORT="${RUNTIME_GATE_PORT:-39092}"
$compose up -d --build
project_id=$(docker compose --env-file .env -f deployments/docker-compose.yml exec -T postgres psql -U opengraphrag -d opengraphrag -Atc "insert into projects(id,name) values(gen_random_uuid(),'m1 gate') returning id")
api="http://localhost:$WEB_PORT/api"
headers="X-Project-ID: $project_id"
dataset=$(curl -fsS -H "$headers" -H 'Content-Type: application/json' -d '{"name":"gate"}' "$api/v1/datasets")
dataset_id=$(printf '%s' "$dataset" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
printf 'runtime integration\n' > /tmp/ogm-m1.txt
first=$(curl -fsS -H "$headers" -F 'file=@/tmp/ogm-m1.txt;type=text/plain' "$api/v1/datasets/$dataset_id/documents")
second=$(curl -fsS -H "$headers" -F 'file=@/tmp/ogm-m1.txt;type=text/plain' "$api/v1/datasets/$dataset_id/documents")
[ "$(printf '%s' "$second" | python -c 'import json,sys; print(str(json.load(sys.stdin)["duplicate"]).lower())')" = true ]
first_id=$(printf '%s' "$first" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
second_id=$(printf '%s' "$second" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
[ "$first_id" = "$second_id" ]
$compose exec -T rustfs sh -c "test -n \"$(find /data -type f | head -1)\""
