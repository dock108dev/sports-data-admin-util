# Infrastructure

Docker configuration for the sports-data-admin stack.

## Quick Start

```bash
cd infra
cp .env.example .env  # Edit credentials

# Development
docker compose --profile dev up -d --build

# Production (includes daily backup service)
docker compose --profile prod up -d --build
```

## Profiles

| Profile | Services | Use Case |
|---------|----------|----------|
| `dev` | postgres, redis, api, scraper, web, backup | Local development |
| `prod` | postgres, redis, api, scraper, web, backup | Production |

## Services

| Service | Port | Description |
|---------|------|-------------|
| postgres | 5432 | PostgreSQL database |
| redis | 6379 | Redis for Celery queue |
| api | 8000 | FastAPI backend |
| scraper | — | Celery worker |
| web | 3000 | Next.js admin UI |
| backup | — | Daily backup service |

## URLs

| Service | URL |
|---------|-----|
| Web Admin | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

## Files

| File | Description |
|------|-------------|
| `docker-compose.yml` | All services with dev/prod profiles |
| `api.Dockerfile` | FastAPI service |
| `scraper.Dockerfile` | Celery worker with Playwright |
| `web.Dockerfile` | Next.js admin UI |
| `scripts/backup.sh` | Database backup script |
| `scripts/restore.sh` | Database restore script |
| `backups/` | Local backup storage |
| `.env.example` | Environment template |

## Commands

```bash
# Start development stack
docker compose --profile dev up -d --build

# Start production stack (includes backup service)
docker compose --profile prod up -d --build

# View logs
docker compose logs -f api
docker compose logs -f scraper

# Restart a service
docker compose restart api

# Stop all
docker compose --profile dev down

# Stop and delete volumes (WARNING: deletes data)
docker compose --profile dev down -v
```

## Database Backup & Restore

### Automatic Backups (Production)

When running with `--profile prod`, the backup service automatically:
- Creates a compressed SQL dump daily
- Stores backups in `infra/backups/`
- Keeps only the last 7 days of backups
- Maintains a `latest.sql.gz` symlink

### Manual Backup

```bash
# Create a backup now
docker exec sports-postgres /scripts/backup.sh

# List available backups
ls -la infra/backups/
```

### Restore from Backup

```bash
# Restore from latest backup (destructive)
CONFIRM_DESTRUCTIVE=true docker exec sports-postgres /scripts/restore.sh

# Restore from specific backup
CONFIRM_DESTRUCTIVE=true docker exec sports-postgres /scripts/restore.sh /backups/sports_20260108_120000.sql.gz
```

### Backup to External Storage

For production, consider copying backups offsite:

```bash
# Copy to S3
aws s3 sync infra/backups/ s3://your-bucket/sports-backups/

# Copy to remote server
rsync -avz infra/backups/ user@backup-server:/backups/sports/
```

## Data Migration

### Import Existing Data

If you have data in a host Postgres and want to migrate to Docker:

```bash
# 1. Export from host Postgres
pg_dump -h localhost -U dock108 dock108 > data_export.sql

# 2. Start the Docker stack
docker compose --profile dev up -d

# 3. Wait for postgres to be ready
docker compose logs -f postgres  # Wait for "ready to accept connections"

# 4. Import into Docker postgres
cat data_export.sql | docker exec -i sports-postgres psql -U sports -d sports

# 5. Verify
docker exec sports-postgres psql -U sports -d sports -c "SELECT COUNT(*) FROM sports_games;"
```

## Migrations

Alembic migrations are run explicitly (not on every API startup). Use the dedicated
`migrate` service or run Alembic in the API container.

```bash
# Recommended (explicit) migration job
docker compose --profile prod run --rm migrate

# Check current version
docker exec sports-api alembic current

# Run pending migrations manually
docker exec sports-api alembic upgrade head

# Create a new migration
docker exec sports-api alembic revision --autogenerate -m "describe change"
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_DB` | Yes | Database name |
| `POSTGRES_USER` | Yes | Database user |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `POSTGRES_PORT` | No | Host port for postgres (default: 5432) |
| `REDIS_PASSWORD` | No | Redis password |
| `ENVIRONMENT` | No | `development` or `production` |
| `RUN_MIGRATIONS` | No | Run Alembic on startup (dev-only; default false) |
| `ODDS_API_KEY` | No | The Odds API key |
| `X_AUTH_TOKEN` | No | X/Twitter auth cookie |
| `X_CT0` | No | X/Twitter CSRF cookie |
| `NEXT_PUBLIC_SPORTS_API_URL` | Yes | API URL for frontend |
| `SPORTS_API_INTERNAL_URL` | No | Internal API URL for server-side fetches in Docker |
| `NEXT_PUBLIC_THEORY_ENGINE_URL` | No | Back-compat client URL fallback |
| `ALLOWED_CORS_ORIGINS` | Prod | Allowed CORS origins |
| `CONFIRM_DESTRUCTIVE` | No | Required for restore/reset scripts |

## Health Checks

All services have health checks configured:

```bash
# Check all service health
docker compose ps

# Check specific service
docker inspect --format='{{.State.Health.Status}}' sports-api
```

The API container health check calls `GET /healthz`, which performs a lightweight database connectivity check and returns `503` when the database is unavailable. Use the same endpoint for deploy verification.

## Troubleshooting

### Postgres connection refused

```bash
# Check if postgres is running
docker compose ps postgres

# Check postgres logs
docker compose logs postgres
```

### API won't start

```bash
# Check API logs
docker compose logs api

# Common issues:
# - Database not ready: wait for postgres healthcheck
# - Migration error: check alembic version
```

### Scraper not processing jobs

```bash
# Check scraper logs
docker compose logs scraper

# Check Redis connection
docker exec sports-redis redis-cli ping
```
