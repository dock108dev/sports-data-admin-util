# Book + Chapters Model

> **Status:** Authoritative
> **Last Updated:** 2026-01-24
> **Scope:** NBA

---

## Overview

The Book + Chapters model is the core architecture for narrative story generation.

**Core Principle:** A game is a book. Plays are pages. Chapters are contiguous play ranges. Sections are AI-ready representations.

**Design Philosophy:**
- **Structure before narrative** — Chapters and sections are deterministic
- **Separation of concerns** — Structure, classification, and rendering are distinct layers
- **Single AI call** — One rendering call produces the complete story

---

## Core Definitions

### Play

**The atomic unit of game action.**

A play is a single play-by-play event. Plays are the raw pages of the game's book.

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

**A contiguous range of plays representing a structural boundary.**

Chapters are created by the Chapterizer based on structural rules (timeouts, period breaks, etc.).

```python
@dataclass
class Chapter:
    chapter_id: str         # Unique ID (e.g., "ch_001")
    play_start_idx: int     # First play index (inclusive)
    play_end_idx: int       # Last play index (inclusive)
    plays: list[Play]       # Raw plays in chapter
    reason_codes: list[str] # Why this boundary exists
    period: int | None      # Quarter/period number
    time_range: TimeRange | None  # Game clock range
```

**Properties:**
- Contiguous (no gaps)
- Deterministic (same input → same output)
- Structural (not narrative)
- Explainable (reason codes)

**What Chapters Are:**
- Structural scene breaks
- Deterministic boundaries
- Input to section building

**What Chapters Are NOT:**
- Narrative labels
- Importance rankings
- AI-generated

---

### StorySection

**An AI-ready representation of one or more chapters.**

Sections contain beat types, stats, notes, and time context — everything the AI needs to render a paragraph.

```python
@dataclass
class StorySection:
    section_index: int
    beat_type: BeatType  # FAST_START, RUN, RESPONSE, etc.
    team_stat_deltas: dict[str, TeamStatDelta]
    player_stat_deltas: dict[str, PlayerStatDelta]
    notes: list[str]  # Machine-generated observations
    start_score: dict[str, int]
    end_score: dict[str, int]
    start_period: int | None
    end_period: int | None
    start_time_remaining: int | None
    end_time_remaining: int | None
```

**Properties:**
- Beat type classification
- Stat deltas (not cumulative)
- Time context for anchoring
- Machine-generated notes

**Enables:**
- Structured AI input
- Deterministic header assignment
- Consistent rendering

---

### Header

**A deterministic one-sentence orientation anchor.**

Headers tell the reader WHERE we are, not WHAT happened.

```python
# Example headers by beat type
HEADER_TEMPLATES = {
    BeatType.FAST_START: ["The floor was alive from the opening tip."],
    BeatType.RUN: ["One side started pulling away."],
    BeatType.RESPONSE: ["The trailing team clawed back into it."],
    BeatType.STALL: ["Scoring dried up on both ends."],
}
```

**Properties:**
- Template-based selection
- Deterministic (same beat type + index → same header)
- NOT narrative or AI-generated
- Structural guides for rendering

---

### GameStory

**The authoritative output consumed by apps.**

```python
@dataclass
class GameStory:
    game_id: int
    sport: str
    sections: list[StorySection]
    compact_story: str | None
    reading_time_estimate_minutes: float | None
    metadata: dict
```

**Properties:**
- Complete game narrative
- Forward-compatible schema
- Serializable as JSON

**Contains:**
- All sections (structural units)
- Headers (deterministic)
- Compact story (AI-rendered)

---

## Pipeline Architecture

### High-Level Flow

```
Play-by-Play
    ↓
Chapterizer (Deterministic)
    ↓
Chapters (Structural boundaries)
    ↓
Section Builder (Deterministic)
    ↓
StorySections (with beat types, stats, notes)
    ↓
Header Generator (Deterministic)
    ↓
Story Renderer (Single AI Call)
    ↓
Compact Story
```

### Stage 1: Chapterization

**Component:** `chapterizer.py`
**Input:** Normalized play-by-play events
**Output:** Chapters with reason codes
**Deterministic:** Yes
**AI:** No

**Logic:**
- Detect structural boundaries (NBA rules)
- Create contiguous chapters
- Assign reason codes
- Validate coverage

**Boundaries:**
- **Hard:** Period start/end, overtime, game end
- **Scene Reset:** Timeouts, reviews, challenges
- **Momentum:** Crunch time start

See [NBA_BOUNDARY_RULES.md](NBA_BOUNDARY_RULES.md)

### Stage 2: Section Building

**Component:** `story_section.py`
**Input:** Ordered chapters
**Output:** StorySections with beat types, stats, notes
**Deterministic:** Yes
**AI:** No

