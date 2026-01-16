# AGENTS.md — Sports Data Admin

> This file provides context for AI agents (Codex, Cursor, Copilot) working on this codebase.

## Quick Context

**What is this?** Backend infrastructure for Scroll Down Sports: API, data scraper, admin UI.

**Tech Stack:**
- API: Python, FastAPI, PostgreSQL
- Scraper: Python, uv
- Web Admin: React, TypeScript

**Key Directories:**
- `api/` — FastAPI backend
- `scraper/` — Python data scraper
- `web/` — Admin UI (React/TypeScript)
- `sql/` — Database schema and migrations
- `infra/` — Docker and deployment

## Core Principles

1. **Stability over speed** — Downstream apps depend on this
2. **Predictable schemas** — No silent changes
3. **Zero silent failures** — Log everything
4. **Traceable changes** — Every transformation explainable

## Consumers

This backend serves:
- `scroll-down-app` (iOS)
- `scroll-down-sports-ui` (Web)

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

## Contract

This API implements `scroll-down-api-spec`. Schema changes require:
1. Update spec first
2. Then update implementation
3. Document breaking changes

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


