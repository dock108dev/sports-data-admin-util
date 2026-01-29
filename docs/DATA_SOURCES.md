# Data Sources & Ingestion

This document describes where data comes from and how it's ingested.

## Overview

| Data Type | Source | Leagues | Update Frequency |
|-----------|--------|---------|------------------|
| Boxscores | Sports Reference | NBA | Post-game |
| Boxscores | CBB Stats API | NCAAB | Post-game |
| Boxscores | NHL API | NHL | Post-game |
| Play-by-Play (Historical) | Sports Reference | NBA, NCAAB | Post-game |
| Play-by-Play (Live) | League APIs | NBA, NHL | During game (15s polling) |
| Odds | The Odds API | NBA, NHL, NCAAB | Pre-game + live |
| Social | X/Twitter | NBA, NHL | 24-hour game window |

## Boxscores & Player Stats

### Source
- **NBA**: basketball-reference.com
- **NHL**: NHL API (`api-web.nhle.com/v1/gamecenter/{game_id}/boxscore`)
- **NCAAB**: CBB Stats API (`/games/teams`, `/games/players`) with date range batching

### Data Collected
- Team stats (points, rebounds, assists, etc.)
- Player stats (minutes, points, shooting percentages, etc.)
- Final scores

### Storage
- `sports_team_boxscores` - Team-level stats (JSONB)
- `sports_player_boxscores` - Player-level stats (JSONB)
- `sports_games` - Final scores updated

### Timing
- Scraped after game status changes to `final`
- Automatic ingestion runs daily at 9:00 UTC (4 AM EST / 5 AM EDT)
- Manual scraping available via Admin UI

## Play-by-Play

### Historical (Sports Reference) - NBA/NCAAB

**Source:**
- **NBA**: `basketball-reference.com/boxscores/pbp/{game_id}.html`
- **NCAAB**: `sports-reference.com/cbb/boxscores/{game_id}.html`

**Format:** HTML tables with quarter headers and play rows

**Parsing:**
- Quarter detection from header rows (`q1`, `q2`, etc.)
- Sequential `play_index` from HTML row order
- Clock preserved as-is from table
- Scores extracted when available
- Description concatenated from away/home columns

**Storage:** `sports_game_plays`

**Implementation:**
- `scraper/sports_scraper/scrapers/nba_sportsref.py`
- `scraper/sports_scraper/scrapers/ncaab_sportsref.py`

See also:
- [pbp-nba-review.md](pbp-nba-review.md) - NBA PBP implementation details
- [pbp-ncaab-sports-reference.md](pbp-ncaab-sports-reference.md) - NCAAB PBP details

### Live Feeds / NHL API

**NBA:**
- Source: `cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json`
- Polling: Every 15 seconds during live games
- Implementation: `scraper/sports_scraper/live/nba.py`

**NHL (All PBP + Boxscores):**
- PBP Source: `api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play`
- Boxscore Source: `api-web.nhle.com/v1/gamecenter/{game_id}/boxscore`
- Polling: Every 15 seconds during live games
- Implementation: `scraper/sports_scraper/live/nhl.py`

NHL uses the official NHL API for ALL data (schedule, PBP, boxscores) rather than web scraping.

**Play Index Calculation:**
- Live feeds use `period * 10000 + actionNumber` for stable ordering
- Guarantees chronological order even with late updates

**Clock Parsing:**
- NBA: `PT11M22.00S` → `11:22`
- NHL: Clock extracted from play data

## Odds

### Source
The Odds API (v4): `https://api.the-odds-api.com`

### Endpoints
- **Live**: `/sports/{sport}/odds` - Today and future games
- **Historical**: `/historical/sports/{sport}/odds` - Past dates

### Markets
- **Spread** (`spreads`) - Point spread with price
- **Total** (`totals`) - Over/under with price
- **Moneyline** (`h2h`) - Win/loss odds

### Bookmakers
- Configurable via `include_books` parameter
- If unset, all bookmakers returned by API are accepted
- Common books: DraftKings, FanDuel, BetMGM, Caesars

### Game Matching
1. Try exact team ID match (home/away and away/home)
2. Fall back to normalized team name matching (NCAAB only)
3. If no match, log warning and skip

### Storage
- `sports_game_odds` table
- Unique constraint: `(game_id, book, market_type, side, is_closing_line)`
- Upsert strategy: `ON CONFLICT DO UPDATE`

### Rate Limiting
- Historical endpoint: 5-day delay between requests (API rate limits)
- Caching: Per-league, per-date JSON files under scraper cache

