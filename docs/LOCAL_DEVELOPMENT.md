# Local Development

## Docker (Recommended)

The easiest way to run the full stack locally.

### Quick Start

```bash
cd infra
cp .env.example .env   # Edit credentials as needed

# Start everything with the dev profile
docker compose --profile dev up -d --build
```

**URLs:**
- Admin UI: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/healthz

### Using an Existing Database

By default, `infra/docker-compose.yml` runs Postgres **inside Docker** and the API connects to it via the `postgres` service name.
If you want to connect to a host Postgres instead, you’ll need to override the compose config (not provided by default).

### Migrations

Migrations are run explicitly (not on every container startup). Use the dedicated
`migrate` service or run Alembic in the API container.

To run migrations manually:

```bash
# Recommended (explicit) migration job
docker compose --profile dev run --rm migrate

# Check current version
docker exec sports-api alembic current

# Run pending migrations
docker exec sports-api alembic upgrade head

# Create a new migration
docker exec sports-api alembic revision --autogenerate -m "describe change"
```

### Container Commands

```bash
# View logs
docker compose --profile dev logs -f api
docker compose --profile dev logs -f scraper

# Restart a service
docker compose --profile dev restart api

# Rebuild and restart
docker compose --profile dev up -d --build api

# Stop everything
docker compose --profile dev down
```

## Local Services (Without Docker)

For development without Docker, run each service manually.

### 1. Database Setup

```bash
# Apply schema (if starting fresh)
psql "$DATABASE_URL" -f sql/000_sports_schema.sql

# Or run Alembic migrations
cd api
alembic upgrade head
```

### 2. API

```bash
cd api
pip install -r requirements.txt

export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/sports"
export REDIS_URL="redis://localhost:6379/2"

uvicorn main:app --reload --port 8000
```

### 3. Scraper (Celery Worker)

```bash
cd scraper
uv pip install --system -e .

export DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/sports"
export REDIS_URL="redis://localhost:6379/2"

celery -A bets_scraper.celery_app.app worker --loglevel=info --queues=bets-scraper
```

### 4. Web UI

```bash
cd web
pnpm install

export NEXT_PUBLIC_SPORTS_API_URL=http://localhost:8000
pnpm dev
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| DATABASE_URL | Yes | PostgreSQL connection string |
| REDIS_URL | Yes | Redis for Celery queue |
| POSTGRES_DB | Yes | Database name |
| POSTGRES_USER | Yes | Database user |
| POSTGRES_PASSWORD | Yes | Database password |
| ODDS_API_KEY | No | The Odds API key for live odds |
| X_AUTH_TOKEN | No | X auth cookie for social scraping |
| X_CT0 | No | X csrf cookie for social scraping |
| NEXT_PUBLIC_SPORTS_API_URL | Yes (web) | API base URL for frontend |
| RUN_MIGRATIONS | No | Run Alembic on startup (default: false) |

## Troubleshooting

### API won't start

Check the logs:
```bash
docker logs sports-api
```

Common issues:
- Database not ready: wait for postgres healthcheck
- Migration error: check Alembic version mismatch
- Import error: rebuild the container

### Scraper returns empty results

For social scraping:
1. Check X cookies are valid (they expire)
2. Verify X_AUTH_TOKEN and X_CT0 in .env
3. Rebuild scraper: docker compose --profile dev up -d --build scraper

### Database connection refused

- Ensure postgres is running: docker ps | grep postgres
- Check the host: Docker uses host.docker.internal for host machine
- Verify credentials in .env

### Restoring a DB backup (local)

The `infra/scripts/restore.sh` helper is **destructive** and guarded by `CONFIRM_DESTRUCTIVE=true`.
On Postgres 16+ it uses `DROP DATABASE ... WITH (FORCE)` so you typically don’t need to stop services first.
