# Book + Chapters Model

**Status:** Phase 0 Implementation Complete  
**Date:** 2026-01-21  
**Replaces:** Legacy "Moments" concept

---

## Overview

The Book + Chapters model is a fundamental architectural reset of game storytelling.

**Core Principle:** A game is a book. Plays are pages. Chapters are contiguous play ranges that represent coherent scenes.

This model replaces the legacy "moments" concept, which suffered from event-first design and structural over-segmentation.

---

## Why "Moments" Were Removed

The legacy moments system had fundamental architectural problems:

### Problem 1: Event-First Design
Moments were created by reacting to events (tier crossings, lead flips) rather than tracking narrative intent. This produced:
- Over-segmentation (2-3x too many moments)
- Fragmented story beats split across multiple moments
- AI compensation to paper over structural problems

### Problem 2: Conflated Structure and Narrative
Moments tried to be both structural units (coverage, continuity) and narrative units (story beats). This created:
- Moment "types" (LEAD_BUILD, CUT, etc.) that were really narrative labels
- Merging logic (481 lines) to fix over-segmentation
- Coherence enforcement to repair fragmentation

### Problem 3: Unpredictable Boundaries
Moment boundaries were determined by:
- Ladder tier crossings (numeric thresholds)
- Scoring runs (heuristics)
- Multi-pass merging (repair logic)
- Coherence dampening (suppression)

This made moments unpredictable and hard to reason about.

### The Reset

The Book + Chapters model separates concerns:
- **Chapters** = Structure (where are the scene breaks?)
- **Narrative** = Story (what happened in each scene?)
- **AI** = Rendering (how do we describe it?)

Chapters are deterministic, reproducible, and simple. Narrative is generated after structure exists.

---

## Core Definitions

### Play

**The atomic unit of game action.**

A play is a single play-by-play event. Plays are the raw pages of the game's book. They are never modified or summarized.

```python
@dataclass
class Play:
    index: int              # Position in timeline (0-based)
    event_type: str         # Type of event (pbp, social, etc.)
    raw_data: dict[str, Any]  # Complete event data
```

**Properties:**
- Chronological
- Immutable
- Complete (contains all original data)

---

### Chapter

**A contiguous range of plays representing a single narrative scene.**

A chapter is the fundamental structural unit of game storytelling. It answers "where are the scene breaks?" not "what happened?"

```python
@dataclass
class Chapter:
    chapter_id: str         # Unique identifier (e.g., "ch_001")
    play_start_idx: int     # First play index (inclusive)
    play_end_idx: int       # Last play index (inclusive)
    plays: list[Play]       # All plays in this chapter
    reason_codes: list[str] # Why boundaries exist (for debugging)
```

**Properties:**
- Deterministic (same input → same output)
- Contiguous (no gaps between chapters)
- Complete coverage (every play in exactly one chapter)
- No narrative text (text is generated later)

**What Chapters Are:**
- Structural units for organizing plays
- Scene breaks in the game's story
- UI expansion boundaries
- Deterministic and reproducible

**What Chapters Are NOT:**
- Narrative labels (no "types")
- Event buckets (not defined by tier crossings)
- AI-generated (no AI in chapter creation)
- Fragments requiring merging

---

### GameStory

**A narrative artifact produced from chapters.**

The GameStory is the final output consumed by apps. It contains chapters (structure) and optional narrative text (AI-generated).

```python
@dataclass
class GameStory:
    game_id: int                # Database game ID
    chapters: list[Chapter]     # All chapters in chronological order
    compact_story: str | None   # Optional AI-generated summary
    metadata: dict[str, Any]    # Game metadata (teams, score, etc.)
```

**Properties:**
- Contains all chapters
- Validates structural integrity
- Optional AI-generated narrative
- Ready for API consumption

---

## Architecture

### Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ INPUT: Play-by-Play Timeline                                    │
│ • Raw PBP events from data feed                                 │
│ • Social posts (optional metadata)                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: Extract Plays                                           │
│ • Filter canonical PBP events                                   │
│ • Create Play objects                                           │
│ • Preserve chronological order                                  │
│                                                                  │
│ Output: List[Play]                                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: Detect Boundaries                                       │
│ • Identify structural inflection points                         │
│ • Phase 0: Quarter/period changes                               │
│ • Future: Narrative state changes                               │
│                                                                  │
│ CRITICAL: Boundaries are deterministic, not AI-driven           │
│                                                                  │
│ Output: List[ChapterBoundary]                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Create Chapters                                         │
│ • Partition plays at boundaries                                 │
│ • Ensure complete coverage (no gaps, no overlaps)               │
│ • Validate structural integrity                                 │
│                                                                  │
│ Output: List[Chapter]                                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Build GameStory                                         │
│ • Wrap chapters in GameStory                                    │
│ • Attach metadata                                               │
│ • Validate story structure                                      │
│                                                                  │
│ Output: GameStory                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: AI Enrichment (Optional, Future Phase)                  │
│ • Generate chapter headlines                                    │
│ • Generate chapter summaries                                    │
│ • Generate compact story                                        │
│                                                                  │
│ CRITICAL: AI operates on chapters, does not define them         │
│                                                                  │
│ Output: Enriched GameStory                                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ OUTPUT: API Response                                            │
│ • Apps consume chapters directly                                │
│ • UI expands/collapses chapters                                 │
│ • Narrative text enhances but doesn't define structure          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Principles

### 1. Structure Before Narrative

Chapters are created deterministically from play structure. Narrative text is generated after chapters exist.

**Old way (event-first):**
```
Event → Label → Fragment → Merge → Hope for coherence
```

**New way (structure-first):**
```
Plays → Boundaries → Chapters → Narrative
```

### 2. Chapters Are Logistics, Not Narrative

Chapters answer "where are the scene breaks?" not "what happened?"

- Chapter boundaries are structural inflection points
- Narrative meaning is derived from plays within chapters
- AI describes chapters, it doesn't define them

### 3. Determinism

Same PBP input → same chapters output. Always.

- No randomness
- No AI in chapter creation
- No heuristics that change over time
- Reproducible across runs

### 4. Complete Coverage

Every play belongs to exactly one chapter. No gaps, no overlaps.

- Chapters are contiguous
- Chronologically ordered
- Validated at creation time

### 5. AI Is a Renderer, Not a Decision Engine

AI generates narrative text from chapters. It does not:
- Define chapter boundaries
- Determine structure
- Compensate for fragmentation
- Invent distinctions

---

## JSON Schemas

### Chapter Schema

```json
{
  "chapter_id": "ch_001",
  "play_start_idx": 0,
  "play_end_idx": 4,
  "play_count": 5,
  "plays": [
    {
      "index": 0,
      "event_type": "pbp",
      "raw_data": { ... }
    },
    ...
  ],
  "reason_codes": ["quarter_change"]
}
```

**Required fields:**
- `chapter_id`: string
- `play_start_idx`: integer
- `play_end_idx`: integer
- `play_count`: integer
- `plays`: array of Play objects
- `reason_codes`: array of strings

**No AI fields. No ladder metadata. No moment types.**

---

### GameStory Schema

```json
{
  "game_id": 12345,
  "chapter_count": 4,
  "total_plays": 20,
  "chapters": [ ... ],
  "compact_story": null,
  "metadata": {
    "home_team": "Lakers",
    "away_team": "Celtics",
    "sport": "NBA"
  }
}
```

**Required fields:**
- `game_id`: integer
- `chapter_count`: integer
- `total_plays`: integer
- `chapters`: array of Chapter objects
- `compact_story`: string or null
- `metadata`: object

---

## Usage

### Building Chapters

```python
from app.services.chapters import build_chapters

# Input: timeline from data feed
timeline = [
    {"event_type": "pbp", "quarter": 1, ...},
    {"event_type": "pbp", "quarter": 1, ...},
    ...
]

# Build chapters
story = build_chapters(
    timeline=timeline,
    game_id=12345,
    metadata={"home_team": "Lakers", "away_team": "Celtics"}
)

# Access chapters
for chapter in story.chapters:
    print(f"{chapter.chapter_id}: {chapter.play_count} plays")

# Serialize for API
story_dict = story.to_dict()
```

