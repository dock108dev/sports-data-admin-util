# Infrastructure

Docker configuration for the sports-data-admin stack.

## Quick Start

```bash
cd infra
cp .env.example .env  # Edit as needed

# Full stack (creates database)
COMPOSE_PROFILES=dev docker compose up -d --build
```

## Files

| File | Description |
|------|-------------|
| `docker-compose.yml` | Full stack with postgres, redis, api, scraper, web |
| `docker-compose.local.yml` | Connect to existing localhost postgres/redis |
| `api.Dockerfile` | FastAPI service |
| `scraper.Dockerfile` | Celery worker with Playwright |
| `web.Dockerfile` | Next.js admin UI |
| `nginx/admin.conf` | Admin-only Nginx config |
| `.env.example` | Environment template |

## URLs

| Service | URL |
|---------|-----|
| Web Admin | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

## Commands

```bash
docker compose up -d --build      # Start all
docker compose logs -f api        # View logs
docker compose down               # Stop all
docker compose down -v            # Stop and delete volumes
```

See root [README.md](../README.md) for full documentation.
