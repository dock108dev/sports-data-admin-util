# Changelog

All notable changes to Sports Data Admin.

## [2026-02-08] - Current

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
- **Daily sweep at 5:00 AM EST**: Ingestion + truth repair + social scrape #2
- **Flow generation at 6:30/6:45/7:00 AM EST**: NBA, NHL, NCAAB respectively

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
