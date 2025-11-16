#!/usr/bin/env bash
set -eo pipefail

HOST="${HEALTHCHECK_HOST:-127.0.0.1}"
PORT="${HEALTHCHECK_PORT:-8000}"
PATH_PART="${HEALTHCHECK_PATH:-/}"

URL="http://${HOST}:${PORT}${PATH_PART}"

curl -fsS --max-time 2 "$URL" > /dev/null

