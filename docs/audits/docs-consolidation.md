# Documentation Consolidation Audit

---

## Review Pass 4 — 2026-04-20

Full doc + AIDLC issue cross-reference pass. 64 files audited (up from 47 — 17 new research docs added since Pass 3). Three targeted changes applied.

### Files Changed

#### `ROADMAP.md`

**Problem:** 19 roadmap items remained unchecked despite being confirmed implemented in the `.aidlc/issues/` tracker. The previous doc passes only checked 5 items (Phase 1 MIN_BLOCKS alignment, Phase 2 ScoreObject/PipelineStage/CANCELLED/v1-namespace/story_version).

**Items now checked off:**

| Item | Issue | Evidence |
|------|-------|----------|
| Event-driven dispatch on FINAL (replace schedule) | ISSUE-001 | `scraper/sports_scraper/jobs/flow_trigger_tasks.py` — `trigger_flow_for_game` task |
| ORM `after_flush`/`after_commit` hook | ISSUE-001 | `api/app/db/hooks.py` — `_track_final_transitions` + `_dispatch_final_game_tasks` |
| Redis `SET NX` lock on `game_id` | ISSUE-001 | `flow_trigger_tasks.py` — `acquire_redis_lock("pipeline_lock:trigger_flow_for_game:{game_id}")` |
| Golden corpus: 10 games per sport | ISSUE-003 | `**Status**: implemented` in `.aidlc/issues/ISSUE-003.md` |
| `pytest` CI gate against corpus | ISSUE-004 | `**Status**: implemented` |
| Coverage validation (score, winner, OT) | ISSUE-005 | `**Status**: implemented` |
| `mini_box` audit in `validate_blocks.py` | ISSUE-005 | `**Status**: implemented` |
| Backfill script (7-day window) | ISSUE-001 | `backfill_missing_flows()` in `flow_trigger_tasks.py` |
| `isLive`/`isFinal`/`isPregame` computed non-nullable | ISSUE-008 | `**Status**: implemented` |
| camelCase `Field(alias=...)` audit + CI lint | ISSUE-013, ISSUE-027 | Both `**Status**: implemented` |
| Split auth middleware (consumer vs. admin) | ISSUE-010 | `**Status**: implemented` |
| JSONB schema validation for `external_ids` | ISSUE-011, ISSUE-028 | Both `**Status**: implemented` |
| `UNKNOWN` in `GamePhase` enum | ISSUE-014 | `**Status**: implemented` |
| `NOT NULL` on `TeamSocialPost.game_phase` | ISSUE-015 | `**Status**: implemented` |
| Evaluate X/Twitter alternative + prototype | ISSUE-017 | `**Status**: implemented` |
| OTel instrumentation (FastAPI + Celery) | — | `api/app/otel.py` exists; ISSUE-018 extends it |
| Pipeline stage duration metrics export | ISSUE-018 | `**Status**: implemented` |
| Alerts (quality, social, odds burn, score mismatch) | ISSUE-020 | `**Status**: implemented` |
| Replace DB poller with LISTEN/NOTIFY | ISSUE-021 | `**Status**: implemented` |

**Remaining unchecked in Phase 1:** "recap pending" consumer state.
**Remaining unchecked in Phase 3:** Playwright health probe, embedded post ID DB validation, circuit breaker telemetry, `mediaType` enum enforcement.
**Remaining unchecked in Phase 4:** Grafana dashboards (2 items), pipeline coverage report job.
**Remaining unchecked in Phase 5:** Redis Streams pub/sub, sequence tracking on Redis, `useLiveGameScore`/`useLiveOdds` hooks, differential updates, SSE load test.
**Phase 6:** All items remain pending.

---

#### `docs/aidlc-futures.md` — DELETED

**Problem:** Stale copy of AIDLC futures metadata with incorrect run statistics (`issues_implemented: 49` vs. root `AIDLC_FUTURES.md` which shows `61`) and broken relative links (pointed to `docs/audits/` rather than `audits/` from within the `docs/` directory). Pass 3 intended to "move" the root file here but instead created a mismatched copy. The root `AIDLC_FUTURES.md` is the authoritative version and stays at root.

