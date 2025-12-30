#!/usr/bin/env bash
set -euo pipefail

if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
  alembic -c /app/alembic.ini upgrade head
fi

exec "$@"
