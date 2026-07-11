#!/bin/sh
set -eu
uv run pytest
(cd apps/web && npm test)
