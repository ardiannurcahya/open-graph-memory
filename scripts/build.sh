#!/bin/sh
set -eu
(cd apps/web && npm run build)
docker compose -f deployments/docker-compose.yml config >/dev/null
