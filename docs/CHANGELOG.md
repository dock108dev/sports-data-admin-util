# Changelog

All notable changes to Sports Data Admin are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- **Game reading positions table** — Tracks user scroll position for game detail views
- **Compact mode thresholds** — Configurable thresholds per sport for compact play-by-play
- **Social post rich media fields** — `tweet_text`, `image_url`, `video_url`, `source_handle`, `media_type`
- **`updated_at` timestamps** — Added to all major tables for staleness tracking
- **Social post upsert** — Rescraping now updates existing posts instead of skipping
- **Paginated social posts** — Admin UI shows 10 posts per page with navigation
- **Hybrid social rendering** — Twitter embed for videos, custom cards for images/text

### Changed
- **Simplified scrape run config** — Replaced `include_X`/`backfill_X` with data type toggles and shared filters
- **Scraper filters** — Added `only_missing` and `updated_before` options for targeted rescrapes
- **Documentation rewrite** — Clarified platform purpose and updated outdated schemas

### Fixed
- Video URL extraction for social posts
- React StrictMode duplicate embed prevention
- Collapsible sections now default to collapsed

---

## [2024-12-26] — Initial Documented Release

### Added
- Compact play-by-play slice endpoint for admin games
- Game preview score endpoint
- Summary cache hit-rate tracking
- Spoiler redaction logging for compact summaries

### Changed
- Split sports admin router modules to reduce file sizes
- Consolidated sports admin API client types into modular helpers
- Moved root docs into `/docs` directory
- Added local development guide

### Infrastructure
- Docker Compose profiles for dev/prod
- Alembic migrations for schema management
- Nginx admin-only configuration template
