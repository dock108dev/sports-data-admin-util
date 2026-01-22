# AGENTS.md — Sports Data Admin

> This file provides context for AI agents (Codex, Cursor, Copilot) working on this codebase.

## Quick Context

**What is this?** Centralized sports data hub for all Dock108 apps. Automated ingestion, normalization, and serving of sports data.

**Purpose:**
- Single source of truth for sports data across Dock108 products
- Automated scraping from ESPN, Hockey Reference, Sports Reference
- Normalized API for multi-sport data (NBA, NHL, NCAAB)
- Narrative story generation for Scroll Down Sports
- Admin UI for data management and monitoring

**Tech Stack:**
- API: Python, FastAPI, PostgreSQL
- Scraper: Python, uv, Celery
- Web Admin: React, TypeScript, Next.js
- Story Generation: Chapters-first architecture

**Key Directories:**
- `api/` — FastAPI backend (REST API, story generation)
- `api/app/services/chapters/` — Story generation system (Scroll Down Sports)
- `scraper/` — Multi-sport data scraper
- `web/` — Admin UI (data browser, story generator, scraper management)
- `sql/` — Database schema and migrations
- `infra/` — Docker and deployment
- `docs/` — Architecture and API documentation

## Core Principles

1. **Stability over speed** — Downstream apps depend on this
2. **Predictable schemas** — No silent changes
3. **Zero silent failures** — Log everything
4. **Traceable changes** — Every transformation explainable
5. **Structure before narrative** — Chapters are deterministic, AI adds meaning
6. **No future knowledge** — AI sees only prior chapters during generation

## Consumers

This data hub serves all Dock108 sports products:
- **Scroll Down Sports** (iOS, Web) — Narrative game stories
- **Other Dock108 apps** — Normalized sports data API

## Data Provided

**Core Data Types:**
- Play-by-play (full game timelines)
- Box scores (team and player stats)
- Betting odds (multiple books, closing lines)
- Social media (team highlights, reactions)
- Game metadata (schedules, scores, standings)

**Sports Supported:**
- NBA (full coverage)
- NHL (full coverage)
- NCAAB (full coverage)

## Story Generation System (Scroll Down Sports)

**Architecture:** Chapters-First

A game is a book. Plays are pages. Chapters are scenes.

**Pipeline:**
```
Play-by-Play → ChapterizerV1 → Chapters → StoryState → AI → GameStory
```

**Key Concepts:**
- **Chapter:** Contiguous play range, structural unit, deterministic
- **StoryState:** Running context from prior chapters only
- **GameStory:** Complete output with chapters + summaries + compact story

**Rules:**
- Chapters are structural, not narrative
- AI never defines boundaries
- No future knowledge during sequential generation
- Reason codes explain every boundary

See `docs/BOOK_CHAPTERS_MODEL.md` for details.

## Coding Standards

See `.cursorrules` for complete standards. Key points:

### Python
- Type hints on all functions
- Pydantic models for validation
- Log errors with context
- Never swallow exceptions

### TypeScript (Web)
- No `any` types
- Functional components

## API Contract

This system serves multiple Dock108 products. Schema changes require:
1. Update spec first (if spec exists)
2. Then update implementation
3. Document breaking changes
4. Notify consuming teams

**Primary API:** REST endpoints for normalized sports data  
**Story API:** Chapters-first narrative generation (Scroll Down Sports)

## Do NOT

- **Auto-commit changes** — Wait for user to review and commit manually
- Run commands that require interactive input to quit
- Run long-running commands (>5 seconds) without verbose logging (use logging that outputs every 30 seconds or so)
- Update code on remote servers through SSH unless specifically asked — all code changes should be done locally and applied through approved channels only
- Make breaking API changes without spec update
- Ignore or swallow errors
- Add dependencies casually
- Modify data schemas without migration

## Development

```bash
# API
cd api && pip install -r requirements.txt
uvicorn main:app --reload

# Scraper
cd scraper && uv sync
uv run python -m bets_scraper

# Web
cd web && npm install && npm run dev
```

## Database

```bash
# Run migrations
cd api && alembic upgrade head
```
