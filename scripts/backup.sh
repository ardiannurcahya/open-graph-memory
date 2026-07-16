#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

COMPOSE_FILE="${COMPOSE_FILE:-deployments/docker-compose.yml}"
BACKUP_ROOT="${BACKUP_ROOT:-backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${BACKUP_ROOT}/${STAMP}"
mkdir -p "${DEST}"

if [[ ! -f .env ]]; then
  echo "missing .env" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

POSTGRES_DB="${POSTGRES_DB:-opengraphrag}"
POSTGRES_USER="${POSTGRES_USER:-opengraphrag}"
S3_BUCKET="${S3_BUCKET:-opengraphrag}"

printf 'Creating PostgreSQL backup...\n'
docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --format=custom --no-owner \
  > "${DEST}/postgres.dump"

printf 'Creating local object-storage backup...\n'
mkdir -p "${DEST}/objects"
docker compose -f "${COMPOSE_FILE}" cp rustfs:/data/. "${DEST}/objects/" || {
  echo "object backup failed; PostgreSQL dump retained" >&2
  echo "External S3 deployments must use provider-native versioning/export instead." >&2
  exit 1
}

(
  cd "${DEST}"
  sha256sum postgres.dump > SHA256SUMS
  find objects -type f -print0 | sort -z | xargs -0 -r sha256sum >> SHA256SUMS
)
cat > "${DEST}/manifest.txt" <<EOF
created_at=${STAMP}
postgres_db=${POSTGRES_DB}
s3_bucket=${S3_BUCKET}
authoritative_stores=postgresql,object-storage
rebuildable_stores=neo4j
EOF
printf 'Backup complete: %s\n' "${DEST}"
printf 'Copy this directory to encrypted off-host storage.\n'
