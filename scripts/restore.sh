#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ $# -ne 1 ]]; then
  echo "usage: RESTORE_CONFIRM=RESTORE scripts/restore.sh backups/<timestamp>" >&2
  exit 2
fi
if [[ "${RESTORE_CONFIRM:-}" != "RESTORE" ]]; then
  echo "Refusing destructive restore. Set RESTORE_CONFIRM=RESTORE after reading docs/runbooks/backup-restore.md." >&2
  exit 2
fi

COMPOSE_FILE="${COMPOSE_FILE:-deployments/docker-compose.yml}"
SOURCE="$1"
[[ -f "${SOURCE}/postgres.dump" && -f "${SOURCE}/SHA256SUMS" ]] || {
  echo "invalid backup directory" >&2
  exit 1
}
(
  cd "${SOURCE}"
  sha256sum --check SHA256SUMS
)

set -a
# shellcheck disable=SC1091
source .env
set +a
POSTGRES_DB="${POSTGRES_DB:-opengraphrag}"
POSTGRES_USER="${POSTGRES_USER:-opengraphrag}"

printf 'Stopping writers...\n'
docker compose -f "${COMPOSE_FILE}" stop api worker

printf 'Restoring PostgreSQL...\n'
docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists --no-owner \
  < "${SOURCE}/postgres.dump"

if [[ -d "${SOURCE}/objects" ]]; then
  printf 'Restoring local object storage...\n'
  docker compose -f "${COMPOSE_FILE}" stop rustfs
  docker compose -f "${COMPOSE_FILE}" run --rm --no-deps \
    -v "$(pwd)/${SOURCE}/objects:/restore:ro" \
    --entrypoint /bin/sh rustfs -c 'rm -rf /data/* && cp -a /restore/. /data/'
  docker compose -f "${COMPOSE_FILE}" start rustfs
fi

printf 'Starting PostgreSQL-backed application services.\n'
docker compose -f "${COMPOSE_FILE}" up -d migrate api worker web
printf 'Validate /api/ready, smoke queries, object reads, and graph queries.\n'
