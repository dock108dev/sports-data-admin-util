# Story Pipeline Contract Review

This document reviews the pipeline infrastructure for story generation, mapping contract requirements to current implementation state.

---

## Task 1: Pipeline Contract Analysis

### Where Story Output Is Expected

The pipeline has 5 stages executed in order:
1. **NORMALIZE_PBP** - Fetches and normalizes play-by-play data
2. **DERIVE_SIGNALS** - (stub) See correction below
3. **GENERATE_MOMENTS** - (stub) Segment PBP into moments, render narratives
4. **VALIDATE_MOMENTS** - (stub) Validate moments against contract
5. **FINALIZE_MOMENTS** - (stub) Persist final story to database

**Story output is expected from GENERATE_MOMENTS** and persisted by **FINALIZE_MOMENTS**.

### Which Stage Produces Artifacts

| Stage | Current State | Expected Output |
|-------|---------------|-----------------|
| NORMALIZE_PBP | Implemented | `normalized_plays[]` with parsed clock, scores, teams |
| DERIVE_SIGNALS | Stub | **RECOMMEND DELETION** - see correction below |
| GENERATE_MOMENTS | Stub | `moments[]` - ordered CondensedMoment objects |
| VALIDATE_MOMENTS | Stub | `validated: true/false`, `validation_errors[]` |
| FINALIZE_MOMENTS | Stub | `story_saved: true`, persistence confirmation |

### Where Persistence Currently Occurs

**Stage outputs are persisted to:** `GamePipelineStage.output_json` (JSONB column per stage)

**Story persistence location:** None currently. The `FINALIZE_MOMENTS` stub does not persist to any story table.

**Relevant tables:**
```
sports_game_pipeline_runs     - Tracks pipeline executions
sports_game_pipeline_stages   - Stage-level output and logs
sports_game_stories           - LEGACY: chapter-based story cache
sports_game_timeline_artifacts - Timeline visualization data
```

### How `has_story` Is Determined Today

**Current logic** (in `api/app/routers/sports/games.py:173-178`):
```python
story_check_stmt = select(db_models.SportsGameStory.game_id).where(
    db_models.SportsGameStory.game_id.in_(game_ids),
    db_models.SportsGameStory.has_compact_story.is_(True),
)
```

**Problem:** The pipeline does NOT write to `SportsGameStory`. Pipeline runs complete successfully, but `has_story` remains `False` because:
- Pipeline writes stage outputs to `GamePipelineStage.output_json`
- `has_story` check queries `SportsGameStory.has_compact_story`
- These are completely disconnected tables

---

## Task 2: Story Output to Persistence Mapping

### Story Contract Requirements

From `docs/story_contract.md`, a Story is:
- An **ordered list of condensed moments**
- Each moment contains required fields:

| Field | Type | Purpose |
|-------|------|---------|
| `play_ids` | `list[int]` | PBP play identifiers backing this moment |
| `explicitly_narrated_play_ids` | `list[int]` | Subset of play_ids that are explicitly described |
| `start_clock` | `string` | Game clock at first play (metadata) |
| `end_clock` | `string` | Game clock at last play (metadata) |
| `period` | `int` | Game period (metadata) |
| `score_before` | `(home, away)` | Score at moment start |
| `score_after` | `(home, away)` | Score at moment end |
| `narrative` | `string` | Human-readable text describing the plays |

### Existing Models vs. Contract

#### `SportsGameStory` (LEGACY)
```python
# Designed for chapter-based prose, NOT condensed moments
chapters_json: list[dict]       # Hierarchical chapter structure
summaries_json: list[dict]      # Section summaries
titles_json: list[dict]         # Chapter titles
compact_story: str              # Full prose narrative
has_compact_story: bool         # What has_story checks
```

**Verdict:** Does NOT match. This table is for chapter-based storytelling with prose narratives. The new Story contract explicitly prohibits chapters, headers, and sections.

#### `SportsGameTimelineArtifact`
```python
# Designed for timeline visualization
timeline_json: list[dict]       # Timeline events
summary_json: dict              # Game summary
game_analysis_json: dict        # Analysis data
```

**Verdict:** Does NOT match. This is for timeline visualization, not condensed moment narration.

#### `GamePipelineStage.output_json`
```python
# Stage-level output (JSONB)
output_json: dict | None        # Arbitrary stage output
```

**Verdict:** Suitable for intermediate stage data, but not for permanent story persistence. This is ephemeral per-run data.

### Persistence Recommendation

**Option A: Extend SportsGameStory** (Recommended for MVP)
Add new columns to existing table:
```python
# New columns for condensed moments
moments_json: list[CondensedMoment]    # The story as ordered moments
has_moments: bool                       # Flag for new story type
moments_version: str                    # Contract version
validation_passed: bool                 # Did moments pass validation
moment_count: int                       # Number of moments
```

Update `has_story` check to:
```python
has_story = has_compact_story OR has_moments
```

**Option B: New Table**
Create `sports_game_condensed_stories` with clean schema matching contract.

---

## Task 3: Frontend Consumption Review

### How Frontend Checks for Story

