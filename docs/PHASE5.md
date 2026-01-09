# Beta Phase 5 — Monitoring & Trust

This phase adds explicit monitoring surfaces, safety guards, and diagnostics so data issues are immediately visible and explainable. No new data sources were added.

## Monitoring Surfaces

### Job Execution Dashboard (Internal)
Job runs are stored in `sports_job_runs` and exposed at:

* `GET /api/admin/sports/jobs` — phase-level runs with status, duration, and error summary.

Tracked phases:
* `ingest` — boxscore + odds ingestion
* `pbp` — live play-by-play ingestion
* `social` — social ingestion
* `snapshot` — snapshot API generation

### Game-Level Update Timestamps
Each game now tracks:
* `last_ingested_at` — boxscore / game metadata changes
* `last_pbp_at` — new play-by-play events
* `last_social_at` — new or updated social posts

The snapshot API exposes `last_updated_at` (max of the above) so staleness is visible immediately.

### Diagnostics Endpoints
* `GET /api/admin/sports/diagnostics/missing-pbp` — games that are live/final but missing PBP.
* `GET /api/admin/sports/diagnostics/conflicts` — duplicate external IDs or team mismatches.

## Safety Philosophy

* **No auto-fixes:** suspicious data is never silently corrected.
* **Safety first:** conflicts or missing team mappings mark a game unsafe at read time.
* **Explainable exclusions:** snapshot APIs skip unsafe games and log the reason.

This keeps app-visible data unambiguous without deleting or mutating source records.

## Debugging Guide

### Did ingestion run?
1. Check `/api/admin/sports/jobs` for the latest `ingest`, `pbp`, or `social` runs.
2. Verify `status`, `duration_seconds`, and `error_summary`.

### Why is a game stale?
1. Look at `last_updated_at` in snapshot responses.
2. For detailed timestamps, inspect the game record in admin endpoints or the DB.

### Missing PBP in live/final games
1. Visit `/api/admin/sports/diagnostics/missing-pbp`.
2. Review the `reason`:
   * `no_feed` — feed returned no plays
   * `not_supported` — league has no live PBP feed

### Wrong game opens / ambiguous identity
1. Check `/api/admin/sports/diagnostics/conflicts` for duplicate external IDs.
2. Conflicts include both game IDs and the conflicting fields.
3. Snapshot APIs automatically exclude these games until the conflict is resolved.

## Logging Notes

Structured logs now include:
* Game resolution (external → internal IDs)
* Skipped games and reasons
* Conflict detection records
* PBP absence detections

These logs make root cause analysis deterministic instead of speculative.
