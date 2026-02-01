# Cursor Rules for Sports Data Admin

**Centralized sports data hub for all Dock108 apps.**

## Core Principles
1. **Stability over speed** — All Dock108 apps depend on this
2. **Predictable schemas** — No silent changes
3. **Zero silent failures** — Log everything
4. **Traceable changes** — Every transformation explainable
5. **Single source of truth** — Normalized data across sports

## Tech Stack
- API: Python, FastAPI, PostgreSQL
- Scraper: Python, uv, Celery
- Web Admin: React, TypeScript, Next.js

## Coding Standards

### Python
- Type hints on all functions
- Pydantic models for validation
- Log errors with context
- Never swallow exceptions
- Deterministic transformations

### TypeScript (Web)
- No `any` types
- Functional components
- Strict type checking

## Directory Structure
- `api/` — FastAPI backend (REST API, data serving)
- `api/app/services/pipeline/` — Story generation pipeline (condensed moments)
- `scraper/` — Multi-sport data scraper (automated ingestion)
- `web/` — Admin UI (data browser, scraper management)
- `sql/` — Database schema and migrations
- `infra/` — Docker and deployment
- `docs/` — Architecture and API documentation

## Data Hub Responsibilities

**Primary Function:** Centralized sports data for all Dock108 apps

**Data Types:**
- Play-by-play (full game timelines)
- Box scores (team and player stats)
- Betting odds (multiple books)
- Social media (team content)

**Sports:** NBA, NHL, NCAAB

**Consumers:** All Dock108 sports products

## Story Generation

**Architecture:** Condensed moment-based narratives via multi-stage pipeline

A story is an ordered list of condensed moments. Each moment is a small set of PBP plays with at least one explicitly narrated play.

**Contract:** See `docs/STORY_CONTRACT.md`

**Key Concepts:**
- **Condensed Moment:** Small set of plays with explicit narration
- **Traceability:** Every narrative sentence maps to backing plays
- **No abstraction:** No headers, sections, or thematic groupings
- **Mechanical segmentation:** Moment boundaries are deterministic
- **OpenAI is prose-only:** It renders narratives, not structure

**Code:** `api/app/services/pipeline/`

## Scheduled Scraping

**Daily Schedule (US Eastern Time):**
- **5:30 AM** — Sports ingestion (NBA → NHL → NCAAB sequentially)
- **7:00 AM** — Timeline generation (90 min after ingestion)
- **7:15 AM** — NBA flow generation (15 min after timeline)

Configured in `scraper/sports_scraper/celery_app.py`

## Data Sources by League

| League | Boxscores | Play-by-Play | Game Matching |
|--------|-----------|--------------|---------------|
| NBA | Basketball Reference | Basketball Reference | `source_game_key` (e.g., `202601290ATL`) |
| NHL | NHL API | NHL API | `external_ids.nhl_game_pk` |
| NCAAB | CBB API | CBB API | `external_ids.cbb_game_id` |

**NCAAB Team Mapping:** Requires `CBB_STATS_API_KEY` in migrate container to populate `sports_teams.external_codes.cbb_team_id` via Alembic migrations.

## Testing
- Add comprehensive tests for API endpoints
- Test data transformation logic
- Mock external dependencies

## Do NOT
- **Auto-commit changes** — Wait for user to review and commit manually
- Run commands that require interactive input to quit
- Run long-running commands (>5 seconds) without verbose logging
- Update code on remote servers through SSH unless specifically asked
- Make breaking API changes without spec update
- Ignore or swallow errors
- Add dependencies casually
- Modify data schemas without migration
