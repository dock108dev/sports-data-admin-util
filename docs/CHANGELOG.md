# Changelog

All notable changes to Sports Data Admin.

## [2026-01-17]

### Added
- **Moments/Highlights system**: Replaced legacy segments with grounded moments
  - Each game timeline is partitioned into contiguous, non-overlapping moments
  - Moments are typed: NEUTRAL, RUN, LEAD_BATTLE, CLOSING_STRETCH
  - Notable moments (is_notable=True) become highlights
  - Player stats (pts, ast, blk, stl) extracted per moment
- **Timeline management UI**: Admin page for generating and regenerating timelines
  - List games missing timelines
  - List existing timelines with regeneration options
  - Batch generation and per-game regeneration
- **Sports SSOT configuration**: Centralized league config in `config_sports.py`
  - Eliminated hardcoded "NBA" defaults throughout codebase
  - Per-league feature flags (pbp, social, timeline, odds)
  - Required `league_code` parameters with validation
- **Post-scrape timeline generation**: Automatically generates timelines for all games missing them after each scrape job completes (no date limit)

### Changed
- Moments API returns chronological order (by start_play_id), not importance ranking
- `GET /games/{id}/highlights` returns filtered view of moments (is_notable=True)
- `GET /games/{id}/moments` returns all moments (full timeline coverage)
- Timeline generation processes ALL games missing timelines (removed 7-day lookback limit)
- Consolidated DEPLOYMENT.md and DEPLOYMENT_SETUP.md

### Removed
- Legacy segments/highlights terminology
- "Stale timeline" concept (timelines don't go stale after game is final)
- Hardcoded "NBA" defaults in scheduler, tasks, and API endpoints
- Empty directories and unused files

## [Unreleased]

### Added
- Reading position storage endpoints for tracking user progress through games
- Score redaction filter for reveal-safe summaries and posts
- Score checkpoint integration to API
- AI summary retrieval endpoint for compact moments
- AI summary generator service for moments (OpenAI with fallback)
- Compact moment posts endpoint
- Compact moment PBP slice endpoint
- Compact moments endpoint (`GET /games/{id}/compact`)
- Finalized game timeline artifacts with NBA timeline generation + read endpoint
- Game analysis JSON for segmented timelines and highlight extraction
- `game_reading_positions` table for storing user read positions
- `compact_mode_thresholds` table with per-sport defaults
- `updated_at` columns on `game_social_posts` and `sports_game_plays`
- Social post content fields: `tweet_text`, `video_url`, `image_url`, `source_handle`, `media_type`
- Twitter embed widget for video posts in admin UI
- Pagination for social posts (10 per page)
- Live feed polling for NBA/NHL status updates
- Live play-by-play ingestion with append-only event storage
- NHL team X handle registry with validation helper
- NHL play-by-play ingestion via Hockey-Reference
- Production Docker Compose profile

### Changed
- Docker compose now connects to host database via `host.docker.internal`
- Auto-migrations disabled by default (`RUN_MIGRATIONS=false`)
- Migrations are now run explicitly via the `migrate` compose service
- Destructive restore utilities now require `CONFIRM_DESTRUCTIVE=true`
- Social scraper performs upsert (updates existing posts)
- Ingestion config simplified to data type toggles + shared filters
- NBA timeline synthesis now treats regulation and halftime as separate fixed blocks

### Fixed
- Fixed compact mode threshold model restoration
- Fixed timezone handling in social scraper
- Fixed duplicate Twitter embeds in React StrictMode

## [2024-12-30]

### Added
- Play-by-play (PBP) functionality with quarter pagination
- Social media scraping from X/Twitter team accounts
- X authentication via cookies for historical search
- Spoiler filtering for social posts
- Admin UI game detail with collapsible sections
- Feature flags for experimental features

### Changed
- Moved documentation to `/docs` folder
- Added structured logging throughout

## [2024-12-01]

### Added
- Initial release
- FastAPI admin API
- Celery scraper workers
- Next.js admin UI
- Sports Reference boxscore scraping
- The Odds API integration
- PostgreSQL with JSONB stats storage
