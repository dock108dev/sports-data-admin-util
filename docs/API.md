# API

FastAPI service for sports data administration.

## Quick Start

```bash
pip install -r requirements.txt
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/sports"
export REDIS_URL="redis://localhost:6379/2"
uvicorn main:app --reload --port 8000
```

## Endpoints

- `GET /healthz` — Liveness + database readiness check (returns 503 when dependencies fail)
- `GET /docs` — OpenAPI documentation
- `GET /api/admin/sports/games` — List games
- `GET /api/admin/sports/games/{id}` — Game detail
- `POST /api/admin/sports/scraper/runs` — Create scrape job
- `GET /api/social/posts/game/{id}` — Social posts for game

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL (asyncpg driver) |
| `REDIS_URL` | Yes | Redis for Celery broker |

See the [root README](../README.md) for setup details and the [docs index](INDEX.md) for more guides.

### Health Response Shape

```json
{
  "status": "ok",
  "app": "ok",
  "db": "ok"
}
```
