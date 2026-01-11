#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.prod.yml}
API_BASE_URL=${API_BASE_URL:-http://localhost:8000}

required_services=(
  db
  api
  worker
)

log() {
  printf '%s\n' "$1"
}

fail() {
  log "ERROR: $1"
  exit 1
}

check_service_running() {
  local service="$1"
  local container_id
  container_id=$(docker compose -f "$COMPOSE_FILE" ps -q "$service")
  if [[ -z "$container_id" ]]; then
    fail "Service '$service' is not running (no container found)."
  fi

  local status
  status=$(docker inspect -f '{{.State.Status}}' "$container_id")
  if [[ "$status" != "running" ]]; then
    fail "Service '$service' is not running (status: $status)."
  fi

  local health
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")
  if [[ "$health" != "none" && "$health" != "healthy" ]]; then
    fail "Service '$service' is unhealthy (health: $health)."
  fi

  if [[ "$health" == "healthy" ]]; then
    log "OK: $service is running (health: healthy)"
  else
    log "OK: $service is running"
  fi
}

check_db_connectivity() {
  log "Checking database connectivity..."
  if ! docker compose -f "$COMPOSE_FILE" exec -T db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null; then
    fail "Database connectivity check failed."
  fi
  log "OK: database is reachable"
}

check_endpoint() {
  local path="$1"
  local url="${API_BASE_URL}${path}"
  local status
  status=$(curl -sS -o /dev/null -w "%{http_code}" "$url")
  if [[ "$status" != "200" ]]; then
    fail "Endpoint check failed for $path (status: $status)."
  fi
  log "OK: $path returned 200"
}

log "Starting post-deploy verification..."
log "Using compose file: $COMPOSE_FILE"
log "Using API base URL: $API_BASE_URL"

log "Checking required services..."
for service in "${required_services[@]}"; do
  check_service_running "$service"
done

check_db_connectivity

log "Checking API endpoints..."
check_endpoint "/healthz"
check_endpoint "/games"

log "All checks passed."
