# AI Agent Context — Sports Data Admin

> For AI agents (Codex, Cursor, Copilot, Claude) working on this codebase.
> See [CLAUDE.md](CLAUDE.md) for complete coding standards and principles.

## Quick Context

**What:** Centralized sports data hub for Dock108 apps.

**Purpose:**
- Multi-sport data ingestion (NBA, NHL, NCAAB)
- Normalized API for all Dock108 products
- Story generation (condensed moment-based narratives)

**Tech:** Python/FastAPI (API), Python/Celery (Scraper), React/Next.js (Web)

## Key Directories

```
api/                 FastAPI backend
api/app/services/story/   Story generation system
scraper/             Multi-sport data scraper
web/                 Admin UI
docs/                Documentation
```

## Core Principles

1. **Stability over speed** — Downstream apps depend on this
2. **Predictable schemas** — No silent changes
3. **Zero silent failures** — Log everything
4. **Traceability** — Every narrative maps to specific plays

## Data Sources

- **NBA**: Basketball Reference (boxscores, PBP) — matched via `source_game_key`
- **NHL**: NHL API — matched via `external_ids.nhl_game_pk`
- **NCAAB**: CBB API — matched via `external_ids.cbb_game_id` (requires `CBB_STATS_API_KEY`)

## Scheduled Tasks

Daily at 5:30 AM EST: ingestion → 7:00 AM: timelines → 7:15 AM: flows
Config: `scraper/sports_scraper/celery_app.py`

## Do NOT

- Auto-commit changes
- Make breaking API changes without spec update
- Ignore or swallow errors
- Add dependencies casually
- Modify data schemas without migration

## Development

```bash
# API
cd api && pip install -r requirements.txt && uvicorn main:app --reload

# Scraper
cd scraper && uv sync && uv run python -m sports_scraper

# Web
cd web && npm install && npm run dev

# Database migrations
cd api && alembic upgrade head
```

See [CLAUDE.md](CLAUDE.md) for complete standards.
