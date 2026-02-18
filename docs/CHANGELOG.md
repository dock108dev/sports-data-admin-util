# Changelog

All notable changes to Sports Data Admin.

## [2026-02-18] - Current

### Unified Odds Sync

- **`sync_all_odds` task**: Replaced three separate Celery tasks (`run_scheduled_odds_sync`, `poll_active_odds`, `run_scheduled_props_sync`) with a single unified odds sync task
- **5-minute cadence**: Odds now sync every 5 minutes (previously 30 min for mainlines, 30 min offset for props)
- **Redis lock**: `sync_all_odds` acquires a Redis lock to prevent overlapping runs
- **`OddsSynchronizer` removed from `ScrapeRunManager`**: Odds sync is now a standalone Celery beat task, no longer triggered during manual scrape runs

### Odds Browser UI

- **OddsEntry schema expansion**: Added `market_category`, `player_name`, `description` fields to the API schema and TypeScript types
- **Tabbed cross-book view**: Game detail odds section rewritten with category tabs (Mainline, Player Props, Team Props, Alternates) and cross-book comparison tables showing all sportsbooks as columns
- **Player prop search**: Search input to filter player props by player name
- **Dynamic tabs**: Only categories with data are shown; defaults to Mainline

### Tweet Mapper Floor Constraint

- **4 AM ET sports day boundary**: `get_game_window()` now floors `window_end` at 4:00 AM ET on the day after the game date, ensuring the collection window extends to the end of the sports day

### Test Fixes

- **`test_run_manager.py` / `test_services_run_manager.py`**: Removed all `OddsSynchronizer` patches and obsolete odds-specific tests to match the refactored `ScrapeRunManager`
- **`test_tweet_mapper.py`**: Updated 5 `TestGetGameWindow` expected values to account for the 4 AM ET floor constraint

---

## [2026-02-17]

### Live Boxscore Polling

- **Live boxscore ingestion**: New polling task fetches boxscores for in-progress games every 5 minutes alongside live PBP
- **`last_boxscore_at` column**: New timestamp on `sports_games` tracks when boxscore data was last refreshed
- **Active game service**: New `services/active_games.py` module centralizes live game detection for polling tasks

### NCAAB Team Normalization & Matching

- **NCAAB name normalization**: New `normalization/ncaab_teams.py` with 28 additional alias mappings for NCAAB team matching
- **Odds matching improvements**: `persistence/odds_matching.py` enhanced with fuzzy matching for NCAAB teams where canonical names differ from odds API names
- **Missing NCAAB teams seeded**: 7 HBCU/mid-major teams added to `sports_teams` (included in baseline seed data)
- **NCAAB social handles fixed**: Corrected X handles for 66 NCAAB teams (8 NULL + 58 stale)
- **Alembic squash**: Replaced 51 broken migration files (cycles, duplicates) with clean baseline + seed + linear chain

### Legacy Code Cleanup

- **Dead timeline constants removed**: `NBA_PREGAME_REAL_SECONDS`, `NBA_OVERTIME_PADDING_SECONDS`, `POSTGAME_WINDOW_HOURS`, `LEAGUE_SEGMENTS` deleted from `timeline_types.py`
- **Dead feature flags removed**: `ENABLE_AI_SOCIAL_ROLES`, `ENABLE_AI_SEGMENT_ENRICHMENT`, `ENABLE_AI_SUMMARY`, `NEXT_PUBLIC_ENABLE_INLINE_X_VIDEO` removed from `docker-compose.yml` and `.env`
- **API client hardened**: `client.ts` timeout made private, silent `{} as T` fallback replaced with explicit error throw

### Documentation

- **Accuracy fixes**: Fixed migration path in ARCHITECTURE.md, updated live PBP info in DATA_SOURCES.md, removed stale nginx reference in OPERATOR_RUNBOOK.md
- **Missing env vars documented**: Added `OPENAI_MODEL_CLASSIFICATION` and `OPENAI_MODEL_SUMMARY` to INFRA.md
- **Phase N terminology removed**: Cleaned "Phase 5"/"Phase 1"/"Phase 4" labels from gameflow README.md

