# Data Sources & Ingestion

This document describes where data comes from and how it's ingested.

## Overview

| Data Type | Source | Leagues | Update Frequency |
|-----------|--------|---------|------------------|
| Boxscores | Sports Reference | NBA | Post-game |
| Boxscores | CBB Stats API | NCAAB | Post-game |
| Boxscores | NHL API | NHL | Post-game |
| Play-by-Play | NBA API / NHL API / CBB API | NBA, NHL, NCAAB | Post-game |
| Play-by-Play (Live) | League APIs | NBA, NHL, NCAAB | During game (5 min polling) |
| Odds | The Odds API | NBA, NHL, NCAAB | Pre-game + live |
| Social | X/Twitter | NBA, NHL, NCAAB | 24-hour game window |

## Boxscores & Player Stats

### Source
- **NBA**: basketball-reference.com
- **NHL**: NHL API (`api-web.nhle.com/v1/gamecenter/{game_id}/boxscore`)
- **NCAAB**: CBB Stats API (`/games/teams`, `/games/players`) with date range batching

### NCAAB Team Mapping
NCAAB boxscore ingestion requires `cbb_team_id` in `sports_teams.external_codes` to match games to the CBB API.

**How it's populated:**
- Alembic migration fetches teams from CBB API and maps by normalized name
- Requires `CBB_STATS_API_KEY` in migrate container environment
- Configured in `infra/docker-compose.yml`

**If games aren't getting boxscores:**
1. Check `sports_teams` has `external_codes.cbb_team_id` populated
2. Verify `CBB_STATS_API_KEY` is set in `.env`
3. Re-run migrations if needed

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
- Automatic ingestion runs daily at 08:30 UTC (3:30 AM EST)
- Manual scraping available via Admin UI

## Play-by-Play

### NBA (Official NBA API)

**Source:** `cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json`

NBA uses the official NBA API for PBP ingestion. The scraper matches games using `source_game_key` and fetches PBP from the CDN.

**Parsing:**
- Each JSON action becomes a `NormalizedPlay`
- `play_index`: `period * 10000 + actionNumber` for stable ordering
- Clock parsed from ISO-8601 format (e.g., `PT11M22.00S` → `11:22`)
- `play_type`, `team_abbreviation`, `player_id`, `player_name` from action payload

**Storage:** `sports_game_plays`

**Implementation:** `scraper/sports_scraper/services/pbp_ingestion.py` → `ingest_pbp_via_nba_api`

### NCAAB (CBB Stats API)

**Source:** CBB Stats API (`/plays/game/{game_id}`)

NCAAB uses the CBB Stats API for play-by-play ingestion. Games are matched via `external_ids.cbb_game_id` in `sports_games`.

**Parsing:**
- Each API play becomes a `NormalizedPlay`
- `play_index`: `period * 10000 + sequence` for stable ordering
- Event types mapped via `ncaab_constants.py`
- Player and team attribution from API payload

**Storage:** `sports_game_plays`

**Implementation:** `scraper/sports_scraper/services/pbp_ncaab.py` → `ingest_pbp_via_ncaab_api`

### NHL (Official NHL API)

**Source:** `api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play`

NHL uses the official NHL API for ALL data (schedule, PBP, boxscores).

**Parsing:**
- Period and time from play data
- Event types mapped to normalized play types
- Player attribution when available

**Storage:** `sports_game_plays`

**Implementation:** `scraper/sports_scraper/live/nhl.py`

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
- `sports_game_odds` table (game-centric, for historical analysis)
- Unique constraint: `(game_id, book, market_type, side, is_closing_line)`
- Upsert strategy: `ON CONFLICT DO UPDATE`

### FairBet Work Table

A separate bet-centric table for cross-book odds comparison:

- `fairbet_game_odds_work` table
- **Purpose:** Store odds by bet definition (game + market + selection + line) with books as rows
- **Populated:** During odds ingestion for non-completed games only
- **Primary key:** `(game_id, market_key, selection_key, line_value, book)`
- **Note:** `line_value` of 0 is sentinel for moneylines (no line)

