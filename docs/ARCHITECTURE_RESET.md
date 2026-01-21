# Architecture Reset: Moments → Chapters

**Date:** 2026-01-21  
**Status:** Phase 0 Complete  
**Breaking Change:** Yes

---

## Summary

The legacy "Moments" concept has been retired and replaced with the **Book + Chapters** model.

**Old:** Event-first design with ladder-driven segmentation, moment types, and multi-pass merging  
**New:** Structure-first design with deterministic chapters and narrative layering

---

## What Changed

### Conceptual Model

**Before:**
```
Events → Ladder Crossings → Moment Boundaries → Moments → Merge → Coherence → AI
```

**After:**
```
Plays → Structural Boundaries → Chapters → AI Narrative
```

### Core Types

| Old | New | Notes |
|-----|-----|-------|
| `Moment` | `Chapter` | Renamed and simplified |
| `MomentType` enum | _(removed)_ | No types; structure only |
| `MomentReason` | `reason_codes` | Simplified to debug strings |
| Ladder tiers | _(removed from structure)_ | May be used for narrative later |
| Merging logic | _(removed)_ | No longer needed |
| Coherence enforcement | _(removed)_ | Inherent in design |

---

## Why This Change

### Problem 1: Over-Segmentation
The old system created 2-3x too many moments by reacting to every tier crossing. This required:
- 481 lines of merge logic to undo fragmentation
- Coherence enforcement to suppress repetition
- AI compensation to make fragments sound distinct

### Problem 2: Conflated Concerns
Moments tried to be both:
- **Structural units** (coverage, continuity)
- **Narrative units** (story beats, types)

This made them unpredictable and hard to reason about.

### Problem 3: Non-Determinism
Moment boundaries were influenced by:
- Numeric thresholds (ladder tiers)
- Heuristics (runs, density gating)
- Multi-pass merging (repair logic)
- Coherence dampening (suppression)

Same input could produce different moments depending on tuning.

---

## The Solution: Book + Chapters

### Separation of Concerns

**Chapters = Structure**
- Where are the scene breaks?
- Deterministic boundaries
- Complete coverage (no gaps, no overlaps)

**Narrative = Story**
- What happened in each scene?
- Generated from chapter plays
- Layered after structure exists

**AI = Rendering**
- How do we describe it?
- Operates on coherent chapters
- No structural decisions

### Key Principles

1. **Structure before narrative** — Chapters created deterministically, narrative added later
2. **Determinism** — Same input → same output, always
3. **Complete coverage** — Every play in exactly one chapter
4. **No AI in structure** — AI describes chapters, doesn't define them

---

## Migration Guide

### For API Consumers

**Breaking changes:**
- `/api/games/{id}/moments` endpoint will be updated to return chapters
- Response schema changed (see below)
- Moment-specific fields removed

**What to update:**
```typescript
// Old
interface Moment {
  id: string;
  type: "LEAD_BUILD" | "CUT" | "FLIP" | "TIE" | ...;
  ladder_tier_before: number;
  ladder_tier_after: number;
  is_notable: boolean;
  importance_score: number;
  // ...
}

// New
interface Chapter {
  chapter_id: string;
  play_start_idx: number;
  play_end_idx: number;
  play_count: number;
  plays: Play[];
  reason_codes: string[];
}
```

### For Backend Code

**Modules removed:**
- `moments_boundaries.py` (replaced by `chapters/builder.py`)
- `moments_merging.py` (no longer needed)
- `moments/coherence.py` (no longer needed)
- `moments_validation.py` (validation built into Chapter)

**Modules replaced:**
- `moments/types.py` → `chapters/types.py`
- `moments/partition.py` → `chapters/builder.py`

**Import changes:**
```python
# Old
from app.services.moments import Moment, MomentType, partition_game

# New
from app.services.chapters import Chapter, GameStory, build_chapters
```

---

## Phase 0 Implementation

### What's Complete

✅ Core data types (`Play`, `Chapter`, `GameStory`)  
✅ Deterministic chapter creation  
✅ Structural validation  
✅ Comprehensive unit tests (23 tests, all passing)  
✅ Command-line interface  
✅ Documentation

### What's NOT Implemented (Future Phases)

❌ Advanced boundary detection (narrative state tracking)  
❌ AI narrative generation  
❌ Chapter importance scoring  
❌ Sport-specific tuning  
❌ API endpoint updates  
❌ UI integration

**This is intentional.** Phase 0 establishes the structural backbone. Intelligence is added in later phases.

---

## Testing

### Run Chapter Tests

```bash
cd api
pytest tests/test_chapters.py -v
```

All 23 tests pass, enforcing:
- Chapter coverage (every play in exactly one chapter)
- Determinism (same input → same output)
- Structural integrity (contiguous, valid boundaries)
- Moment regression guard (no moment objects)

### Run CLI

```bash
cd api
python -m app.services.chapters.cli app/services/chapters/sample_input.json
```

Produces valid chapter JSON without AI involvement.

---

## Documentation

- **[Book + Chapters Model](BOOK_CHAPTERS_MODEL.md)** — Complete architectural documentation
- **[Phase 0 Narrative Reframe](PHASE_0_NARRATIVE_REFRAME.md)** — Original conceptual analysis
- **Code:** `api/app/services/chapters/`
- **Tests:** `api/tests/test_chapters.py`

---

## Timeline

- **2026-01-21:** Phase 0 complete (structure + tests)
- **Future:** Phase 1 (advanced boundaries)
- **Future:** Phase 2 (AI narrative)
- **Future:** Phase 3 (importance & selection)
- **Future:** Phase 4 (UI integration)

---

## Success Criteria

Phase 0 is successful if:

✅ **"Moment" is no longer a first-class concept**  
→ Chapters are the only structural primitive

✅ **Tests enforce coverage, determinism, and contiguity**  
→ All tests pass, structural guarantees validated

✅ **System runs end-to-end without AI**  
→ CLI produces valid chapters from sample input

✅ **No moment artifacts in output**  
→ Regression tests prevent moment reintroduction

**All criteria met. Phase 0 complete.**

---

## Questions?

See [BOOK_CHAPTERS_MODEL.md](BOOK_CHAPTERS_MODEL.md) for complete documentation, or ask in #eng-sports-data.