---

## [2026-02-14]

### FairBet EV Framework

- **EV eligibility gating**: New `evaluate_ev_eligibility()` function with 4-check pipeline: strategy exists, sharp book present, freshness, minimum qualifying books
- **EV strategy config**: `ev_config.py` maps `(league, market_category)` → strategy with confidence tiers (high/medium/low), staleness limits, and minimum book thresholds
- **Book exclusion**: 20 offshore/promo/irrelevant books excluded at SQL level via `EXCLUDED_BOOKS`; remaining ~17 included books participate in EV calculation
- **Confidence tiers**: High (NBA/NHL mainlines), Medium (NCAAB mainlines, team props), Low (player props, alternates); player props can never be High
- **Pregame-only filter**: FairBet odds endpoint restricted to pregame games (`game_start > now`) — removed stale 4-hour live cutoff
- **Odds model expansion**: Added `market_category`, `has_fair`, `player_name`, `selection_key` columns to odds tables; new prop market support

### FairBet UI Fixes

- **CSS stacking context fix**: Replaced `filter: brightness(0.96)` hover with `background: linear-gradient()` to prevent derivation popover from being clipped by adjacent cards

### Legacy Code Cleanup

- **Deleted one-shot scripts**: `migrate_sports_data.sh`, `_team_color_data.py`, `extract_team_colors.py`, `map_ncaab_teams.py`, `harvest_cbb_abbreviations.py`
- **Cleaned legacy comments**: Removed "Phase N" labels from FlowSection.tsx, fixed misleading "Safe fallback" comments in render_blocks.py, cleaned StatusBadge.module.css comment

### Documentation

- **EV_LIFECYCLE.md**: End-to-end EV computation walkthrough from ingestion to annotation
- **EV_INFRASTRUCTURE_REVIEW.md**: Codebase review documenting assumptions, gaps, and open questions

---

## [2026-02-13]

### Mini Box Score Fix

- **Per-team score deltas**: `game_stats_helpers.py` now uses per-team score deltas instead of combined total to prevent cross-team point inflation (e.g., a player getting credited with 20 PTS when actual was 13)
- **`_compute_single_team_delta()`**: New helper that isolates home vs away scoring, with team-abbreviation matching as a tiebreaker when both scores change simultaneously
- **Score=0 fix**: Replaced `event.get("home_score") or prev_home` with explicit `None` check so a legitimate score of 0 is not treated as missing

### Legacy Code Cleanup

- **Position-based tweet system removed**: Deleted `TweetPosition` enum, `classify_tweet_position()`, `_select_with_distribution()`, `_compute_distribution()`, `enforce_embedded_caps()`, `_find_target_block()` — all dead code replaced by temporal block matching
- **Fallback name matching removed**: `game_stats_helpers.py` no longer guesses team abbreviation via player-name substring matching; players without abbreviations are skipped
- **`TYPE_CHECKING` block removed**: Cleaned empty import guard from `ncaab_boxscore.py`
- **Legacy vocabulary cleaned**: Removed "Phase N" labels from module docstrings, renamed "Old format"/"New format" to "Flat format"/"Nested format" in `ncaab_helpers.py`

### Documentation Consolidation

- **GAMEFLOW_CONTRACT.md**: Updated embedded tweet selection criteria from "early, mid, late" position distribution to temporal matching
- **CHANGELOG.md**: Removed "(Phase N)" labels from section headers
- **API.md**: Updated with enhanced scraper and team/player stats endpoints

---

## [2026-02-11]

### Team Color Management

- **`PATCH /teams/{id}/colors`**: New endpoint to update team light/dark hex colors
- **`colorLightHex`/`colorDarkHex`** on `TeamSummary` and `TeamDetail` responses
- **`get_matchup_colors()`**: Server-side color selection with perceptual distance fallback (`team_colors.py`)

### Server-Side Computation

