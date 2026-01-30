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