### Implementation
- Client: `scraper/sports_scraper/odds/client.py`
- Sync: `scraper/sports_scraper/odds/synchronizer.py`
- Persistence: `scraper/sports_scraper/persistence/odds.py`

See also:
- [odds-nba-ncaab-review.md](odds-nba-ncaab-review.md) - NBA/NCAAB odds details
- [odds-nhl-validation.md](odds-nhl-validation.md) - NHL odds validation

## Social Media (X/Twitter)

### Source
X/Twitter via Playwright browser automation

### Collection Window
- **Start**: 5:00 AM ET on game day
- **End**: 4:59 AM ET next day (24-hour window)

### Accounts
- Official team accounts only (no players, no media)
- Registry: `team_social_accounts` table
- Fallback: `sports_teams.x_handle` column

### Search Strategy
X advanced search: `from:<handle> since:<date> until:<date>`

### Authentication
Requires X session cookies:
- `X_AUTH_TOKEN` - Auth token from logged-in session
- `X_CT0` - CSRF token

Get from browser: Dev Tools → Application → Cookies → x.com

### Filtering
- **Retweets**: Excluded via `data-testid="socialContext"` check
- **Spoilers**: Posts with scores/results flagged with `reveal_risk` + `reveal_reason`
- **Replies**: May be included if returned by search (not explicitly filtered)

### Spoiler Detection
Conservative patterns in `api/app/utils/reveal_utils.py`:
- Score patterns: `110-105`, `W 110-105`
- Result words: "final", "recap", "highlights"
- Safe patterns whitelisted: "game day", "let's go", etc.

### Deduplication
- Primary: `external_post_id` + `platform`
- Fallback: `post_url`
- Existing posts updated in place (timestamps, text, media, reveal flags)

### Rate Limiting
- In-memory limiter: 300 requests / 15 minutes
- DB-backed cache: `social_account_polls` prevents repeated polling

### Storage
- `game_social_posts` table
- Fields: `post_url`, `posted_at`, `tweet_text`, `has_video`, `video_url`, `image_url`, `media_type`, `reveal_risk`, `reveal_reason`

### Implementation
- Collector: `scraper/sports_scraper/social/collector.py`
- Playwright: `scraper/sports_scraper/social/playwright_collector.py`
- Registry: `scraper/sports_scraper/social/registry.py`
- Reveal utils: `api/app/utils/reveal_utils.py` (shared with API)

See also:
- [X_INTEGRATION.md](X_INTEGRATION.md) - X/Twitter integration architecture
- [social-nba-review.md](social-nba-review.md) - NBA social implementation
- [social-nhl.md](social-nhl.md) - NHL social accounts

## Scraper Execution

### Automatic (Scheduled)
- **Scheduler**: Celery Beat
- **Ingestion**: Daily at 9:00 UTC (4 AM EST) - boxscores, odds, PBP, social
- **Timeline Generation**: Daily at 10:30 UTC (5:30 AM EST) - 90 min after ingestion
- **Story Generation**: Daily at 10:45 UTC (5:45 AM EST) - 15 min after timeline gen
- **Window**: Yesterday through today (catches overnight game completions)

### Manual (Admin UI)
- Create scrape run via `/api/admin/sports/scraper/runs`
- Specify: league, date range, data types, bookmakers
- Job queued to Celery worker
- Status tracked in `sports_scrape_runs` table

### Execution Flow
```
1. Create SportsScrapRun record (status: pending)
2. Enqueue run_scrape_job task
3. Worker picks up job
4. Fetch data from sources
5. Normalize and persist to database
6. Update run status (completed/failed)
7. Log metrics (games processed, errors)
```

### Error Handling
- Transient errors: Logged, job continues
- Fatal errors: Job marked failed, error_summary recorded
- Partial success: Some games may succeed even if others fail

## Data Quality

### Team Name Normalization
- `scraper/sports_scraper/normalization/__init__.py`
- Maps external team names to canonical database names
- Exhaustive for NBA, partial for NCAAB (by design)

### Validation
- Required fields checked before persistence
- Invalid data logged but not persisted
- Duplicate detection via unique constraints

### Monitoring
- `sports_scrape_runs` table tracks all executions
- `sports_job_runs` table tracks post-processing (timeline generation)
- Logs include game counts, error summaries, duration

## See Also

- [ADDING_NEW_SPORTS.md](ADDING_NEW_SPORTS.md) - Adding new leagues and scrapers
- [DATABASE_INTEGRATION.md](DATABASE_INTEGRATION.md) - Database schema and queries
- [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md) - Production operations
