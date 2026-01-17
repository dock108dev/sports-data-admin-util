# Quick Start - Running Locally

## Prerequisites

- Docker and Docker Compose installed
- At least 4GB RAM available for Docker

## Quick Start (Recommended)

```bash
cd infra
cp .env.example .env
docker compose --profile dev up -d --build
```

**Access:**
- Admin UI: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/healthz

## What Just Happened?

The Docker Compose setup starts:
1. **PostgreSQL** - Database (port 5432)
2. **Redis** - Celery broker (port 6379)
3. **API** - FastAPI backend (port 8000)
4. **Scraper Worker** - Celery worker for data ingestion
5. **Scraper Beat** - Celery scheduler (13:00-02:00 UTC, every 15 min)
6. **Web** - Next.js admin UI (port 3000)

## Verify Everything Works

```bash
# Check all services are running
docker compose ps

# Check API health
curl http://localhost:8000/healthz

# Check logs
docker compose logs -f api
docker compose logs -f scraper-worker
docker compose logs -f web
```

## Run Database Migrations

```bash
# If this is first time, run migrations
docker compose exec api alembic upgrade head
```

## Manual Setup (Alternative)

If you prefer to run services individually:

### 1. API
```bash
cd api
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://user:pass@localhost:5432/sports_data"
export ENVIRONMENT="development"

# Run migrations
alembic upgrade head

# Start API
uvicorn main:app --reload --port 8000
```

### 2. Scraper
```bash
cd scraper
uv sync

# Start Celery worker
uv run celery -A bets_scraper.celery_app worker --loglevel=info

# Start Celery beat (scheduler)
uv run celery -A bets_scraper.celery_app beat --loglevel=info
```

### 3. Web Admin
```bash
cd web
npm install
npm run dev
```

## Environment Variables

Key variables in `infra/.env`:

```bash
# Database
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/sports_data

# Environment
ENVIRONMENT=development

# Optional: AI enrichment
OPENAI_API_KEY=your_key_here

# Optional: Odds ingestion
ODDS_API_KEY=your_key_here

# Optional: X/Twitter scraping
X_AUTH_TOKEN=your_token_here
X_CT0=your_ct0_here
```

## Troubleshooting

### Services won't start
```bash
# Check Docker resources
docker system df

# Clean up old containers
docker compose down -v
docker compose up -d --build
```

### Database connection errors
```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check logs
docker compose logs postgres
```

### API import errors
```bash
# Rebuild API container
docker compose build api
docker compose up -d api
```

### Port already in use
```bash
# Find what's using the port
lsof -i :8000  # or :3000, :5432, etc.

# Stop the conflicting service or change ports in docker-compose.yml
```

## Next Steps

1. **Explore Admin UI**: http://localhost:3000
2. **Browse API Docs**: http://localhost:8000/docs
3. **Trigger a scrape**: Use the admin UI to create a scrape run
4. **View data**: Browse games, teams, and timeline artifacts

## Development Workflow

```bash
# Make code changes...

# Restart affected service
docker compose restart api        # For API changes
docker compose restart web        # For web changes
docker compose restart scraper-worker  # For scraper changes

# View logs
docker compose logs -f api

# Run tests
docker compose exec api pytest tests/ -v
```

## Stopping Services

```bash
# Stop all services
docker compose down

# Stop and remove volumes (clean slate)
docker compose down -v
```

## See Also

- [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md) - Detailed development setup
- [INFRA.md](INFRA.md) - Infrastructure details
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment
- [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md) - Operations guide
