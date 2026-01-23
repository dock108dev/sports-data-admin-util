# Cursor Rules for Sports Data Admin

**Centralized sports data hub for all Dock108 apps.**

## Core Principles
1. **Stability over speed** — All Dock108 apps depend on this
2. **Predictable schemas** — No silent changes
3. **Zero silent failures** — Log everything
4. **Traceable changes** — Every transformation explainable
5. **Single source of truth** — Normalized data across sports
6. **Structure before narrative** — (Story generation) Chapters are deterministic, AI adds meaning
7. **No future knowledge** — (Story generation) AI sees only prior chapters

## Tech Stack
- API: Python, FastAPI, PostgreSQL
- Scraper: Python, uv, Celery
- Web Admin: React, TypeScript, Next.js
- Story Generation: Chapters-first architecture (Scroll Down Sports feature)

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
- `api/app/services/chapters/` — Story generation (Scroll Down Sports feature)
- `scraper/` — Multi-sport data scraper (automated ingestion)
- `web/` — Admin UI (data browser, story generator, scraper management)
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

## Story Generation (Scroll Down Sports Feature)

**Chapters-First Pipeline:**
```
PBP → Chapterizer → Chapters → StoryState → AI → GameStory
```

**Key Concepts:**
- **Chapter:** Structural unit (contiguous play range)
- **StoryState:** Running context (prior chapters only)
- **GameStory:** Output contract (chapters + summaries + compact story)

**Rules:**
- Chapters are structural, not narrative
- AI never defines boundaries
- Reason codes explain every boundary
- No future knowledge during sequential generation

**Scope:** This is one feature of the data hub, specific to Scroll Down Sports.

## Contract
This API implements `scroll-down-api-spec`. Schema changes require:
1. Update spec first
2. Then update implementation
3. Document breaking changes

## Testing
- Add comprehensive tests for API endpoints
- Test data transformation logic
- Mock external dependencies

## Do NOT
- **Auto-commit changes** — Wait for user to review and commit manually
- Run commands that require interactive input to quit
- Run long-running commands (>5 seconds) without verbose logging (use logging that outputs every 30 seconds or so)
- Update code on remote servers through SSH unless specifically asked — all code changes should be done locally and applied through approved channels only
- Make breaking API changes without spec update
- Ignore or swallow errors
- Add dependencies casually
- Modify data schemas without migration
