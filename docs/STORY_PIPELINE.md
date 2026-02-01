# Story Pipeline

Multi-stage pipeline for generating condensed moment-based game stories from play-by-play data.

## Overview

The pipeline transforms raw PBP data into narrative stories through 5 sequential stages. Each stage produces output consumed by the next stage.

```
NORMALIZE_PBP → GENERATE_MOMENTS → VALIDATE_MOMENTS → RENDER_NARRATIVES → FINALIZE_MOMENTS
```

**Location:** `api/app/services/pipeline/`

## Stages

### 1. NORMALIZE_PBP

**Purpose:** Fetch and normalize play-by-play data from the database.

**Input:** Game ID
**Output:** Normalized plays with phase assignments, synthetic timestamps, score states

**Implementation:** `stages/normalize_pbp.py`

**Output Schema:**
```python
{
    "pbp_events": [...],        # Normalized play records
    "game_start": "...",        # ISO datetime
    "game_end": "...",          # ISO datetime
    "has_overtime": bool,
    "total_plays": int,
    "phase_boundaries": {...}   # Phase → (start, end) times
}
```

### 2. GENERATE_MOMENTS

**Purpose:** Segment PBP into condensed moments with explicit narration targets.

**Input:** Normalized PBP events
**Output:** Ordered list of moments with play assignments

**Implementation:** `stages/generate_moments.py`

**Segmentation Rules:**
- Moments are contiguous sets of plays (typically 1-5)
- Natural boundaries: timeouts, dead balls, period ends
- Score-change boundaries when applicable
- No play appears in multiple moments

**Output Schema:**
```python
{
    "moments": [
        {
            "play_ids": [1, 2, 3],
            "explicitly_narrated_play_ids": [2],
            "period": 1,
            "start_clock": "11:42",
            "end_clock": "11:00",
            "score_before": [0, 0],
            "score_after": [3, 0]
        },
        ...
    ]
}
```

### 3. VALIDATE_MOMENTS

**Purpose:** Validate moment structure against story contract requirements.

**Input:** Generated moments + normalized plays
**Output:** Validation status and any errors

**Implementation:** `stages/validate_moments.py`

**Validation Rules:**
1. Non-empty `play_ids` in each moment
2. Non-empty `explicitly_narrated_play_ids` (subset of `play_ids`)
3. No overlapping plays between moments
4. Canonical ordering by play_index
5. All play references exist in PBP data

**Output Schema:**
```python
{
    "validated": true,
    "errors": []
}
# OR
{
    "validated": false,
    "errors": ["EMPTY_PLAY_IDS: Moment 0 has empty play_ids", ...]
}
```

**Failure Behavior:** Stage fails if validation errors exist. No auto-correction.

### 4. RENDER_NARRATIVES

**Purpose:** Generate narrative text for each moment using OpenAI.

**Input:** Validated moments + play data
**Output:** Moments with narrative text populated

**Implementation:** `stages/render_narratives.py`

**OpenAI Usage:**
- Moments batched (up to 15 per call) for efficiency
- Input: Play descriptions, scores, clock values per batch
- Output: Narrative strings for all moments in the batch

**Constraints:**
- OpenAI only writes prose - it does not decide moment boundaries
- Narratives must reference explicitly narrated plays
- Forbidden phrases: "momentum", "turning point", "crucial", etc.

**Post-Rendering Validation:**
- Narrative is non-empty
- No forbidden phrases detected
- Length within expected bounds

**Output Schema:**
```python
{
    "rendered": true,
    "moments": [
        {
            "play_ids": [...],
            "explicitly_narrated_play_ids": [...],
            "narrative": "Durant sinks a three-pointer from the corner...",
            ...
        }
    ],
    "openai_calls": 15
}
```

### 5. FINALIZE_MOMENTS

**Purpose:** Persist completed story to database.

**Input:** Rendered moments
**Output:** Persistence confirmation

**Implementation:** `stages/finalize_moments.py`

**Storage:**
- Table: `sports_game_stories`
- Column: `moments_json` (JSONB)
- Version: `story_version = "v2-moments"`
- Metadata: `moment_count`, `validated_at`

**Output Schema:**
```python
{
    "finalized": true,
    "story_id": 123,
    "story_version": "v2-moments",
    "moment_count": 15
}
```

## Pipeline Execution

### API Endpoints

**Base path:** `/api/admin/sports/pipeline`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/runs` | POST | Start a new pipeline run |
| `/runs/{run_id}` | GET | Get run status and stage details |
| `/runs/{run_id}/advance` | POST | Advance to next stage |
| `/batch` | POST | Run pipeline for multiple games |

### Database Tables

| Table | Purpose |
|-------|---------|
| `sports_game_pipeline_runs` | Pipeline execution records |
| `sports_game_pipeline_stages` | Per-stage output and logs |
| `sports_game_stories` | Persisted story artifacts |

### Execution Modes

**Auto-chain:** All stages run sequentially without pause.
**Manual:** Each stage requires explicit advancement (for debugging).

## Story Output

The final story is an ordered list of condensed moments matching the [Story Contract](STORY_CONTRACT.md).

### API Access

```
GET /api/admin/sports/games/{game_id}/story
```

Returns the persisted story exactly as stored:

```json
{
    "gameId": 123,
    "story": {
        "moments": [...]
    },
    "plays": [...],
    "validationPassed": true,
    "validationErrors": []
}
```

Returns 404 if no story exists.

### Discovery

Games with stories are discoverable via the `has_story` flag:

```sql
has_story = moments_json IS NOT NULL
```

## Key Principles

1. **Moments are mechanical** - Segmentation is deterministic, not AI-driven
2. **OpenAI is prose-only** - It renders narratives, not structure
3. **Full traceability** - Every narrative sentence maps to specific plays
4. **No abstraction** - No headers, sections, or thematic groupings
5. **Validation is strict** - Pipeline fails on contract violations

## See Also

- [STORY_CONTRACT.md](STORY_CONTRACT.md) - Authoritative story specification
- [PBP_STORY_ASSUMPTIONS.md](PBP_STORY_ASSUMPTIONS.md) - PBP data requirements
- [API.md](API.md) - Complete API reference