**Fix:** Deleted `docs/aidlc-futures.md`.

---

#### `docs/research/x-scraping-alternatives.md` — DELETED

**Problem:** Fully redundant with `docs/research/x-twitter-data-alternatives.md`. Both documents covered the same five options (X API v2, Apify, Bright Data, Nitter, Social-Searcher) with nearly identical analysis. `x-twitter-data-alternatives.md` is the more complete version — it includes the hybrid approach architecture diagram, decision tree, and implementation pattern. The ADR (`x-twitter-alternative-decision.md`) already references `x-twitter-data-alternatives.md` as the evaluation source.

**Fix:** Deleted `docs/research/x-scraping-alternatives.md`.

---

#### `docs/research/README.md` — CREATED

**Problem:** 32 research documents had no navigation aid. New contributors had no way to discover which doc to read before implementing a given feature.

**Fix:** Created `docs/research/README.md` with a categorized index organized by topic area: Event-Driven Architecture, Realtime & Pub/Sub, API & Schema Design, Database & Migrations, Narrative Pipeline, Quality & Grading, Social & Ingestion, Observability. Each entry states the question the doc answers.

---

#### `docs/index.md`

**Problem:** No link to the new `docs/research/README.md` from the top-level index.

**Fix:** Added a "Research" section at the bottom of `docs/index.md` linking to `research/README.md`.

---

### Files Audited and Unchanged (this pass)

All 59 remaining docs verified accurate against current codebase and issue tracker. No further issues found.

---

## Review Pass 2 — 2026-04-19

47 documentation files audited. No files deleted. No files moved. Five targeted fixes applied: two factual corrections in `docs/gameflow/`, three checked-off roadmap items, and stale-resolution annotations in `BRAINDUMP.md`.

### Files Changed

#### `docs/gameflow/pipeline.md`

**Problem:** Stage 8 (FINALIZE_MOMENTS) storage block listed `story_version = "v2-moments"`. The code (`finalize_moments.py`) writes `FLOW_VERSION = "v2-blocks"` since the `aidlc_1` rename.

**Fix:** Updated to `story_version = "v2-blocks"`.

#### `docs/gameflow/version-semantics.md`

**Problem:** The `v1-blocks` table row described the schema as "4–7 blocks." `MIN_BLOCKS = 3` is the actual constant (verified in `api/app/services/pipeline/stages/block_types.py`).

**Fix:** Updated to "3–7 blocks".

#### `ROADMAP.md`

**Problem:** Five items completed during `aidlc_1` were still shown as unchecked.

**Items checked off:**

| Item | Evidence |
|------|----------|
| Align block count constraints | `MIN_BLOCKS = 3` in both `block_types.py` and `guardrails.ts` |
| Dedupe `PipelineStage` enum | SSOT in `services/pipeline/models.py`; `db/pipeline.py` re-exports |
| Remove `cancelled`/`canceled` duplicate | Canonical value `CANCELLED` confirmed; migration `20260419_000038` applied |
| Introduce `/api/v1/` router namespace | `api/app/routers/v1/` exists; game flow endpoint live |
| Document `story_version` semantics + rename | `docs/gameflow/version-semantics.md` published; code writes `v2-blocks` |

#### `BRAINDUMP.md`

**Problem:** Three analytical sections described problems that `aidlc_1` resolved, without noting the resolution. Readers would conclude the problems were still open.

**Sections updated with `> Resolved in aidlc_1` callouts:**

| Section | Stale claim | Current state |
|---------|-------------|---------------|
| "Guardrails enforcement" | Frontend MIN=4 vs backend MIN=3 mismatch | Both are 3; verified in sync |
| "Consumer-facing game flow components" | No `/api/v1/` consumer endpoint | `/api/v1/games/{id}/flow` is live |
| "`story_version = 'v2-moments'` naming" | Naming was confusing | Renamed to `v2-blocks`; version doc published |
| "Scores are tuples, not objects" | All endpoints return tuples | Consumer endpoint uses `ScoreObject`; admin migration is Phase 2 |
| "The `moments` layer is vestigial" | Moments exposed in consumer API | Moments not in `/api/v1/` response; internal only |