**API returns `has_story: boolean`** in `GameSummary` type.

**Frontend types exist** in `web/src/lib/api/sportsAdmin/storyTypes.ts`:
```typescript
export type CondensedMoment = {
  play_ids: number[];
  explicitly_narrated_play_ids: number[];
  start_clock: string;
  end_clock: string;
  period: number;
  score_before: ScoreTuple;
  score_after: ScoreTuple;
  narrative: string;
};

export type StoryOutput = {
  moments: CondensedMoment[];
};

export type StoryResponse = {
  game_id: number;
  sport: string;
  home_team: string;
  away_team: string;
  story: StoryOutput;
  plays: PlayData[];         // For expansion view
  validation_passed: boolean;
  validation_errors: string[];
};
```

**These types are contract-compliant.** Frontend is ready to consume Story data.

### How Frontend Fetches Story

**No fetch function currently exists.** The `StoryResponse` type exists but there's no:
- API endpoint to GET story for a game
- API client function to call that endpoint
- UI component to render moments

### How Frontend Renders Story

**No rendering exists in `GameDetailClient.tsx`.** The game detail page shows:
- Game metadata
- Team/player stats
- Odds
- Social posts
- PBP plays

But NO story section. The `has_story` flag is not displayed in the UI either.

### Frontend Gaps

| Gap | Current State | Required |
|-----|---------------|----------|
| Story flag display | Not shown | Add "Story" to data flags |
| Story fetch | No endpoint/client | Add `getGameStory(gameId)` API function |
| Story rendering | No component | Add flat moment list component |
| Moment expansion | Types exist | Add expansion UI for play_ids |

---

## Task 4: Story Readiness Checklist

When implementing story logic in the pipeline stages, verify these items:

### Backend Checklist

- [ ] **GENERATE_MOMENTS stage**
  - [ ] Segments PBP directly into moment boundaries (mechanical segmentation)
  - [ ] Selects explicitly narrated plays within each segment
  - [ ] Calls OpenAI ONLY to render narrative text for each moment
  - [ ] Produces `moments[]` matching `CondensedMoment` schema
  - [ ] Each moment has non-empty `play_ids`
  - [ ] Each moment has non-empty `explicitly_narrated_play_ids` (subset of play_ids)
  - [ ] Each moment has non-empty `narrative`
  - [ ] Moments ordered by `play_index` (chronological game order)
  - [ ] No play_id appears in multiple moments

- [ ] **VALIDATE_MOMENTS stage**
  - [ ] Validates all contract requirements from `story_contract.md`
  - [ ] Checks play_ids exist in PBP data
  - [ ] Checks narrated_ids are subset of play_ids
  - [ ] Checks moment ordering by play_index
  - [ ] Returns clear validation errors

- [ ] **FINALIZE_MOMENTS stage**
  - [ ] Persists to correct table (see Task 2 recommendation)
  - [ ] Sets `has_moments = True` (or equivalent flag)
  - [ ] Updates `has_story` check to include moments
  - [ ] Stores moment_count, validation status

- [ ] **has_story integration**
  - [ ] Update `games.py` to check new moments flag
  - [ ] Update count queries for `with_story_count`

### Frontend Checklist

- [ ] **Story API client**
  - [ ] Add `getGameStory(gameId): Promise<StoryResponse>`
  - [ ] Handle 404 (no story) gracefully

- [ ] **Story flag in UI**
  - [ ] Add "Story" to data availability flags in GameDetailClient
  - [ ] Show green/red badge like other flags

- [ ] **Story rendering component**
  - [ ] Create component to render flat ordered list of moments
  - [ ] NO headers, sections, or grouping
  - [ ] Display score progression inline per moment
  - [ ] Show narrative text for each moment

- [ ] **Moment expansion**
  - [ ] Click moment to expand backing plays
  - [ ] Highlight explicitly narrated plays
  - [ ] Show which plays are implicit context

- [ ] **Story generator page**
  - [ ] Refresh games after bulk generation shows correct `has_story` status

### Database Checklist

- [ ] Migration to add moments columns to `SportsGameStory` (if Option A)
- [ ] OR migration to create new table (if Option B)
- [ ] Index on new `has_moments` column
- [ ] Backfill strategy for existing data (none needed if new system)

---

## Summary

| Component | Status | Action Needed |
|-----------|--------|---------------|
| Pipeline infrastructure | Complete | None |
| NORMALIZE_PBP | Implemented | None |
| DERIVE_SIGNALS | Stub | **DELETE** - see correction below |
| GENERATE_MOMENTS | Stub | Implement segmentation + narrative rendering |
| VALIDATE_MOMENTS | Stub | Implement contract validation |
| FINALIZE_MOMENTS | Stub | Implement persistence |
| Story persistence table | Gap | Add moments columns or new table |
| has_story flag | Points to legacy | Update to include moments |
| Frontend types | Ready | None |
| Frontend fetch | Missing | Add API client function |
| Frontend render | Missing | Add flat moment list component |

---

# Corrected Story Pipeline Contract Summary

## CORRECTIONS TO PRIOR REVIEW

