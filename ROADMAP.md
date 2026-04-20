# Roadmap

North star: **for every completed game, deliver a high-quality, factually grounded, sport-appropriate narrative flow within 15 minutes of the final whistle.**

Phases are sequenced by dependency, not calendar. Each checkbox is scoped to be implementable as a single GitHub issue.

---

## Phase 1 — Flow Reliability

**Goal:** Flows generate reliably within 15 minutes of FINAL, and regressions are caught before they ship.

**Exit criteria:**
- 95% of games transitioning to FINAL have a flow within 15 minutes.
- CI blocks any pipeline change that regresses the golden corpus.
- Every generated flow has a populated `mini_box` for all blocks.

**Deliverables:**
- [x] Replace daily 4:30–6:30 AM flow schedule with event-driven dispatch on FINAL transition (+5 min delay for PBP settle). See `docs/archived/research/event-driven-celery-task-dispatch.md`.
- [x] Add ORM-level `after_flush`/`after_commit` hook on `Game.status` transitions that enqueues `generate_flow` Celery task.
- [x] Add Redis `SET NX` lock keyed on `game_id` to prevent duplicate dispatches from retry paths.
- [x] Build golden corpus: 10 games per sport (NBA, NHL, MLB, NFL, NCAAB) with human-validated narrative outputs. See `docs/archived/research/golden-corpus-construction-methodology.md`.
- [x] Add `pytest` CI gate that runs the pipeline against the corpus and diffs outputs against reference on every PR.
- [x] Add coverage validation: assert every flow mentions final score, winning team, and OT if applicable. See `docs/archived/research/nlg-coverage-validation-techniques.md`.
- [x] Add `mini_box` population audit in `validate_blocks.py` — reject any block missing cumulative stats + segment deltas.
- [x] Align block count constraints: MIN=3 (blowouts) enforced in both `block_types.py` and `guardrails.ts`.
- [ ] Add a "recap pending" consumer-facing state with ETA instead of 404 on missing flows.
- [x] Backfill script to regenerate flows for any FINAL game from last 7 days missing a flow.

---

## Phase 2 — Contract Hardening

**Goal:** API contracts become self-documenting and drift-proof between backend and frontend.

**Exit criteria:**
- No nullable state predicates in API responses.
- Scores are structured objects end-to-end.
- One namespace for consumer endpoints, one for admin.

**Deliverables:**
- [x] Introduce `ScoreObject` Pydantic model `{home: int, away: int}` and migrate all score-returning endpoints off `[int, int]` tuples. See `docs/archived/research/pydantic-score-object-migration.md`.
- [x] Delete `_swap_score()` helper once migration complete.
- [x] Make `isLive`, `isFinal`, `isPregame` computed non-nullable booleans in `GameSummary`.
- [x] Audit all response schemas for missing camelCase `Field(alias=...)` declarations; add lint check.
- [x] Dedupe `PipelineStage` enum: single source of truth in `services/pipeline/models.py`, imported by DB layer.
- [x] Remove `cancelled`/`canceled` duplicate entry in `GameStatus` enum. Canonical value is `CANCELLED`.
- [x] Introduce `/api/v1/` router namespace for consumer endpoints. Game flow endpoint live at `/api/v1/games/{id}/flow`.
- [x] Split auth middleware: consumer keys vs admin keys with different rate limits.
- [x] Add JSONB schema validation for `external_ids`, `external_codes` at write time. See `docs/archived/research/jsonb-schema-validation-postgres.md`.
- [x] Document `story_version` vs `blocks_version` semantics; renamed `v2-moments` to `v2-blocks`. See `docs/gameflow/version-semantics.md`.

---

## Phase 3 — Social Stabilization

**Goal:** Social ingestion stops being the most brittle subsystem.

**Exit criteria:**
- Every mapped social post has non-null `game_phase`.
- Session health detected before scraping failures.
- Embedded post IDs always resolve to real posts.