- **Derived metrics**: 40+ metrics computed server-side (`derived_metrics.py`), returned on `GameSummary.derivedMetrics` and `GameDetailResponse.derivedMetrics`
- **Period labels**: `periodLabel` and `timeLabel` on `PlayEntry` — league-aware ("Q1", "1st Half", "P2") via `period_labels.py`
- **Play tiers**: `tier` on `PlayEntry` (1=key, 2=notable, 3=routine) and `groupedPlays` for Tier-3 collapse via `play_tiers.py`
- **Play serialization**: `teamAbbreviation` and `playerName` now included on `PlayEntry`

### Timeline Odds Integration

- **`odds_events.py`** (NEW): Odds event processing — book selection, movement detection, event building
- **Odds in timeline**: Up to 3 pregame odds events (opening_line, closing_line, line_movement) merged into unified timeline
- **Book priority**: fanduel > draftkings > betmgm > caesars
- **Movement thresholds**: spread >= 1.0 pt, total >= 1.0 pt, moneyline >= 20 cents
- **`GET /games/{id}/timeline`**: New endpoint to retrieve persisted timeline artifacts (404 if not generated)
- **Validation updated**: C3 dedup handles odds events; W4 warning for odds missing phase

### Documentation Consolidation

- **TIMELINE_ASSEMBLY.md**: Rewritten — added odds as third source, multi-league PHASE_ORDER, updated merge pseudocode
- **TIMELINE_VALIDATION.md**: Rewritten — aligned check numbering with code (C1-C6, W1-W4), removed aspirational checks
- **API.md**: Added GET timeline endpoint, PATCH colors, PlayEntry/TimelineArtifactResponse models
- **SERVER_SIDE_MIGRATION.md** (NEW): Comprehensive 6-phase migration guide
- **INDEX.md**: Added Server-Side Migration section
- **ARCHITECTURE.md**: Updated timeline section with all modules

---

## [2026-02-09]

### NCAAB Social Scraping Enabled

- **NCAAB social enabled**: Social/X scraping now active for all three leagues (NBA, NHL, NCAAB)
- **Config flag**: `config_sports.py` NCAAB `social_enabled` flipped to `True`
- **Run manager**: NCAAB added to `_supported_social_leagues` so social runs execute instead of being silently skipped
- **Prerequisite**: NCAAB teams need active `TeamSocialAccount` rows with X handles before collection produces results

### Embedded Tweet Backfill

- **Post-generation backfill**: New pipeline endpoint `POST /pipeline/backfill-embedded-tweets` attaches social post references to flows that were generated before social scraping completed
- **Final-whistle integration**: After social Scrape #1, backfill runs automatically for the completed game
- **Daily sweep integration**: Sweep scans flows from the last 7 days for missing embedded tweets
- **Sole permitted mutation**: Backfill only sets `embedded_social_post_id` on blocks — block structure, roles, and narratives are never altered

### Game Stats Delta Validation

- **Scoring logic refactor**: `game_stats_helpers.py` delta computation rewritten with explicit validation
- **Expanded test coverage**: Comprehensive tests for delta calculation edge cases

### Odds Upsert Result Enum

- **`OddsUpsertResult` enum**: `upsert_odds` now returns `PERSISTED`, `SKIPPED_NO_MATCH`, or `SKIPPED_LIVE` instead of a boolean
- **Live game protection**: Live games explicitly skipped during odds sync to preserve pre-game closing lines

---

## [2026-02-08]

### Story to Game Flow Rename

