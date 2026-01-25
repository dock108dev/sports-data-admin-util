# Changelog

All notable changes to Sports Data Admin.

## [2026-01-24] - Current

### Architecture

- **Chapters-First Story Generation**: Games are split into structural chapters based on periods, timeouts, and reviews
- **Single AI Call**: One AI call renders the complete story from structured sections
- **Beat Classification**: 9 beat types (FAST_START, BACK_AND_FORTH, EARLY_CONTROL, RUN, RESPONSE, STALL, CRUNCH_SETUP, CLOSING_SEQUENCE, OVERTIME)
- **Deterministic Pipeline**: Everything is deterministic until final AI rendering

### Features

- FastAPI admin API with story generation endpoints
- Celery scraper workers for NBA, NHL, NCAAB data
- Next.js admin UI for data browsing and story generation
- Sports Reference boxscore and PBP scraping
- NHL live feed integration
- The Odds API integration
- Social media scraping from X/Twitter team accounts
- PostgreSQL with JSONB stats storage

### Documentation

- [BOOK_CHAPTERS_MODEL.md](BOOK_CHAPTERS_MODEL.md) - Story generation architecture
- [NBA_BOUNDARY_RULES.md](NBA_BOUNDARY_RULES.md) - Chapter boundary rules for NBA
- [AI_SIGNALS_NBA.md](AI_SIGNALS_NBA.md) - AI signal definitions
