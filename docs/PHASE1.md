# Beta Phase 1 — Scheduled Ingestion

## Overview
Phase 1 automates the existing manual scraper pipeline by scheduling the same ingestion path every 15 minutes.
The scheduler only orchestrates runs; it does not add new scraping logic.

## Scheduler Design
- **Runner:** Celery beat triggers a `run_scheduled_ingestion` task every 15 minutes.
- **Hours:** 13:00–02:00 UTC (`minute="*/15", hour="13-23,0-2"`).
- **Window:** UTC yesterday through now + 24 hours.
- **Leagues:** NBA, NHL, NCAAB.
- **Execution:** Each scheduled run creates a `sports_scrape_runs` record and enqueues the existing `run_scrape_job` task.

## Reuse of Manual Ingestion
Both manual UI-triggered runs and scheduled runs execute the same ingestion entry point:
- The UI enqueues `run_scrape_job`.
- The scheduler also enqueues `run_scrape_job`.
This task funnels into the shared ingestion function in `bets_scraper/services/ingestion.py`.

## Failure Handling & Visibility
- **Structured logs** capture scheduler start/end, per-league enqueue results, created vs updated counts, and failures.
- **Retry safety:** the scheduler task retries on transient failures (Celery autoretry), while per-league failures are logged and skipped.
- **Operational visibility:** `sports_scrape_runs` rows provide per-league summaries; scheduler logs emit `last_run_at` and failure counters.

## Manual Debug Trigger
To manually trigger a scheduled run:
```
celery -A bets_scraper.celery_app.app call run_scheduled_ingestion
```

## Notes
- Ingestion is idempotent: the game upsert preserves the canonical start time and only sets `end_time` when a game reaches `final`.
- External IDs are attached but never treated as canonical identifiers in API responses.