### Command-Line Interface

```bash
# Run chapter builder on sample input
python -m app.services.chapters.cli sample_input.json

# Output: JSON with chapters
{
  "game_id": 12345,
  "chapters": [...],
  ...
}
```

---

## Testing

The Book + Chapters model has comprehensive unit tests that enforce:

### 1. Chapter Coverage
- Every play belongs to exactly one chapter
- No gaps between chapters
- No overlaps

### 2. Determinism
- Same input → same output
- Reproducible boundaries
- Chronological order preserved

### 3. Structural Integrity
- Plays within chapters are contiguous
- Chapter boundaries align to play indices
- No empty chapters
- Validation catches invalid structures

### 4. Moment Regression Guard
- No Moment objects produced
- No moment-related imports
- No moment-specific fields in schemas

### Running Tests

```bash
# Run all chapter tests
pytest api/tests/test_chapters.py -v

# Run specific test categories
pytest api/tests/test_chapters.py::test_chapter_coverage_all_plays_assigned
pytest api/tests/test_chapters.py::test_determinism_same_input_same_output
pytest api/tests/test_chapters.py::test_moment_regression_no_moment_objects
```

---

## Phase 0 Implementation

The current implementation is intentionally minimal:

**What's Implemented:**
- Core data types (Play, Chapter, GameStory)
- Deterministic chapter creation
- Boundary detection at quarter/period changes
- Complete structural validation
- Comprehensive unit tests
- Command-line interface

**What's NOT Implemented (Future Phases):**
- Advanced boundary detection (narrative state tracking)
- AI narrative generation
- Chapter importance scoring
- Sport-specific tuning

**This is by design.** Phase 0 establishes the structural backbone. Intelligence is added in later phases.

---

## Migration from Moments

### What Changed

| Old (Moments) | New (Chapters) |
|---------------|----------------|
| `Moment` object | `Chapter` object |
| `MomentType` enum | No types (structure only) |
| Ladder-driven segmentation | Structural boundaries |
| Multi-pass merging | No merging needed |
| Coherence enforcement | Inherent coherence |
| AI compensation | AI description |

### Breaking Changes

**The Moment concept is retired.** Code that depends on:
- `Moment` objects
- `MomentType` enum
- Ladder-based segmentation
- Moment merging logic

...must be updated to use chapters.

### Backward Compatibility

Phase 0 does not maintain backward compatibility with the moments API. This is a hard reset.

Future phases may add a compatibility layer if needed, but the core architecture is chapters-first.

---

## Future Phases

### Phase 1: Advanced Boundary Detection
- Narrative state tracking
- Intent change detection
- Momentum shift detection
- Sport-specific boundaries

### Phase 2: AI Narrative Generation
- Chapter headlines
- Chapter summaries
- Compact story generation
- Contextual descriptions

### Phase 3: Importance & Selection
- Chapter importance scoring
- Budget enforcement (if needed)
- Display priority

### Phase 4: UI Integration
- Chapter expansion/collapse
- Progressive disclosure
- Narrative flow

---

## Success Criteria

Phase 0 is complete when:

✅ **"Moment" is no longer a first-class concept**  
→ Chapters are the only structural primitive

✅ **Tests enforce coverage, determinism, and contiguity**  
→ All tests pass, structural guarantees validated

✅ **System runs end-to-end without AI**  
→ CLI produces valid chapters from sample input

✅ **No moment artifacts in output**  
→ Regression tests prevent moment reintroduction

---

## References

- **Code:** `api/app/services/chapters/`
- **Tests:** `api/tests/test_chapters.py`
- **CLI:** `api/app/services/chapters/cli.py`
- **Sample Input:** `api/app/services/chapters/sample_input.json`

---

**Document Status:** Phase 0 Complete  
**Next Phase:** Advanced boundary detection (narrative state tracking)
