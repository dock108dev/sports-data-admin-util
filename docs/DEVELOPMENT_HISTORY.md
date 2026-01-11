# Development History

This document summarizes the beta development phases that shaped the current platform.

## Phase 0 — Game Identity Stabilization (Jan 2026)

Established the canonical data model where every game has a single, reliable internal ID. Key outcomes:

- **Internal IDs only**: All routing, queries, and relationships use `games.id`
- **External IDs for reference**: `source_game_key` stored but never used for routing
- **Status lifecycle**: `scheduled` → `live` → `final`
- **Schema indexes**: `(league_id, game_date)` and `(league_id, status)`

See [DATABASE_INTEGRATION.md](DATABASE_INTEGRATION.md) for schema details.

## Phase 1 — Scheduled Ingestion

Automated the manual scraper pipeline with 15-minute Celery beat scheduling:

- **Hours**: 13:00–02:00 UTC
- **Window**: Yesterday through now + 24 hours
- **Leagues**: NBA, NHL, NCAAB
- **Execution**: Creates `sports_scrape_runs` record, enqueues `run_scrape_job`

Both manual UI runs and scheduled runs use the same ingestion entry point.

## Phase 2 — Live Feeds & Play-by-Play

Added live data feeds for real-time PBP:

| League | Live PBP Source | Post-game |
|--------|-----------------|-----------|
| NBA | `cdn.nba.com` | Sports-Reference |
| NHL | `statsapi.web.nhl.com` | Sports-Reference |
| NCAAB | Best-effort only | Sports-Reference |

Status synchronization ensures games marked `live` never regress.

## Phase 3 — Social Layer

Integrated X/Twitter posts from official team accounts:

- **Account registry**: `team_social_accounts` stores platform/handle mappings
- **Collection**: 24-hour game day window (5 AM ET to 5 AM ET)
- **Spoiler handling**: Conservative by default — only safe patterns whitelisted

See [X_INTEGRATION.md](X_INTEGRATION.md) for implementation details.

## Phase 4 — Game Snapshots API

Introduced the read-only API surface for iOS app consumption:

| Endpoint | Description |
|----------|-------------|
| `GET /api/games?range=` | Games by time window (`last2`, `current`, `next24`) |
| `GET /games/{id}/pbp` | Play-by-play events by period |
| `GET /games/{id}/social` | Social posts with reveal levels |
| `GET /games/{id}/recap` | AI-generated summaries |

All responses use explicit reveal levels (`pre` / `post`).

## Phase 5 — Monitoring & Trust

Added observability and safety guards:

- **Job dashboard**: `sports_job_runs` tracks phase execution
- **Game timestamps**: `last_ingested_at`, `last_pbp_at`, `last_social_at`
- **Diagnostics**: Missing PBP detection, conflict identification
- **Safety**: Suspicious data flagged, never auto-corrected

See [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md) for debugging procedures.

---

*This history is provided for context. Current implementation details live in the respective docs.*