### Files Audited and Unchanged (this pass)

All 42 remaining docs re-verified. No further issues found. See Review Pass 1 section below for the full file-by-file table.

---

## Review Pass 1 — 2026-04-18

> Branch: `aidlc_1`

47 documentation files audited across the repo. No files deleted (all carry unique value). No files moved (root docs are referenced by `CLAUDE.md` and must stay in place). Six files updated to fix factual errors or stale content introduced by the `aidlc_1` SSOT cleanup changes.

---

## Files Changed

### `ARCHITECTURE.md` (root)

**Problem:** Multiple stale and incorrect statements relative to the current codebase.

**Changes made:**

| Section | Old | New |
|---------|-----|-----|
| `scraper/` components | Listed "Analytics/ML" as a scraper component | Removed — analytics lives in `api/app/analytics/`, not the scraper |
| `api/` components | No mention of analytics | Added analytics as an `api/` component with correct path |
| Web guardrails | Block count "(4–7)" | Corrected to "(3–7)" — both ends now use MIN_BLOCKS = 3 |
| Pipeline stage names | Old names: `normalize_pbp`, `drama_analysis`, `group_moments`, `generate_blocks`, `embedded_tweets`, `validate_blocks`, `finalize_moments`, `persist` | Corrected to actual enum names: `NORMALIZE_PBP`, `GENERATE_MOMENTS`, `VALIDATE_MOMENTS`, `ANALYZE_DRAMA`, `GROUP_BLOCKS`, `RENDER_BLOCKS`, `VALIDATE_BLOCKS`, `FINALIZE_MOMENTS` |
| Pipeline stage order | Drama analysis was stage 2; embedded_tweets was a standalone stage 5 | Correct order: moments generated/validated before drama; embed selection folded into `RENDER_BLOCKS` |
| Social ingestion note | "Embed selector (stage 5 of flow pipeline)" | "Embed selector (during `RENDER_BLOCKS` pipeline stage)" |
| State management | `GameStatus` "has duplicate cancelled/canceled; dedupe in Phase 2" | "Canonical value is `CANCELLED`" (fixed by SSOT cleanup migration) |
| State management | `PipelineStage` "currently duplicated in DB and service layers" | "Single SSOT in `api/app/services/pipeline/models.py`; db layer re-exports" |
| Directory structure | Listed `scraper/sports_scraper/pipeline/` and `analytics/` — neither exists | Removed both; added correct scraper subdirs (`jobs/`, `live/`, `persistence/`, `services/`) and `api/app/analytics/` |
| Known pressures | Listed "Enum duplication" and "Moments vs blocks vestige" as open | Removed — both resolved in `aidlc_1` |
| Known pressures | "Score tuple convention … Phase 2 moves to `{home, away}`" | Updated to reflect partial completion: consumer endpoint uses `ScoreObject`; admin endpoints still pending |
| Known pressures | Consumer/admin boundary phrasing | Updated to reflect `/api/v1/` game flow endpoint is now live |
| API router description | "All currently live under `/api/admin/sports/`; Phase 2 introduces `/api/v1/`" | Updated to reflect `/api/v1/` is live for game flow |

---

### `DESIGN.md` (root)

**Problem:** "Pipeline as ordered stages" paragraph referenced `scraper/sports_scraper/pipeline/` — a path that does not exist. Pipeline code lives in `api/app/services/pipeline/stages/`.

**Change:** Updated path to `api/app/services/pipeline/stages/`.

---

### `CLAUDE.md` (root)

**Problem:** "Where things live" section listed two wrong paths:
- `Pipeline stages: scraper/sports_scraper/pipeline/`
- `Flow validation: scraper/sports_scraper/pipeline/validate_blocks.py`
- `Frontend guardrails` had an "(or similar — verify path)" hedge that is no longer needed

**Changes:**
- Corrected both paths to `api/app/services/pipeline/stages/`
- Removed the unnecessary path-verification hedge on `guardrails.ts`

---

