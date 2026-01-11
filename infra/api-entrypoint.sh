#!/usr/bin/env bash
set -euo pipefail

environment="${ENVIRONMENT:-development}"

# Only validate all env vars when starting the API server (not for migrations)
is_api_server=false
for arg in "$@"; do
  if [[ "$arg" == "uvicorn" ]]; then
    is_api_server=true
    break
  fi
done

if [[ "${environment}" == "production" || "${environment}" == "staging" ]]; then
  : "${DATABASE_URL:?DATABASE_URL must be set for ${environment}.}"
  
  # CORS and Redis only required for the API server, not migrations
  if [[ "$is_api_server" == "true" ]]; then
    : "${ALLOWED_CORS_ORIGINS:?ALLOWED_CORS_ORIGINS must be set for ${environment}.}"
    : "${REDIS_URL:?REDIS_URL must be set for ${environment}.}"
  fi
fi

if [[ "${RUN_MIGRATIONS:-false}" == "true" ]]; then
  alembic -c /app/alembic.ini upgrade head
fi

exec "$@"