- **Story -> Game Flow rename**: All consumer-facing "story" terminology renamed to "game flow" across API responses, documentation, and types
- **API endpoint**: `/games/{id}/story` -> `/games/{id}/flow`, response field `story` -> `flow`
- **Type renames**: `GameStoryResponse` -> `GameFlowResponse`, `StoryContent` -> `GameFlowContent`, `StoryBlock` -> `GameFlowBlock`, `StoryMoment` -> `GameFlowMoment`, `StoryPlay` -> `GameFlowPlay`
- **`embedded_tweet` -> `embeddedSocialPostId`**: Block-level social context now uses a social post ID reference (`number | null`) instead of an inline tweet object; `EmbeddedTweet` interface removed
- **camelCase mini box keys**: `delta_pts` -> `deltaPts`, `delta_reb` -> `deltaReb`, `delta_ast` -> `deltaAst`, `delta_goals` -> `deltaGoals`, `delta_assists` -> `deltaAssists`; `block_stars` -> `blockStars` on `BlockMiniBox`
- **`GamePhase` enum added**: `"pregame" | "in_game" | "postgame"` type for social post phase classification
- **`hasStory` -> `hasFlow`**, **`withStoryCount` -> `withFlowCount`** in game list responses
- **Documentation files renamed**: `STORY_CONTRACT.md` -> `GAMEFLOW_CONTRACT.md`, `STORY_PIPELINE.md` -> `GAMEFLOW_PIPELINE.md`, `PBP_STORY_ASSUMPTIONS.md` -> `PBP_GAMEFLOW_ASSUMPTIONS.md`
- Internal pipeline identifiers (`story_type`, `storyline_score`, `sports_game_stories`, `story_version`, Celery task names) remain unchanged

---

## [2026-02-06]

### Game-State-Machine & Two-Scrape Social Model

- **Game-state-machine**: Games tracked through state transitions (PREGAME → LIVE → FINAL) with polling tasks every 3-5 min
- **Two-scrape social model**: Scrape #1 on final-whistle (immediate), Scrape #2 in daily sweep (catch-up)
- **`game_social_posts` eliminated**: All social data lives in `team_social_posts` with `mapping_status` column
- **`XPostCollector` → `TeamTweetCollector`**: Simplified team-centric collection
- **Daily sweep at 4:00 AM EST**: Ingestion + truth repair + social scrape #2
- **Flow generation at 4:30/5:00/5:30 AM EST**: NBA, NHL, NCAAB respectively

### Legacy Code Cleanup

- **Removed `game_social_posts` table**: Mapping now tracked via `team_social_posts.mapping_status`
- **Removed `XPostCollector`**: Replaced by `TeamTweetCollector`
- **Removed `poll_active_social_task`**: Social collection handled by two-scrape model

---

## [2026-02-05]

### Social Collection Architecture

- **Team-centric collection**: Social scraping now collects all tweets for a team in a date range, then maps to games
- **New tables**: `team_social_posts` for raw collected tweets

### Legacy Code Cleanup

- **Removed NHL SportsRef scraper**: NHL uses official NHL API exclusively for all data
- **Simplified timeline generator**: Removed unused `build_nba_timeline()` function
- **Simplified social events**: Removed AI classification stubs (heuristics only)

---

## [2026-02-03]

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

- **Block-based Game Flow Model**: Game flows are ordered lists of narrative blocks backed by moments and specific plays
- **Multi-Stage Pipeline**: NORMALIZE_PBP → GENERATE_MOMENTS → VALIDATE_MOMENTS → ANALYZE_DRAMA → GROUP_BLOCKS → RENDER_BLOCKS → VALIDATE_BLOCKS → FINALIZE_MOMENTS
- **Deterministic Segmentation**: Moment boundaries are mechanical, AI is prose-only
- **Full Traceability**: Every narrative sentence maps to specific plays

### Features

- FastAPI admin API with game flow generation endpoints
- Celery scraper workers for NBA, NHL, NCAAB data
- Next.js admin UI for data browsing and game flow generation
- Sports Reference boxscore and PBP scraping
- NHL official API integration (schedule, PBP, boxscores)
- NCAAB College Basketball Data API integration
- The Odds API integration with local JSON caching
- Social media scraping from X/Twitter team accounts
- PostgreSQL with JSONB stats storage

### Documentation

- [GAMEFLOW_CONTRACT.md](GAMEFLOW_CONTRACT.md) - Authoritative game flow specification
- [GAMEFLOW_PIPELINE.md](GAMEFLOW_PIPELINE.md) - Pipeline stages and implementation