**Logic:**
- Classify beat type from chapter characteristics
- Extract team and player stat deltas
- Generate machine observations (notes)
- Add time context from plays

### Stage 3: Header Generation

**Component:** `header_reset.py`
**Input:** StorySections
**Output:** Deterministic headers
**Deterministic:** Yes
**AI:** No

**Logic:**
- Select template based on beat type
- Vary selection based on section index
- Same input → same header every time

### Stage 4: Story Rendering

**Component:** `story_renderer.py`
**Input:** Sections + Headers + Team info
**Output:** Compact story (prose)
**Deterministic:** No (AI)
**AI:** Yes (OpenAI)

**Single Call Architecture:**
- One AI call renders entire story
- AI uses headers verbatim
- AI follows comprehensive prompt rules
- AI adds language polish, not logic

See [SUMMARY_GENERATION.md](SUMMARY_GENERATION.md)

---

## Data Flow

### Input: Play-by-Play
```json
[
  {
    "play_index": 0,
    "quarter": 1,
    "game_clock": "12:00",
    "description": "Jump ball",
    "team": "LAL",
    "score_home": 0,
    "score_away": 0
  },
  ...
]
```

### Output: GameStory
```json
{
  "game_id": 1,
  "sport": "NBA",
  "story_version": "2.0.0",
  "sections": [
    {
      "section_index": 0,
      "beat_type": "FAST_START",
      "header": "The floor was alive from the opening tip.",
      "team_stat_deltas": [...],
      "player_stat_deltas": [...],
      "notes": ["Lakers outscored Celtics 14-8"],
      "start_score": {"home": 0, "away": 0},
      "end_score": {"home": 14, "away": 8}
    },
    ...
  ],
  "section_count": 12,
  "total_plays": 155,
  "compact_story": "The Lakers came out firing...",
  "reading_time_estimate_minutes": 3.5,
  "has_compact_story": true
}
```

---

## Invariants

### Chapter Coverage Guarantees
1. **Contiguity:** `chapter[i].play_end_idx + 1 == chapter[i+1].play_start_idx`
2. **No gaps:** First chapter starts at 0, last ends at `len(plays)-1`
3. **No overlaps:** Every play belongs to exactly one chapter
4. **Determinism:** Same input → same chapters (fingerprinted)

### Section Properties
1. **Beat classification:** Every section has a beat type
2. **Stats present:** Team and player deltas always computed
3. **Time context:** Period and clock included when available
4. **Deterministic:** Same chapters → same sections

### Rendering Constraints
1. **Headers verbatim:** AI must use headers as-is
2. **Word count targets:** 60-120 words per section
3. **No inference:** AI uses only provided signals
4. **Single call:** One API call per story

---

## Testing Strategy

### Unit Tests
- Chapter coverage and contiguity
- Boundary rule enforcement
- Section building and beat classification
- Header generation determinism
- Prompt building

### Integration Tests
- End-to-end chapterization
- Section building from chapters
- API endpoint contracts
- Frontend data wiring

**Run tests:**
```bash
cd api
pytest tests/test_chapterizer.py tests/test_story_section.py tests/test_story_renderer.py
```

---

## Admin UI

**Story Generator Interface:**
- Game overview with generation status
- Section inspector (expandable)
- Stats and notes per section
- Regeneration controls
- Pipeline debug view

**Features:**
- Inspect section boundaries
- View beat types and headers
- Expand sections to see stats
- Regenerate story

See [ADMIN_UI_STORY_GENERATOR.md](ADMIN_UI_STORY_GENERATOR.md)

---

## Key Design Decisions

### Why Chapters Are Structural

Chapters are defined by **structural boundaries**, not narrative labels.

**Structural boundaries:**
- Period start/end
- Timeouts
- Reviews
- Crunch time start

**Not boundaries:**
- Individual scores
- Lead changes
- Narrative importance

**Benefit:** Deterministic, reproducible, simple.

### Why Sections Transform Chapters

Sections add the AI-ready layer:
- Beat type classification
- Stat deltas
- Machine-generated notes
- Time context

**Benefit:** Clean separation between structure and rendering input.

### Why Single AI Call

**Problem:** Sequential chapter-by-chapter generation is slow (~60-90 seconds) and produces inconsistent voice.

**Solution:** Single AI call renders entire story at once.

**Benefits:**
- Coherent narrative voice
- Consistent story shape
- Faster generation (~5-15 seconds)
- Better flow between sections

---

## References

- [NBA Boundary Rules](NBA_BOUNDARY_RULES.md)
- [AI Signals (NBA)](AI_SIGNALS_NBA.md)
- [Story Rendering](SUMMARY_GENERATION.md)
- [Technical Flow](TECHNICAL_FLOW.md)
- [Admin UI Guide](ADMIN_UI_STORY_GENERATOR.md)
