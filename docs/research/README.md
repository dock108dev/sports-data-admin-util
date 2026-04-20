# Research Docs

Technical deep-dives that inform design decisions for Phase 1–6 work. Each doc answers a specific question before the implementation begins. Use these before building a feature — the hard tradeoffs are already documented.

## Event-Driven Architecture

| Doc | Question answered |
|-----|------------------|
| [event-driven-celery-task-dispatch.md](event-driven-celery-task-dispatch.md) | How to dispatch a Celery task when a game goes FINAL — SQLAlchemy hooks vs. LISTEN/NOTIFY vs. application-level emit |
| [celery-event-driven-vs-beat-scheduling.md](celery-event-driven-vs-beat-scheduling.md) | Replacing Celery Beat with event-driven dispatch — ETA tasks, deduplication with Redis NX locks, configurable delays |
| [event-driven-flow-generation.md](event-driven-flow-generation.md) | End-to-end pattern for flow generation triggered by game status transitions |

## Realtime & Pub/Sub

| Doc | Question answered |
|-----|------------------|
| [postgres-listen-notify-python.md](postgres-listen-notify-python.md) | Postgres LISTEN/NOTIFY with asyncpg and asyncio — connection lifecycle, reconnect, fan-out |
| [postgres-listen-notify-celery.md](postgres-listen-notify-celery.md) | Integrating Postgres LISTEN/NOTIFY with Celery workers — bridging async DB notifications to task dispatch |
| [redis-pubsub-vs-streams-for-realtime.md](redis-pubsub-vs-streams-for-realtime.md) | Redis Pub/Sub vs. Streams for multi-process SSE fanout — persistence, consumer groups, backfill |
| [redis-pubsub-multiprocess.md](redis-pubsub-multiprocess.md) | Scaling pub/sub across multiple API processes without losing messages |
| [websocket-sse-react-integration-patterns.md](websocket-sse-react-integration-patterns.md) | Building `useLiveGameScore` and `useLiveOdds` hooks over SSE — reconnect, sequence gap detection, backfill |

## API & Schema Design

| Doc | Question answered |
|-----|------------------|
| [fastapi-api-versioning-patterns.md](fastapi-api-versioning-patterns.md) | FastAPI versioning patterns — `/api/v1/` namespace strategy, router organization |
| [pydantic-score-object-migration.md](pydantic-score-object-migration.md) | Migrating score fields from `[int, int]` tuples to `ScoreObject {home, away}` — backward compat, migration path |
| [pydantic-camelcase-audit.md](pydantic-camelcase-audit.md) | Auditing all response schemas for camelCase `Field(alias=...)` compliance and CI lint check |

## Database & Migrations

| Doc | Question answered |
|-----|------------------|
| [alembic-enum-sync-strategies.md](alembic-enum-sync-strategies.md) | Keeping Python enums and Postgres enums in sync — add-then-rename strategy, avoiding in-place drops |
| [alembic-enum-migration-postgres.md](alembic-enum-migration-postgres.md) | Postgres enum migration failure modes, reversibility, and safe rollback patterns |
| [jsonb-schema-validation-postgres.md](jsonb-schema-validation-postgres.md) | Enforcing JSON Schema on JSONB columns via Postgres CHECK constraints |

## Narrative Pipeline

| Doc | Question answered |
|-----|------------------|
| [golden-corpus-construction-methodology.md](golden-corpus-construction-methodology.md) | How to build a golden corpus of game fixtures for pipeline regression testing |
| [golden-corpus-regression-testing.md](golden-corpus-regression-testing.md) | CI integration for golden corpus — snapshot diffing, acceptable drift thresholds, sport-specific gates |
| [nlg-coverage-validation-techniques.md](nlg-coverage-validation-techniques.md) | Techniques for verifying a narrative mentions required entities (score, teams, OT) — regex, NER, embedding, LLM; cost at 50 games/day |
| [narrative-coverage-validation.md](narrative-coverage-validation.md) | Architecture for claim extraction and contradiction detection: `RequiredClaimsExtractor` → `NarrativeClaimParser` → `ClaimVerifier` |
| [information-density-scoring.md](information-density-scoring.md) | Scoring narratives for information density — detecting content-free filler, "strip the names" test |

## Quality & Grading

| Doc | Question answered |
|-----|------------------|
| [llm-narrative-grading-patterns.md](llm-narrative-grading-patterns.md) | LLM-as-judge for sports narratives — rubric design, sports-specific dimensions, open-source frameworks (promptfoo, TruLens, RAGAS), cost management |
| [llm-output-grading.md](llm-output-grading.md) | Production LLM-as-judge best practices — prompt structure, model tier selection (Haiku vs. Sonnet), batching, caching |
| [sports-narrative-quality-benchmarks.md](sports-narrative-quality-benchmarks.md) | Quality benchmarks and thresholds for sports narrative output — what "good" looks like per sport |
| [sport-specific-narrative-structure.md](sport-specific-narrative-structure.md) | Sport-specific block templates — NBA run-based, MLB inning-based, NHL period-based, NFL drive-based, NCAAB tournament-aware |
| [sport-specific-quality-thresholds.md](sport-specific-quality-thresholds.md) | Per-sport quality score thresholds and scraping alternatives — why NBA and NHL require different passing bars |
| [mini-box-score-sport-coverage.md](mini-box-score-sport-coverage.md) | `mini_box` field coverage requirements per sport — which cumulative and delta stats are required for each |

## Social & Ingestion

| Doc | Question answered |
|-----|------------------|
| [x-twitter-data-alternatives.md](x-twitter-data-alternatives.md) | Alternatives to Playwright X scraping — X API v2 tiers, Apify, Bright Data, Nitter, hybrid approach; cost/reliability for 30 accounts at 30-min cadence |
| [x-twitter-alternative-decision.md](x-twitter-alternative-decision.md) | **ADR**: Decision record for X/Twitter alternative — RSS/Atom feeds vs. Bluesky AT Protocol; outcome and prototype approach |
| [playwright-session-health-monitoring.md](playwright-session-health-monitoring.md) | Detecting Playwright cookie expiration before scraping failures — health probe patterns |
| [session-cookie-health-detection.md](session-cookie-health-detection.md) | Session cookie validity detection techniques — lightweight probe requests, expiry heuristics |
| [odds-api-credit-optimization.md](odds-api-credit-optimization.md) | Reducing The Odds API credit consumption — request batching, TTL tuning, selective polling by game state |
| [fairbet-ev-devigging-methods.md](fairbet-ev-devigging-methods.md) | Devigging methods for fair-value odds calculation — additive, multiplicative, Shin's method comparison |

## Observability

| Doc | Question answered |
|-----|------------------|
| [opentelemetry-for-pipeline-observability.md](opentelemetry-for-pipeline-observability.md) | Instrumenting the 8-stage pipeline with OpenTelemetry — span naming, stage duration histograms, fallback rate counters |
