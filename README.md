# Sports Data Admin

**Centralized sports data hub for all Dock108 apps.**

---

## Story Generation System Status

This branch contains the legacy flow-based recap system.

No new features will be added here.

The story generation pipeline in `api/app/services/chapters/` represents the V1 implementation, which converts play-by-play data into flow-based narrative sections.

---

Automated ingestion, normalization, and serving of sports data. Provides play-by-play, box scores, odds, and social media for NBA, NHL, and NCAAB. Powers narrative story generation for Scroll Down Sports.

## Quick Start

```bash
cd infra
cp .env.example .env
docker compose --profile dev up -d --build
```

**URLs:**
- Admin UI: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/healthz

For manual setup, see [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md).

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│ External Sources│────▶│   Scraper    │────▶│  PostgreSQL │
│ (ESPN, SportsRef)     │ (Celery/uv)  │     │    Hub      │
└─────────────────┘     └──────────────┘     └──────┬──────┘
                                                    │
                        ┌───────────────────────────┼───────────────────────────┐
                        │                           │                           │
                        ▼                           ▼                           ▼
                 ┌─────────────┐           ┌───────────────┐           ┌─────────────┐
                 │  REST API   │           │Story Generator│           │  Admin UI   │
                 │  (FastAPI)  │           │  (Chapters)   │           │  (Next.js)  │
                 └──────┬──────┘           └───────┬───────┘           └─────────────┘
                        │                          │
                        ▼                          ▼
                 ┌─────────────┐           ┌───────────────┐
                 │ Dock108 Apps│           │Scroll Down    │
                 └─────────────┘           │Sports         │
                                           └───────────────┘
```

## Tech Stack

| Component | Stack |
|-----------|-------|
| API | Python, FastAPI, PostgreSQL |
| Scraper | Python, uv, Celery, Redis |
| Admin UI | React, TypeScript, Next.js |
| Infrastructure | Docker, Caddy |

## Directory Structure

```
api/          FastAPI backend, story generation
scraper/      Multi-sport data scraper
web/          Admin UI
sql/          Database schema and migrations
infra/        Docker, deployment config
docs/         Documentation
```

## Documentation

| Guide | Description |
|-------|-------------|
| [docs/INDEX.md](docs/INDEX.md) | Full documentation index |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture |
| [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) | Development setup |
| [docs/API.md](docs/API.md) | API reference |
| [docs/BOOK_CHAPTERS_MODEL.md](docs/BOOK_CHAPTERS_MODEL.md) | Story generation system |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deployment guide |

## Contributing

See [CLAUDE.md](CLAUDE.md) for coding standards and development principles.
