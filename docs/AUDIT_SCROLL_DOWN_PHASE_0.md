# Scroll Down System Audit — Phase 0

> **Status:** Read-Only Analysis (No Code Changes)
> **Scope:** Story generation, social integration, UI assumptions
> **Date:** 2026-02-03

---

## Guiding Invariants (Non-Negotiable)

These product constraints MUST be preserved in all future work:

1. **Collapsed game flow must be consumable in 20–60 seconds**
2. **Narrative works with zero social data**
3. **Social content is contextual, never required**
4. **No tweet is ever play-authoritative**
5. **Expansion is opt-in and never implied**

---

## Executive Summary

The current architecture maintains **strong separation** between story generation and social content. Stories are derived exclusively from PBP data via a deterministic pipeline. Social posts are an independent, optional layer that can be absent without breaking any core functionality.

**Key finding:** The system largely COMPLIES with the guiding invariants. Social content is already contextual and non-authoritative. However, there are potential growth vectors for story length and some UI patterns that could evolve toward coupling if not monitored.

---

## 1. Story Generation Pipeline

### 1.1 Architecture Overview

**Location:** `api/app/services/pipeline/`

The story pipeline is a 5-stage sequential process:

| Stage | Purpose | Key File |
|-------|---------|----------|
| NORMALIZE_PBP | Fetch and normalize raw PBP from database | `stages/normalize_pbp.py` |
| GENERATE_MOMENTS | Segment normalized plays into condensed moments | `stages/generate_moments.py` |
| VALIDATE_MOMENTS | Strict validation against story contract | `stages/validate_moments.py` |
| RENDER_NARRATIVES | Generate narrative prose using OpenAI | `stages/render_narratives.py` |
| FINALIZE_MOMENTS | Persist completed story to database | `stages/finalize_moments.py` |

**Orchestration:** `executor.py`

### 1.2 How Moments Are Constructed

**File:** `stages/generate_moments.py`

Moments are built via deterministic rule-based segmentation (NOT AI):

1. Iterate through normalized PBP events ordered by `play_index`
2. Accumulate plays into current moment
3. Check **HARD** boundary conditions (must close immediately):
   - Period boundary (quarter change)
   - Lead change (6+ point swing)
   - Would exceed `MAX_EXPLICIT_PLAYS_PER_MOMENT` (5)
   - Reached `ABSOLUTE_MAX_PLAYS` (50)
4. Check **SOFT** boundary conditions (prefer closing):
   - Reached `SOFT_CAP_PLAYS` (30)
   - Scoring play after 2/3 of soft cap
   - Stoppage (timeout/review)
   - Possession change/turnover

### 1.3 Key Thresholds and Limits

**File:** `stages/moment_types.py`

| Constant | Value | Impact on Length |
|----------|-------|------------------|
| `SOFT_CAP_PLAYS` | 30 | Prefer closing at this point |
| `ABSOLUTE_MAX_PLAYS` | 50 | Hard safety valve |
| `MIN_PLAYS_BEFORE_SOFT_CLOSE` | 15 | Minimum moment size |
| `MAX_EXPLICIT_PLAYS_PER_MOMENT` | 5 | Max narrated plays per moment |
| `PREFERRED_EXPLICIT_PLAYS` | 3 | Target for balanced narratives |

**Narrative length guidance (prompt-based):**
- Target: 6-10 sentences per moment
- Structure: 2-3 paragraphs per moment

### 1.4 Style and Tone Enforcement

**File:** `stages/prompt_builders.py`, `stages/narrative_types.py`

**FORBIDDEN PHRASES** (hard validation):
- Momentum/flow: "momentum", "turning point", "swing", "shift"
- Temporal: "earlier in the game", "later in the game", "previously"
- Summary: "in summary", "overall", "ultimately", "key moment", "crucial"
- Speculation: "could have", "might have", "seemed to"
- Subjective: "dominant", "electric", "huge", "incredible", "clutch"
- Crowd/atmosphere: "crowd erupted", "fans", "atmosphere"
- Intent/psychology: "wanted to", "tried to", "needed to", "frustrated"

### 1.5 Validation Rules (Strict, No Auto-Correction)

**File:** `stages/validate_moments.py`

Seven critical rules (all must pass or pipeline fails):

1. Non-empty play_ids in every moment
2. Explicit narration guarantee (1-5 plays per moment)
3. No overlapping plays across moments
4. Canonical ordering by first play_index
5. Valid play references (all play_ids exist in PBP)
6. Score never decreases
7. Score continuity (score_before[n] = score_after[n-1])

### 1.6 Implicit Assumptions

