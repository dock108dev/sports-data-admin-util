#!/usr/bin/env bash
set -euo pipefail

environment="${ENVIRONMENT:-development}"
if [[ "${environment}" == "production" || "${environment}" == "staging" ]]; then
  : "${DATABASE_URL:?DATABASE_URL must be set for ${environment}.}"
  : "${ALLOWED_CORS_ORIGINS:?ALLOWED_CORS_ORIGINS must be set for ${environment}.}"
  : "${REDIS_URL:?REDIS_URL must be set for ${environment}.}"
fi

if [[ "${RUN_MIGRATIONS:-false}" == "true" ]]; then
  alembic -c /app/alembic.ini upgrade head
fi

exec "$@"