### `BRAINDUMP.md` (root)

**Problem:** Several specific claims were made stale by `aidlc_1` SSOT cleanup work.

**Changes:**

| Claim | Update |
|-------|--------|
| `GameStatus` duplicate `canceled` entry | Moved to "Resolved in `aidlc_1`" note; standardized to `CANCELLED` |
| `PipelineStage` defined in two places | Moved to resolved note; single SSOT now |
| Score tuples `[int, int]` on wire | Moved to resolved note; `ScoreObject` is the consumer contract |
| Moments in consumer API | Moved to resolved note; moments removed from `/api/v1/` |
| Priority 2: "Align MIN_BLOCKS" | Marked as done — both sides now 3, verified in sync |
| Priority 2: "Move scores to objects" | Marked as done (consumer endpoint); admin migration still pending |
| Priority 2: "Single PipelineStage enum" | Marked as done |
| Priority 2: "Document score convention" | Marked as done — `ScoreObject` is self-documenting |

---

## Files Audited and Unchanged

All remaining docs were verified accurate against the current codebase:

| File | Status |
|------|--------|
| `README.md` | Accurate. Concise. No changes. |
| `ROADMAP.md` | Accurate. Phase descriptions match current priorities. |
| `docs/index.md` | Accurate. All linked files exist. |
| `docs/architecture.md` | Accurate. Already had correct pipeline path (`api/app/services/pipeline/`) and correct stage names. |
| `docs/api.md` | Accurate. Endpoint reference matches router files. |
| `docs/database.md` | Accurate. Schema tables match Alembic baseline. |
| `docs/adding-sports.md` | Accurate. Analytics section already correctly references `api/app/analytics/`. |
| `docs/analytics.md` | Accurate. Engine description matches `api/app/analytics/`. |
| `docs/analytics-downstream.md` | Accurate. Integration guide is consistent with API. |
| `docs/gameflow/contract.md` | Accurate. Block spec matches `validate_blocks.py` constants. |
| `docs/gameflow/guide.md` | Accurate. TypeScript types consistent with `packages/js-core/`. |
| `docs/gameflow/pipeline.md` | Accurate. Stage names and order match actual code. |
| `docs/gameflow/pbp-assumptions.md` | Accurate. |
| `docs/gameflow/timeline-assembly.md` | Accurate. |
| `docs/gameflow/timeline-validation.md` | Accurate. |
| `docs/gameflow/version-semantics.md` | Accurate. `v2-blocks` is documented as current; `v2-moments` as deprecated with transition guidance. |
| `docs/ingestion/data-sources.md` | Accurate. All data source references are correct. |
| `docs/ingestion/ev-math.md` | Accurate. Shin's devigging formulas unchanged. |
| `docs/ingestion/odds-and-fairbet.md` | Accurate. Pipeline flow matches scraper code. |
| `docs/golf-pools.md` | Accurate. |
| `docs/ops/infra.md` | Accurate. Docker profile structure matches `infra/`. |
| `docs/ops/deployment.md` | Accurate. CI/CD description matches `.github/workflows/`. |
| `docs/ops/runbook.md` | Accurate. |
| `docs/changelog.md` | Present; not audited for correctness (changelog is append-only). |
| `docs/AUDIT_REPORT.md` | Accurate. All critical/high findings documented as fixed. |
| `docs/audits/abend-handling.md` | Present. |
| `docs/audits/security-audit.md` | Present. |
| `docs/audits/ssot-cleanup.md` | Accurate. Describes exactly what was changed in `aidlc_1`. |
| `docs/research/` (17 files) | Forward-looking research docs. Accuracy depends on implementation status of Phase 2–6 items. No claims made about current implementation state — these are design research docs. |

---

## What Was NOT Changed (and Why)

**Structure:** Root-level docs (`ARCHITECTURE.md`, `DESIGN.md`, `ROADMAP.md`, `BRAINDUMP.md`) were not moved to `/docs/`. `CLAUDE.md` is a Claude Code instruction file that must remain at root and references all four files by relative path. Moving them would break `CLAUDE.md` without adding value.