| Assumption | Location | Description |
|------------|----------|-------------|
| Play ordering | `generate_moments.py` | Assumes `play_index` is sequential and gapless |
| Score continuity | `validate_moments.py` | Assumes scores only increase or stay same |
| Period boundaries | `boundary_detection.py` | Quarter changes always force moment closure |
| Three-pointer detection | `game_stats_helpers.py` | Distance ≥ 22 feet = 3-pointer |

### 1.7 Logic That Could Increase Story Length

**Current growth vectors:**

1. **Soft cap adjustment** — Increasing `SOFT_CAP_PLAYS` creates longer moments, but fewer of them
2. **Explicit plays per moment** — Increasing `MAX_EXPLICIT_PLAYS_PER_MOMENT` adds more narrated content
3. **Sentence targets** — 6-10 sentences is prompt-guided, not enforced
4. **Context expansion** — Adding more player stats or lead context to prompts

**NOT currently implemented but could be added:**
- Post-moment commentary
- Cumulative box score expansion beyond top 5 players
- AI-generated transitions between moments

---

## 2. Social Logic

### 2.1 Scraping Infrastructure

**Location:** `scraper/sports_scraper/social/`

| File | Purpose |
|------|---------|
| `collector.py` | Main orchestrator (`XPostCollector`) |
| `playwright_collector.py` | Headless browser scraping via Playwright |
| `models.py` | Pydantic models for posts |
| `registry.py` | Team account registry helper |
| `rate_limit.py` | In-memory rate limiter (300 req/15 min) |

### 2.2 Scraping Triggers and Windows

**Trigger points:** Social posts are collected when `config.social=True` is passed to `IngestionConfig`. There is NO automatic scheduled social scraping.

**Collection window:**
- Pregame: `tip_time - 180 minutes` (configurable)
- Postgame: `tip_time + 3 hours + 180 minutes` (configurable)

### 2.3 League Coverage

| League | Social Enabled | Config Source |
|--------|----------------|---------------|
| NBA | ✅ Yes | `config_sports.py` |
| NHL | ✅ Yes | `config_sports.py` |
| NCAAB | ❌ No | `config_sports.py` |

### 2.4 Tweet → Play/Moment Association

**CRITICAL FINDING: Social posts are NOT mapped to individual plays.**

**Association model:**
- **Game-level:** Posts attached to `game_id` and `team_id`
- **Timestamp-based:** Posts ordered by `posted_at` (UTC)
- **Phase-based:** Posts assigned to phases based on timestamp boundaries

**Files involved:**
- `api/app/services/social_events.py:240-269` — `assign_social_phase()`
- `api/app/services/timeline_events.py:111-155` — `merge_timeline_events()`

**Phase assignment logic:**
```
if posted_at < game_start: phase = "pregame"
elif posted_at < q1_end: phase = "q1"
elif posted_at < q2_end: phase = "q2"
... etc
```

### 2.5 Role Assignment (Heuristic)

**File:** `api/app/services/social_events.py:104-182`

Roles define WHY a post is in the timeline (not WHAT it is):

| Phase | Possible Roles |
|-------|----------------|
| Pregame | `context`, `hype` |
| In-game | `momentum`, `milestone`, `reaction`, `commentary` |
| Postgame | `result`, `reflection` |
| Universal | `highlight`, `ambient` |

### 2.6 Ordering Guarantees

**File:** `api/app/services/timeline_events.py:111-155`

Timeline merge uses **PHASE-FIRST** ordering:

1. **Primary:** Phase order (pregame → q1 → q2 → ... → postgame)
2. **Secondary:** Intra-phase order (clock for PBP, seconds since phase start for social)
3. **Tertiary:** Event type (PBP before tweet at ties)

**synthetic_timestamp is NOT used for ordering** — it exists only for display/debugging.

### 2.7 Assumptions to Watch

| Assumption | Location | Risk |
|------------|----------|------|
| Posts have text | `social_events.py:299-310` | Posts with empty text are DROPPED |
| Phase boundaries are known | `timeline_phases.py` | Requires reliable `tip_time` |
| Roles are decorative | `social_events.py` | If roles become filtering criteria, this changes |

---

## 3. UI Assumptions

### 3.1 Component Structure

**Game detail page stack:**

| File | Purpose |
|------|---------|
| `web/src/app/admin/sports/games/[gameId]/page.tsx` | Server entry |
| `.../GameDetailClient.tsx` | Main logic (730 lines) |
| `.../StorySection.tsx` | Story/flow display (250 lines) |
| `.../SocialPostsSection.tsx` | Social posts display (110 lines) |
| `.../PbpSection.tsx` | Play-by-play display (115 lines) |

### 3.2 Story Display Behavior

