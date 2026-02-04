# Changelog

All notable changes to Sports Data Admin.

## [2026-02-03] - Current

### Pipeline Enhancements

- **8-stage pipeline**: Added ANALYZE_DRAMA stage between VALIDATE_MOMENTS and GROUP_BLOCKS
- **Drama-weighted block distribution**: AI identifies dramatic peak quarters and weights block allocation accordingly
- **Mini box scores per block**: Each narrative block now includes cumulative stats with segment deltas
- **Fail-fast error handling**: Removed fallback narratives; pipeline fails on errors instead of degrading silently

### NBA PBP Migration

- **NBA API for PBP**: NBA play-by-play now uses the official NBA API instead of Sports Reference
- **Schedule integration**: Games matched via NBA schedule API to obtain game IDs

---

## [2026-02-01]

### Story Compression Overhaul

- **Larger moments**: Increased from 1-5 plays to 15-50 plays per moment (70-80% reduction in moment count)
- **Richer narratives**: Expanded from 3-4 sentences to 2-3 paragraphs (6-10 sentences) per moment
- **Cumulative box scores**: Each moment now includes a running player stats snapshot
- **Smaller batches**: Reduced OpenAI batching from 15 to 5 moments per call for longer outputs
- **More explicit plays**: Increased from 2 to 5 explicitly narrated plays per moment

### Technical Changes

- `SOFT_CAP_PLAYS`: 8 → 30
- `ABSOLUTE_MAX_PLAYS`: 12 → 50
- `MIN_PLAYS_BEFORE_SOFT_CLOSE`: 5 → 15
- `MAX_EXPLICIT_PLAYS_PER_MOMENT`: 2 → 5
- `MOMENTS_PER_BATCH`: 15 → 5

---

## [2026-01-28]

### NCAAB Enhancements

- **Batch API fetching**: Reduced CBB API calls from 2 per game to 2 per date range
- **API response caching**: Added JSON caching for NCAAB and NHL API responses
- **Event type normalization**: Comprehensive NCAAB event type mapping for PBP

### Architecture

- **Condensed Moment Story Model**: Stories are ordered lists of condensed moments backed by specific plays
- **Multi-Stage Pipeline**: NORMALIZE_PBP → GENERATE_MOMENTS → VALIDATE_MOMENTS → RENDER_NARRATIVES → FINALIZE_MOMENTS
- **Deterministic Segmentation**: Moment boundaries are mechanical, AI is prose-only
- **Full Traceability**: Every narrative sentence maps to specific plays

### Features

- FastAPI admin API with story generation endpoints
- Celery scraper workers for NBA, NHL, NCAAB data
- Next.js admin UI for data browsing and story generation
- Sports Reference boxscore and PBP scraping
- NHL official API integration (schedule, PBP, boxscores)
- NCAAB College Basketball Data API integration
- The Odds API integration with local JSON caching
- Social media scraping from X/Twitter team accounts
- PostgreSQL with JSONB stats storage

### Documentation

- [STORY_CONTRACT.md](STORY_CONTRACT.md) - Authoritative story specification
- [STORY_PIPELINE.md](STORY_PIPELINE.md) - Pipeline stages and implementation
- [NARRATIVE_TIME_MODEL.md](NARRATIVE_TIME_MODEL.md) - Timeline ordering model