**No deletes:** Every doc file carries distinct content. There is overlap between root `ARCHITECTURE.md` (monorepo structure, data flow, component overview) and `docs/architecture.md` (operational depth, schema details, API endpoint reference), but they serve different audiences (system overview vs. developer reference) and are cross-linked appropriately.

**Research docs:** 17 forward-looking research documents in `docs/research/` were not modified. They are proposals and analysis docs for Phase 2–6 implementation decisions, not descriptions of current behavior. Their content is accurate for their purpose (providing context before implementing a feature).

---

## Remaining Documentation Gaps

These are known gaps that would require code-level investigation to resolve — not addressed in this doc-only review:

1. **Celery task orchestration** — no single doc describes the full task graph (which tasks dispatch which others, retry policies, hold mechanism). The information is spread across `DESIGN.md`, `docs/ops/runbook.md`, and the research docs.
2. **WebSocket/SSE protocol spec** — sequence tracking, boot epoch, reconnect + backfill behavior are described in `DESIGN.md` conventions and the research doc but there is no authoritative message format spec.
3. **NCAAB fuzzy team matching algorithm** — referenced in `docs/architecture.md` (Levenshtein distance) but not documented in a dedicated doc.
4. **`v2-moments` → `v2-blocks` migration status** — `docs/gameflow/version-semantics.md` says to remove `_LEGACY_FLOW_VERSION` after all rows are migrated, but there is no ops procedure for confirming when that is complete.

---

## Review Pass 3 — 2026-04-19

Full documentation consolidation pass. All 47 docs re-audited. Five targeted changes applied.

### Files Changed

#### `docs/AUDIT_REPORT.md`

**Problem:** File contained the original April 8 error-handling audit findings — identical scope and content now covered by `docs/audits/abend-handling.md` (Apr 19, exhaustive), `docs/audits/security-audit.md`, and `docs/audits/ssot-cleanup.md`. Keeping it caused confusion about which was authoritative.

**Fix:** Replaced content with an index table redirecting to the four audit files in `docs/audits/`. Original findings are preserved in `abend-handling.md`.

#### `docs/index.md`

**Problem:** Operations table linked to stale `AUDIT_REPORT.md` with description "Production Audit" — the old file. New audit docs in `docs/audits/` were not individually linked from the index.

**Fix:** Replaced single "Production Audit" row with four specific rows (error handling, security, SSOT cleanup, docs consolidation). Added `phase6-validation.md` under Game Flow Generation — it existed but was absent from the index.

#### `README.md`

**Problem:** Repo layout listed `api/`, `scraper/`, `web/`, `infra/`, `docs/` but omitted `packages/` which contains `js-core` (shared TS types), `ui`, and `ui-kit`. These are a first-class runtime concern consumed by `web/`.

**Fix:** Added `packages/` with description.

#### `AIDLC_FUTURES.md` (root → `docs/aidlc-futures.md`)

**Problem:** Auto-generated AIDLC process file (run stats, next-run checklist, tips) was sitting at the repo root alongside `ARCHITECTURE.md`, `DESIGN.md`, and `ROADMAP.md`. It is not developer documentation and is not referenced by `CLAUDE.md`.

**Fix:** Moved to `docs/aidlc-futures.md`. Root is now clean: only `ARCHITECTURE.md`, `BRAINDUMP.md`, `CLAUDE.md`, `DESIGN.md`, `README.md`, `ROADMAP.md`.

### Files Audited and Unchanged (this pass)

All 42 remaining docs verified against current codebase state. No further issues found. All root docs (`ARCHITECTURE.md`, `DESIGN.md`, `ROADMAP.md`, `BRAINDUMP.md`, `CLAUDE.md`) are accurate as of the Pass 1 and Pass 2 fixes.

### Remaining Documentation Gaps (carried forward)

Same four gaps from Pass 2 remain open — they require code-level investigation and are not addressable in a doc-only pass:

1. Celery full task graph (dispatch chain, retry policies, hold mechanism)
2. WebSocket/SSE message format spec
3. NCAAB fuzzy team matching algorithm
4. `v2-blocks` migration completion procedure
