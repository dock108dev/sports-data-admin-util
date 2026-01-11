# Sports Data Admin Operator Runbook

## Architecture Overview

```mermaid
flowchart LR
  subgraph Client
    Admin[Admin Browser]
  end

  subgraph Edge
    Nginx[Nginx\nadmin.scrolldownsports.*]
  end

  subgraph App
    Web[Admin UI (Next.js)]
    API[FastAPI API]
    Worker[Celery Worker (Scraper)]
  end

  subgraph Data
    Postgres[(Postgres)]
    Redis[(Redis)]
    Storage[(S3/Storage Box)]
  end

  Admin -->|HTTPS| Nginx --> Web
  Web --> API
  API --> Postgres
  API --> Redis
  Worker --> Postgres
  Worker --> Redis
  Worker --> Storage
```

## Local Development

From `infra/`:

```bash
cd infra
# Compose auto-loads infra/.env when run from this directory
docker compose --profile dev up -d --build
```

If you need non-default networking (e.g. host Postgres), use a compose override file (not provided by default).

## Production Deployment

1. Build and push images (handled by GitHub Actions).
2. Copy `infra/docker-compose.yml` to your deploy host.
3. Start services with the `prod` profile:

```bash
export COMPOSE_PROFILES=prod
docker compose up -d
```

### Admin Access (Private)

1. Use the bundled Nginx template: `infra/nginx/admin.conf`
2. Configure Basic Auth credentials:

```bash
htpasswd -c /etc/nginx/.htpasswd admin
```

3. Add your allowlisted IPs (or VPN CIDR blocks) to the config.
4. Confirm the admin UI is only available at `admin.scrolldownsports.*` and responds with `X-Robots-Tag: noindex, nofollow`.

### Optional SSH Tunnel Access

If you need private access without exposing the UI:

```bash
ssh -L 9000:localhost:80 ops@your-host
```

Then visit `http://localhost:9000` locally.

## API Readiness

* Health endpoint: `GET /healthz` (returns 503 if database connectivity fails).
* CORS is restricted via `ALLOWED_CORS_ORIGINS` (comma-separated list).
* Structured logging: JSON access logs emitted per request.
* Rate limiting: `RATE_LIMIT_REQUESTS` per `RATE_LIMIT_WINDOW_SECONDS`.
* Runtime validation: production/staging requires `ALLOWED_CORS_ORIGINS`.

Use the health endpoint for deploy verification:

```bash
curl -f http://localhost:8000/healthz
```

## Database Migrations

Alembic is configured in `api/alembic/`. Migrations are run explicitly as a separate
step (recommended for production).

Manual migration steps:

```bash
export DATABASE_URL=postgresql+asyncpg://...
docker compose --profile prod run --rm migrate
alembic -c api/alembic.ini revision --autogenerate -m "describe change"
alembic -c api/alembic.ini upgrade head
```

## Backups & Restore

### Nightly Backups

Use `scripts/backup/pg_dump_backup.sh` with a cron job or systemd timer.

Example cron entry:

```bash
0 2 * * * DATABASE_URL=postgresql+asyncpg://... BACKUP_S3_URI=s3://bucket/sports /workspace/scripts/backup/pg_dump_backup.sh
```

Upload options:

* `BACKUP_S3_URI` uses the AWS CLI (`aws s3 cp`).
* `BACKUP_RCLONE_REMOTE` uses `rclone copy` (for Hetzner Storage Box, S3-compatible endpoints, etc).

### Restore Steps

```bash
gzip -cd sports_YYYYMMDDTHHMMSSZ.sql.gz | psql "${DATABASE_URL}"
```
For container restores, set `CONFIRM_DESTRUCTIVE=true` when running `/scripts/restore.sh`.
Note: restore uses `DROP DATABASE ... WITH (FORCE)` on Postgres 16+ so you don’t need to stop app containers first.

### Destructive Operation Guardrails

- `init_db` (SQLAlchemy `create_all`) is blocked in production/staging.
- `/scripts/restore.sh` and `scripts/migrate_sports_data.sh` require `CONFIRM_DESTRUCTIVE=true`.

## CI/CD

GitHub Actions builds and pushes the API, admin UI, and worker images.

Required GitHub Secrets:

* `GHCR_TOKEN` (or use `GITHUB_TOKEN` for GHCR)
* `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`
* `DEPLOY_PATH` (directory containing docker compose files)

Deploys only the changed services and restarts them with `docker compose up -d <service>`.

## Environment Variables Reference

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Postgres connection string |
| `REDIS_URL` | Redis connection string |
| `CELERY_BROKER_URL` | Celery broker override |
| `CELERY_RESULT_BACKEND` | Celery result backend override |
| `ALLOWED_CORS_ORIGINS` | Comma-separated trusted origins |
| `RATE_LIMIT_REQUESTS` | Rate limit requests per window |
| `RATE_LIMIT_WINDOW_SECONDS` | Rate limit window size |
| `ENVIRONMENT` | `development`, `staging`, or `production` |
| `RUN_MIGRATIONS` | Run Alembic on container start (`true`/`false`) |
| `CONFIRM_DESTRUCTIVE` | Required to run destructive restore/reset scripts |
| `BACKUP_S3_URI` | S3 destination for backups |
| `BACKUP_RCLONE_REMOTE` | Rclone destination for backups |

### Startup Environment Validation (Fail-Fast)

The API and scraper now validate required environment variables at startup. Missing or invalid
configuration causes the container to exit before serving traffic or starting workers.

**API required**
- `ENVIRONMENT` (must be `development`, `staging`, or `production`)
- `DATABASE_URL`
- `ALLOWED_CORS_ORIGINS` (production only, must not include `localhost` or `127.0.0.1`)

**Scraper/worker required**
- `ENVIRONMENT` (must be `development`, `staging`, or `production`)
- `DATABASE_URL`
- `REDIS_URL`
- `ODDS_API_KEY` (production only)
- `X_BEARER_TOKEN` **or** `X_AUTH_TOKEN` + `X_CT0` (production only)

**Production-only constraints**
- `DATABASE_URL` and `REDIS_URL` must not point at `localhost` or `127.0.0.1`.
- `DATABASE_URL` must not use default `postgres:postgres` credentials.

**Tradeoff**
- Local development now requires explicit environment variables (typically via `.env`). This avoids
  accidental reliance on unsafe defaults in production.
