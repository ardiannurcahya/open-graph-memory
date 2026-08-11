#!/bin/sh
set -eu

attempt=0
until mc alias set local http://rustfs:9000 "$S3_ACCESS_KEY" "$S3_SECRET_KEY"; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "object storage did not become ready after 60 seconds" >&2
    exit 1
  fi
  sleep 2
done
mc mb --ignore-existing "local/$S3_BUCKET"
mc anonymous set private "local/$S3_BUCKET"
mc stat "local/$S3_BUCKET" >/dev/null
