#!/bin/sh
set -eu
compose='docker compose --env-file .env -f deployments/docker-compose.yml'
cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo '--- API logs ---' >&2
    $compose logs --no-color api >&2 || true
  fi
  $compose down -v --remove-orphans
  exit "$status"
}
trap cleanup EXIT INT TERM
[ -f .env ] || cp .env.example .env
export WEB_PORT="${RUNTIME_GATE_PORT:-39092}"
$compose up -d --build
project_id=$($compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atq -c "insert into projects(id,name) values(gen_random_uuid(), '\''m1 gate'\'') returning id"' | awk 'NF {print; exit}')
api_key="m1-gate-$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
api_key_hash=$(printf '%s' "$api_key" | sha256sum | cut -d ' ' -f 1)
api_key_prefix=$(printf '%.16s' "$api_key")
$compose exec -T postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -v ON_ERROR_STOP=1 -c \"insert into api_keys(id,project_id,name,key_prefix,key_hash) values(gen_random_uuid(),'$project_id','m1 gate','$api_key_prefix','$api_key_hash')\"" >/dev/null
api="http://localhost:$WEB_PORT/api"
headers="X-Project-ID: $project_id"
auth="X-API-Key: $api_key"
dataset=$(curl -fsS -H "$headers" -H "$auth" -H 'Content-Type: application/json' -d '{"name":"gate"}' "$api/v1/datasets")
dataset_id=$(printf '%s' "$dataset" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
printf 'runtime integration\n' > /tmp/ogm-m1.txt
curl -fsS -H "$headers" -H "$auth" -F 'file=@/tmp/ogm-m1.txt;type=text/plain' "$api/v1/datasets/$dataset_id/documents" > /tmp/ogm-m1-first.json &
first_pid=$!
curl -fsS -H "$headers" -H "$auth" -F 'file=@/tmp/ogm-m1.txt;type=text/plain' "$api/v1/datasets/$dataset_id/documents" > /tmp/ogm-m1-second.json &
second_pid=$!
wait "$first_pid"
wait "$second_pid"
first=$(cat /tmp/ogm-m1-first.json)
second=$(cat /tmp/ogm-m1-second.json)
first_id=$(printf '%s' "$first" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
second_id=$(printf '%s' "$second" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
[ "$first_id" = "$second_id" ]
first_duplicate=$(printf '%s' "$first" | python3 -c 'import json,sys; print(str(json.load(sys.stdin)["duplicate"]).lower())')
second_duplicate=$(printf '%s' "$second" | python3 -c 'import json,sys; print(str(json.load(sys.stdin)["duplicate"]).lower())')
[ "$first_duplicate:$second_duplicate" = false:true ] || [ "$first_duplicate:$second_duplicate" = true:false ]
$compose exec -T rustfs sh -c 'test -n "$(find /data -type f | head -1)"'
