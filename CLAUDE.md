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

**Architecture:** Block-based narratives via 8-stage pipeline

A story consists of 4-7 narrative blocks. Each block contains 2-4 sentences (~65 words) with a semantic role (SETUP, MOMENTUM_SHIFT, RESOLUTION, etc.). Target read time: 60-90 seconds.

**Contract:** See `docs/STORY_CONTRACT.md`

**Key Concepts:**
- **Narrative Block:** Consumer-facing output (4-7 per game, 2-4 sentences each)
- **Moments:** Internal traceability layer linking blocks to plays
- **Semantic Roles:** SETUP, MOMENTUM_SHIFT, RESPONSE, DECISION_POINT, RESOLUTION
- **Guardrails:** Hard limits enforced (blocks ≤ 7, tweets ≤ 5, words ≤ 350)
- **Social Independence:** Story structure identical with/without social data
- **OpenAI is prose-only:** It renders narratives, not structure

**Pipeline Stages:**
```
NORMALIZE_PBP → GENERATE_MOMENTS → VALIDATE_MOMENTS → ANALYZE_DRAMA → GROUP_BLOCKS → RENDER_BLOCKS → VALIDATE_BLOCKS → FINALIZE_MOMENTS
```

**Code:** `api/app/services/pipeline/`

## Scheduled Scraping

**Daily Schedule (US Eastern Time):**
- **5:00 AM** — Sports ingestion + daily sweep (NBA → NHL → NCAAB sequentially)
- **6:30 AM** — NBA flow generation (90 min after ingestion)
- **6:45 AM** — NHL flow generation (15 min after NBA)
- **7:00 AM** — NCAAB flow generation (15 min after NHL, max 10 games)

**Recurring Tasks:**
- **Every 3 min** — Game state updates (game-state-machine)
- **Every 5 min** — Live PBP polling
- **Every 30 min** — Odds sync + active odds polling (all leagues, keeps FairBet data fresh)

Configured in `scraper/sports_scraper/celery_app.py`

## Data Sources by League

| League | Boxscores | Play-by-Play | Game Matching |
|--------|-----------|--------------|---------------|
| NBA | Basketball Reference | NBA API | `source_game_key` (e.g., `202601290ATL`) |
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
