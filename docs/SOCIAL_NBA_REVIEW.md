# NBA X (Twitter) Social Integration Review

## Overview

The NBA social integration is a scraper-driven X (Twitter) workflow that attaches official **team** posts to game timelines. It is a **team-only** system (no player accounts), runs inside the scraper service, and persists results to shared database tables used by the API.

## Core Components

### Collection Orchestrator
- **`scraper/sports_scraper/social/team_collector.py`**
  - `TeamTweetCollector` collects tweets for teams with games in a date range.
  - Uses a **two-scrape-per-game** model:
    - **Scrape #1 (final-whistle):** Triggered when a game transitions to FINAL via the game-state-machine. Collects tweets for both teams immediately after the game ends.
    - **Scrape #2 (daily sweep):** Runs as part of the daily sweep at 5:00 AM EST. Catches any tweets missed by Scrape #1 (late posts, delayed publishing).
  - Posts are saved to `team_social_posts` with `mapping_status='unmapped'`, then mapped to games (setting `mapping_status='mapped'` with `game_id` populated).

### Collector Strategy (Playwright)
- **`scraper/sports_scraper/social/playwright_collector.py`**
  - Uses X advanced search: `from:<handle> since:<date> until:<date>`.
  - Uses X cookies (`X_AUTH_TOKEN`, `X_CT0`) for access to historical search.
  - Filters out **retweets** via `data-testid="socialContext"`.
  - Extracts: post URL, timestamp, text, image/video signals.
  - Does **not** explicitly filter replies (replies may be included if returned by search).

### Registry & Handles
- **`scraper/sports_scraper/social/registry.py`**
  - `team_social_accounts` registry is queried first; fallback is `sports_teams.x_handle`.
  - Seed data for NBA is stored in `sql/003_seed_nba_x_handles.sql` and can be inserted into `team_social_accounts` via `sql/008_seed_team_social_accounts.sql`.

### Reveal/Outcome Filtering
- **`api/app/utils/reveal_utils.py`** (Shared with Scraper)
  - Posts are **not deleted** but flagged with `reveal_risk` + `reveal_reason`.
  - Score/final/recap patterns are detected and labeled.
  - Conservative default: if text is missing or ambiguous, posts are flagged as reveal risk.

### Deduplication & Updates
- Deduplication is done by:
  1. `external_post_id` + `platform` (preferred), or
  2. `post_url` fallback.
- Existing posts are updated in place (timestamps, text, media fields, reveal flags).

### Rate Limiting & Polling Cache
- **`scraper/sports_scraper/social/rate_limit.py`**: in-memory rate limiter (default 300 requests / 15 minutes).
- **`scraper/sports_scraper/social/cache.py`**: DB-backed request cache (`social_account_polls`) to avoid repeated polling within a window.

## Storage Model

The NBA social pipeline writes into shared tables (used by all leagues):

- `team_social_posts` (raw collected tweets + mapped game associations)
- `team_social_accounts`
- `social_account_polls`

These are defined in `sql/000_sports_schema.sql` + related migrations and mapped in `api/app/db_models.py`.

## NBA-Specific Assumptions (To Mirror for NHL)

- **Team-only accounts.** NBA integration uses official team accounts; no players, league, or media.
- **Search-based scraping.** X advanced search with date-bounded query is the canonical mechanism.
- **Retweets excluded, replies not explicitly filtered.**
- **Spoiler filtering is conservative** and uses the shared reveal filter.
- **No cross-sport data mixing** because posts are attached to game/team IDs, not a league field on the social posts.
- **No PBP ↔ social matching.** Social posts are stored independently and are not aligned to specific play-by-play events.

## Required Parity for NHL

When mirroring NBA behavior, NHL integration must:
- Use the same search-and-scrape strategy (Playwright).
- Use team-only X handles sourced from the team registry or `x_handle`.
- Apply identical reveal filtering and dedupe semantics.
- Reuse the same rate limiter + polling cache policies.
- Persist to the same `team_social_posts` structure.