The prior review introduced concepts that violate the Story contract. This addendum corrects those errors and establishes authoritative guidance.

### Mandatory Corrections

**1. Story has NO momentum, beats, themes, or narrative signals.**

The Story contract explicitly prohibits:
- "Momentum swings"
- "Turning points"
- "Key stretches"
- "Narrative arcs"
- "Beat-based prose guidance"

These are abstract narrative constructs. Story deals only in concrete plays.

**2. Condensed moments are derived DIRECTLY from PBP, not from signals.**

Moment segmentation is a mechanical operation on raw PBP data. There is no intermediate "signal" layer. Moments are contiguous sets of plays grouped by natural game boundaries (stoppages, timeouts, period breaks) or fixed windowing rules.

**3. OpenAI is used ONLY for moment-level narrative rendering.**

OpenAI receives a set of plays and produces narrative text describing those plays. OpenAI does NOT:
- Decide which plays form a moment
- Identify "important" vs "unimportant" plays
- Detect momentum or narrative significance
- Generate moment boundaries

Moment boundaries are determined mechanically. OpenAI only writes prose.

**4. No stage uses OpenAI to "generate moments".**

The phrase "generate moments" is misleading. The correct description:
- GENERATE_MOMENTS **segments** PBP into moment boundaries (mechanical)
- GENERATE_MOMENTS **selects** which plays to narrate (rule-based)
- GENERATE_MOMENTS **renders** narrative text via OpenAI (prose only)

**5. Canonical ordering is by play_index; clock is metadata only.**

Moments are ordered by `play_index` - the chronological sequence in which plays occurred during the game. Clock values (`start_clock`, `end_clock`) are metadata for display purposes. They are NOT used for ordering logic.

**6. The UI renders a flat ordered list of moments with NO headers, sections, or grouping.**

The UI displays moments as a single sequential list. There are:
- NO period headers
- NO quarter sections
- NO thematic groupings
- NO narrative structure beyond the moment sequence

Score and period are displayed as inline metadata per moment.

---

## PIPELINE STAGE DECISION

### Decision: DELETE `DERIVE_SIGNALS`

The `DERIVE_SIGNALS` stage is **incompatible with the Story contract** and should be removed.

**Rationale:**
- The stage name implies deriving narrative meaning ("signals")
- The contract forbids momentum, runs, and lead-change labeling
- Any output this stage could produce is either:
  - Mechanical metadata (belongs in NORMALIZE_PBP)
  - Narrative interpretation (forbidden by contract)

**Recommendation:**
1. Remove `DERIVE_SIGNALS` from `PipelineStage` enum
2. Remove `execute_derive_signals` from stages
3. Update pipeline executor to skip from NORMALIZE_PBP → GENERATE_MOMENTS
4. Move any purely mechanical enrichment (score deltas, possession markers) to NORMALIZE_PBP if needed

**Revised Pipeline:**
```
NORMALIZE_PBP → GENERATE_MOMENTS → VALIDATE_MOMENTS → FINALIZE_MOMENTS
```

---

## What Story IS

- An **ordered list** of condensed moments
- Each moment is a **small set of contiguous PBP plays**
- Each moment has **at least one explicitly narrated play**
- Moments are ordered by **play_index** (game chronology)
- Narrative text describes **specific plays** that occurred
- Every claim in the narrative is **traceable to backing plays**

## What Story is NOT

- NOT a recap or summary
- NOT organized by quarters, periods, or sections
- NOT structured around narrative arcs or themes
- NOT generated by asking an LLM "what happened"
- NOT momentum-based or beat-based
- NOT hierarchical (no chapters, headers, titles)

## OpenAI Usage

OpenAI is invoked exactly once per moment to render narrative prose.

**Input:** A set of plays with their descriptions, scores, and clock values
**Output:** A narrative string describing those plays

OpenAI does NOT:
- Choose which plays to include
- Decide moment boundaries
- Identify narrative significance
- Produce anything other than prose text

## Moment Segmentation

Moments are segmented mechanically using one of:
- Natural game breaks (timeouts, dead balls, period ends)
- Fixed window rules (e.g., every N plays)
- Score-change boundaries (new moment when score changes)

The segmentation algorithm is deterministic and rule-based. It does not involve LLM inference.

## Ordering

- Primary key: `play_index` (integer, sequential)
- Moments appear in the order their first play occurred
- Clock values are metadata, not ordering keys
- Period is metadata, not a grouping mechanism

## UI Rendering

The UI displays:
```
[Moment 1 narrative] | Score: 0-0 → 3-0 | Q1 11:42
[Moment 2 narrative] | Score: 3-0 → 3-2 | Q1 10:15
[Moment 3 narrative] | Score: 3-2 → 5-2 | Q1 9:30
...
```

No headers. No sections. No grouping. A flat list.

---

## Reference for Implementation

All subsequent implementation tasks MUST:
1. Treat this addendum as authoritative
2. Reject any design that introduces signals, beats, or momentum
3. Use OpenAI only for narrative rendering
4. Order moments by play_index
5. Render UI as a flat list

Any implementation that violates these constraints is non-compliant with the Story contract.
