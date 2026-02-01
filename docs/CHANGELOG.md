# Changelog

All notable changes to Sports Data Admin.

## [2026-01-28] - Current

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
