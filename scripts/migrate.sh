#!/bin/sh
set -eu
docker compose -f deployments/docker-compose.yml exec api alembic upgrade head