This table enables efficient cross-book comparison without the game-centric structure of `sports_game_odds`.

### Rate Limiting
- Historical endpoint: 1-second pause every 5 days of iteration (to avoid rate limits)
- Live games excluded from active odds polling to preserve pre-game closing lines
- Caching: Per-league, per-date JSON files under scraper cache

### Implementation
- Client: `scraper/sports_scraper/odds/client.py`
- Sync: `scraper/sports_scraper/odds/synchronizer.py`
- Persistence: `scraper/sports_scraper/persistence/odds.py`

## Social Media (X/Twitter)

### Source
X/Twitter via Playwright browser automation

### Architecture: Team-Centric Two-Phase Collection

Social collection uses a **team-centric** approach:

**Phase 1 (COLLECT):** Scrape all tweets for teams in a date range
- Tweets saved to `team_social_posts` with `mapping_status='unmapped'`
- Team-centric, not game-centric

**Phase 2 (MAP):** Map unmapped tweets to games
- Maps tweets to games based on team and posting time
- Updates `mapping_status='mapped'` and sets `game_id` on matched tweets in `team_social_posts`

This architecture allows collecting tweets once and mapping to multiple games if needed.

### Schedule

Social collection uses a two-scrape-per-game model:
- **Scrape #1 (final-whistle):** Triggered automatically when games transition to FINAL
- **Scrape #2 (daily sweep):** Runs at **4:00 AM EST** as part of the daily sweep

See `scraper/sports_scraper/celery_app.py` for schedule configuration.

### Collection Window
- **Start**: 5:00 AM ET on game day
- **End**: 8:00 AM ET next day

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
- `team_social_posts` table - Collected tweets, mapped to games via `mapping_status='mapped'` and `game_id`
- Fields: `post_url`, `posted_at`, `tweet_text`, `has_video`, `video_url`, `image_url`, `media_type`, `reveal_risk`, `reveal_reason`, `mapping_status`, `game_id`, `game_phase`, `likes_count`, `retweets_count`, `replies_count`

### Implementation
- Team Collector: `scraper/sports_scraper/social/team_collector.py`
- Tweet Mapper: `scraper/sports_scraper/social/tweet_mapper.py`
- Playwright: `scraper/sports_scraper/social/playwright_collector.py`
- Registry: `scraper/sports_scraper/social/registry.py`
- Reveal utils: `api/app/utils/reveal_utils.py` (shared with API)

See also:
- [X_INTEGRATION.md](X_INTEGRATION.md) - X/Twitter integration architecture

## Scraper Execution

### Automatic (Scheduled)
- **Scheduler**: Celery Beat
- **Ingestion**: Daily at 08:30 UTC (3:30 AM EST) - boxscores, odds, PBP
- **Daily Sweep**: Runs at 09:00 UTC (4:00 AM EST) - truth repair, social scrape #2, backfill embedded tweets (7-day lookback)
- **Flow Generation**: Runs after sweep, staggered by league (30 min apart):
  - 09:30 UTC (4:30 AM EST) - NBA flow generation
  - 10:00 UTC (5:00 AM EST) - NHL flow generation
  - 10:30 UTC (5:30 AM EST) - NCAAB flow generation (capped at 10 games)
- **Game State Updates**: Every 3 minutes
- **Live PBP Polling**: Every 5 minutes (NBA, NHL per-game; NCAAB via batch CBB API)
- **Odds Sync + Active Odds Polling**: Every 30 minutes (pregame games only; live games skipped to preserve closing lines)
- **Props Sync**: Every 30 minutes (offset at :15/:45 to avoid contention with odds sync at :00/:30)
- **Window**: Yesterday through today (catches overnight game completions)

Configuration: `scraper/sports_scraper/celery_app.py`

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