**Deliverables:**
- [ ] Add Playwright session health probe that runs every 30 min and alerts on cookie expiration. See `docs/archived/research/playwright-session-health-monitoring.md`.
- [x] Add `UNKNOWN` value to `GamePhase` enum; update `tweet_mapper.py` to assign it rather than null when phase can't be inferred.
- [x] Add `NOT NULL` constraint on `TeamSocialPost.game_phase` via Alembic migration (after backfill).
- [ ] Add DB-side validation in `embedded_tweets.py` — verify `embedded_social_post_id` exists in `TeamSocialPost` before persisting the block.
- [x] Evaluate alternative X/Twitter data sources and prototype one. See `docs/archived/research/x-twitter-data-alternatives.md`.
- [ ] Add circuit breaker telemetry (tripped count, last trip reason) to the admin dashboard.
- [ ] Drop unused `likesCount`, `retweetsCount`, `repliesCount` from `SocialPostEntry` response or add them to frontend type.
- [ ] Validate `mediaType` as enum `"video" | "image" | null` in both Pydantic model and SQL constraint.

---

## Phase 4 — Observability

**Goal:** Operators see failures before users do.

**Exit criteria:**
- Grafana dashboard covers flow coverage, quality distribution, social health, odds credit burn.
- Pagerable alerts exist for each trust-killing failure mode.

**Deliverables:**
- [x] Instrument FastAPI + Celery with OpenTelemetry traces/metrics. See `docs/archived/research/opentelemetry-for-pipeline-observability.md`.
- [x] Export pipeline stage durations, regeneration count, fallback rate per sport.
- [ ] Grafana dashboard: "% of final games from yesterday with flows" by sport.
- [ ] Grafana dashboard: quality score histogram + fallback rate time series.
- [x] Alert: quality score p50 drops >10 points day-over-day.
- [x] Alert: social collection success rate below 90% over 2h window.
- [x] Alert: Odds API credit burn projects to exceed weekly budget (threshold: 80%).
- [x] Alert: any flow persisted with score mismatch vs authoritative final score.
- [ ] Add pipeline coverage report job (daily) — writes gap summary to DB for admin UI.

---

## Phase 5 — Realtime Activation

**Goal:** Frontend consumes live updates without DB polling bottleneck.

**Exit criteria:**
- API can run multi-process without losing pub/sub fanout.
- Live scores and odds propagate to browser in <5s without client polling.

**Deliverables:**
- [x] Replace DB poller in `realtime/poller.py` with Postgres `LISTEN/NOTIFY` triggered by ingestion writers. See `docs/archived/research/postgres-listen-notify-python.md` and `docs/archived/research/celery-event-driven-vs-beat-scheduling.md`.
- [ ] Move pub/sub manager from in-memory to Redis Streams for multi-process fanout. See `docs/archived/research/redis-pubsub-vs-streams-for-realtime.md`.
- [ ] Preserve sequence tracking + boot epoch semantics on Redis-backed manager.
- [ ] Build `useLiveGameScore(gameId)` React hook over SSE with reconnection + backfill. See `docs/archived/research/websocket-sse-react-integration-patterns.md`.
- [ ] Build `useLiveOdds(gameId)` hook; wire into FairBet live views.
- [ ] Switch game-detail page to differential updates (patches) for score/clock, full refetch only on period change.
- [ ] Load-test: 500 concurrent SSE subscribers on a single API instance.

---

## Phase 6 — Quality Deepening

**Goal:** Narrative quality becomes measurable and sport-appropriate, not just heuristic-passing.

**Exit criteria:**
- LLM grader scores correlate with human judgment on the corpus.
- Sport-specific templates produce recognizably different outputs for NBA vs MLB vs NHL.
- Anti-generic scoring catches "both teams traded baskets"-class language.

**Deliverables:**
- [ ] Build 3-tier LLM grader: Haiku for fast screen, Sonnet for ambiguous cases, human review queue for corpus expansion. See `docs/archived/research/llm-narrative-grading-patterns.md` and `docs/archived/research/sports-narrative-quality-benchmarks.md`.
- [ ] Integrate grader into pipeline as gate between quality scoring and publish — low LLM grade triggers regen with error context.
- [ ] Feed quality-score breakdown into regen prompt so second attempt knows what failed.
- [ ] Add sport-specific block templates (NBA run-based, MLB inning-based, NHL period-based, NFL drive-based, NCAAB tournament-aware). See `docs/archived/research/sport-specific-narrative-structure.md`.
- [ ] Add RESOLUTION block specificity check: must reference at least one specific play from final 2 min / final inning / final period.
- [ ] Add anti-generic detector beyond cliche list — flag content-free phrases via LLM classifier.
- [ ] Expand golden corpus to 25 games per sport including edge cases: OT, shootouts, perfect games, blowouts, comebacks, ejections.
- [ ] Add "information density" test — strip names/teams from narrative; assert output is meaningfully different from template.
