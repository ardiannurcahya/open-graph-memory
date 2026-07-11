#!/bin/sh
set -eu
uv run ruff check .
uv run mypy
(cd apps/web && npm run lint)