**File:** `web/src/app/admin/sports/games/[gameId]/StorySection.tsx`

- **Conditional rendering:** Returns `null` if `!hasStory` (line 205-206)
- **Default state:** Opens by default (`defaultOpen={true}`)
- **No fallback message:** Section is simply absent if no story exists
- **Validation warnings:** Yellow box displays if `!story.validationPassed`

### 3.3 Social Display Behavior

**File:** `web/src/app/admin/sports/games/[gameId]/SocialPostsSection.tsx`

- **Conditional rendering:** Shows "No social posts found" if `filteredPosts.length === 0`
- **Default state:** Closed by default (`defaultOpen={false}`)
- **Filtering:** Only shows posts with content (text, image, or video)
- **Pagination:** 10 posts per page, controls appear if > 10 posts

### 3.4 Layout Changes Driven by Data Presence

| Scenario | UI Impact |
|----------|-----------|
| No story | "Game Flow" section absent from DOM |
| Story with validation errors | Yellow warning box above moments |
| No social posts | Section shows fallback message |
| 1-10 posts | Single page, no pagination |
| 11+ posts | Pagination controls appear |

### 3.5 Potential Layout Breaks if Social Removed

If all tweets were removed from a game:

1. Pagination controls disappear (~80px vertical space)
2. Post count message disappears (~30px)
3. Post grid collapses (variable, ~350px per 10 items)
4. Section header remains with "No social posts found" message

**Total potential shift:** 200-400px vertical collapse, but NO breaking changes.

### 3.6 Visual Affordances

| Element | Location | Implication |
|---------|----------|-------------|
| "Flow" badge (green/red) | `GameDetailClient.tsx:192` | Implies story is expected data |
| Story opens by default | `StorySection.tsx:210` | Story is primary narrative |
| Social closed by default | `SocialPostsSection.tsx` | Social is supplementary |
| Media type badges | `SocialPostsSection.tsx:50-51` | Posts categorized by content type |

---

## 4. Coupling Points

### 4.1 Story ↔ PBP Coupling

**Status:** TIGHT (by design)

| Coupling Point | File | Description |
|----------------|------|-------------|
| Play ordering | `generate_moments.py` | Stories are derived from PBP `play_index` |
| Score tracking | `score_detection.py` | Score continuity validated against PBP |
| Player names | `prompt_builders.py` | Narratives reference PBP player names |
| Game clock | `moment_types.py` | Moment boundaries use `game_clock` |

**Assessment:** This coupling is intentional and correct. Stories MUST be grounded in PBP data per the Story Contract.

### 4.2 Social ↔ PBP Coupling

**Status:** NONE

Social posts and PBP events are merged at the timeline level but have no direct dependencies:

- Posts are not matched to specific plays
- Posts do not reference play_ids
- Posts are ordered by phase, not by play sequence
- Timeline generation works with zero social posts

### 4.3 Social ↔ Story Coupling

**Status:** NONE

The story generation pipeline has ZERO social inputs:

- `api/app/services/pipeline/` contains no social imports
- `SportsGameStory` table has no social references
- Stories are generated before/without timeline generation
- Narrative prose never references tweets

### 4.4 UI ↔ Social Presence

**Status:** MINIMAL

| Component | Behavior if Social Absent |
|-----------|---------------------------|
| `StorySection` | Renders normally (no dependency) |
| `SocialPostsSection` | Shows fallback message |
| `GameDetailClient` | Badge shows "Social (0)" |
| Layout | Graceful collapse, no breaks |

**Critical comment in code:**
```typescript
// SocialPostsSection.tsx lines 15-16
// IMPORTANT: Do NOT sort by timestamp here.
// Trust backend order. See docs/NARRATIVE_TIME_MODEL.md
// Timestamps do not imply causality or reading order.
```

---

## 5. Logic to Delete (Later Phases)

### 5.1 Fragile Joins

| Location | Description | Why Delete |
|----------|-------------|------------|
| None identified | — | — |

**Assessment:** No fragile joins found. The current architecture maintains clean separation.

### 5.2 Over-Precise Mappings

| Location | Description | Why Delete |
|----------|-------------|------------|
| None identified | — | — |

**Assessment:** No tweet → play mappings exist. Phase-based ordering is appropriately coarse.

### 5.3 Potential Future Risks

| Pattern | Location | Risk |
|---------|----------|------|
| Role-based filtering | `social_events.py:104-182` | If roles become required for display, this creates coupling |
| Phase boundary assumptions | `timeline_phases.py` | Requires reliable `tip_time` or social posts are skipped |
| Narrative length growth | `prompt_builders.py` | Sentence targets (6-10) could drift upward |

