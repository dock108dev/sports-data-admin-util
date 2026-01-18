# Changelog

All notable changes to Sports Data Admin.

## [2026-01-17] - Lead Ladder Refactor

### Added

#### Lead Ladder Infrastructure
- **Lead Ladder module** (`lead_ladder.py`): Pure functions for lead state tracking
  - `LeadState`: Immutable snapshot of game control
  - `TierCrossing`: Detected tier crossing events
  - `compute_lead_state()`, `detect_tier_crossing()`: Core utilities
  - Sport-agnostic: thresholds are passed in, no hardcoded defaults
- **New MomentTypes** based on Lead Ladder crossings:
  - `LEAD_BUILD`: Lead tier increased
  - `CUT`: Lead tier decreased (comeback)
  - `TIE`: Game returned to even
  - `FLIP`: Leader changed
  - `CLOSING_CONTROL`: Late-game lock-in
  - `HIGH_IMPACT`: Ejection, injury, etc.
  - `OPENER`: First plays of a period
  - `NEUTRAL`: Normal flow
- **Run metadata** (`run_info`): Runs are now metadata on moments, not separate moments
  - `team`, `points`, `unanswered`, `play_ids`
  - Attached to LEAD_BUILD, CUT, FLIP moments when a run contributed
- **Validation guardrails**: 119 tests covering invariants
  - Full play coverage assertion
  - No overlapping moments
  - Chronological ordering
  - No hardcoded league defaults
  - Multi-sport config regression tests
  - Source code scanning for NBA literals

#### AI Summary Refactor
- AI now only writes copy (headline, subhead) - no structural influence
- Deterministic fallbacks for all AI paths
- Structured `GameSummaryInput` for AI prompts
- `attention_points` derived from Moments (deterministic)

### Changed

#### Moment Detection (Breaking)
- **Moment boundaries** now determined by Lead Ladder tier crossings, not pattern matching
- **Hysteresis** added to prevent tier flicker (default: 2 plays)
- **Runs downgraded**: Scoring runs no longer create moments by themselves
  - Runs become `run_info` metadata on tier-crossing moments
  - Runs that didn't move control become `key_play_ids`

#### Compact Mode
- Compact Mode is now a **pure transformation** - no detection logic
- Compression behavior defined by `COMPRESSION_BEHAVIOR` map
- FLIP, TIE, CLOSING_CONTROL never collapsed
- NEUTRAL heavily collapsed

#### API Response Changes
- `type` field values changed: `RUN`, `BATTLE`, `CLOSING` removed
- New optional fields: `run_info`, `ladder_tier_before`, `ladder_tier_after`, `team_in_control`
- `is_notable` still works as primary highlight filter (unchanged)

### Removed
- `RUN`, `BATTLE`, `CLOSING` MomentTypes
- Hardcoded NBA thresholds (8 pts for run, 10 margin for closing)
- `detect_semantic_groups()` from compact_mode.py
- `SemanticGroup`, `GroupType` abstractions
- AI-generated `overview` and `attention_points` (now deterministic)

---

## [2026-01-16]

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