---

## 6. Logic to Preserve

### 6.1 Narrative Ordering Guarantees

| Guarantee | Location | Why Preserve |
|-----------|----------|--------------|
| Canonical moment ordering | `validate_moments.py:rule 4` | Ensures game-time sequence |
| Play coverage (no gaps) | `validate_moments.py:rule 3` | Every play in exactly one moment |
| Score continuity | `validate_moments.py:rules 6-7` | Maintains score progression |

### 6.2 Trust Invariants

| Invariant | Location | Why Preserve |
|-----------|----------|--------------|
| Explicit play references | `validate_moments.py:rule 2` | Every moment has 1-5 traceable plays |
| Forbidden phrases | `narrative_types.py` | Prevents speculative/subjective prose |
| No cross-period moments | `boundary_detection.py` | Period change forces closure |

### 6.3 Short-Form Reading Support

| Behavior | Location | Why Preserve |
|----------|----------|--------------|
| Soft cap (30 plays) | `moment_types.py` | Controls moment size |
| Hard cap (50 plays) | `moment_types.py` | Safety valve prevents runaway moments |
| Default closed social | `SocialPostsSection.tsx` | Social is opt-in, not forced |
| Story opens by default | `StorySection.tsx` | Story is primary narrative |

---

## 7. Invariant Compliance Check

### 7.1 "Collapsed game flow must be consumable in 20–60 seconds"

**Status:** ⚠️ NEEDS MONITORING

**Current state:**
- Typical game produces 15-25 moments
- Each moment has 2-3 paragraphs (6-10 sentences)
- No explicit word count or reading time limits

**Concerns:**
- No hard limits on total story length
- Sentence targets are prompt-guided, not enforced
- Growth vectors exist (more explicit plays, longer narratives)

**Recommendation:** Add instrumentation to track actual reading time estimates per story.

### 7.2 "Narrative works with zero social data"

**Status:** ✅ COMPLIANT

**Evidence:**
- Story pipeline has zero social inputs
- `SportsGameStory` has no social references
- Stories are generated independently of timeline generation

### 7.3 "Social content is contextual, never required"

**Status:** ✅ COMPLIANT

**Evidence:**
- `build_social_events()` returns empty list if no posts
- `merge_timeline_events()` works with empty social_events
- UI shows fallback message, no breaks

### 7.4 "No tweet is ever play-authoritative"

**Status:** ✅ COMPLIANT

**Evidence:**
- No tweet → play_id mapping exists
- Tweets are phase-assigned, not play-assigned
- Narrative references only PBP data
- Role assignment is decorative (hype, reaction, etc.)

### 7.5 "Expansion is opt-in and never implied"

**Status:** ✅ COMPLIANT

**Evidence:**
- Story Contract explicitly states expansion is "consumption concern"
- UI uses collapsible sections
- Social section defaults to closed
- No auto-expand behavior

---

## 8. Files Reference

### Story Pipeline
- `api/app/services/pipeline/executor.py`
- `api/app/services/pipeline/models.py`
- `api/app/services/pipeline/stages/generate_moments.py`
- `api/app/services/pipeline/stages/validate_moments.py`
- `api/app/services/pipeline/stages/render_narratives.py`
- `api/app/services/pipeline/stages/moment_types.py`
- `api/app/services/pipeline/stages/boundary_detection.py`
- `api/app/services/pipeline/stages/explicit_selection.py`
- `api/app/services/pipeline/stages/prompt_builders.py`
- `api/app/services/pipeline/stages/narrative_types.py`

### Timeline Generation
- `api/app/services/timeline_generator.py`
- `api/app/services/timeline_events.py`
- `api/app/services/timeline_phases.py`
- `api/app/services/timeline_types.py`
- `api/app/services/social_events.py`

### Social Scraping
- `scraper/sports_scraper/social/collector.py`
- `scraper/sports_scraper/social/playwright_collector.py`
- `scraper/sports_scraper/social/models.py`

### Database Models
- `api/app/db_models.py` (SportsGameStory, GameSocialPost, SportsGameTimelineArtifact)

### UI Components
- `web/src/app/admin/sports/games/[gameId]/GameDetailClient.tsx`
- `web/src/app/admin/sports/games/[gameId]/StorySection.tsx`
- `web/src/app/admin/sports/games/[gameId]/SocialPostsSection.tsx`

### Canonical Documents
- `docs/STORY_CONTRACT.md`
- `docs/NARRATIVE_TIME_MODEL.md`

---

## 9. Changelog

| Date | Author | Change |
|------|--------|--------|
| 2026-02-03 | Phase 0 Audit | Initial system audit |
