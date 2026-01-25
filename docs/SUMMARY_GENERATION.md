# Story Rendering: Single AI Call Architecture

> **Status:** Authoritative
> **Last Updated:** 2026-01-24
> **Scope:** NBA v1

---

## Overview

The story generation system converts play-by-play data into narrative stories for Scroll Down Sports.

**Architecture:** Sections-First, Single AI Call

A game's plays become chapters, chapters become sections, sections render into one cohesive story.

---

## Pipeline

```
Play-by-Play Data
    ↓
Chapterizer (Deterministic)
    ↓
Chapters (Structure)
    ↓
Section Builder (Deterministic)
    ↓
StorySections (with beat types, stats, notes)
    ↓
Header Generator (Deterministic)
    ↓
Story Renderer (Single AI Call)
    ↓
Compact Story (Complete)
```

---

## Core Concepts

### StorySections

Sections are the AI-ready representation of chapters. Each section contains:

- **beat_type:** Classification of what happened (RUN, RESPONSE, STALL, etc.)
- **stats:** Team and player stat deltas for the section
- **notes:** Machine-generated observations
- **scores:** Start and end scores
- **time context:** Period and time remaining

### Headers

Deterministic one-sentence orientation anchors that tell the reader WHERE we are:

- "The floor was alive from the opening tip." (FAST_START)
- "One side started pulling away." (RUN)
- "Scoring dried up on both ends." (STALL)

Headers are NOT narrative. They're structural guides.

### Beat Types

| Beat Type | Description |
|-----------|-------------|
| `FAST_START` | High-scoring opening |
| `MISSED_SHOT_FEST` | Low-efficiency stretch |
| `BACK_AND_FORTH` | Neither team separating |
| `EARLY_CONTROL` | One team establishing lead |
| `RUN` | 8+ unanswered points |
| `RESPONSE` | Comeback after a run |
| `STALL` | Scoring drought |
| `CRUNCH_SETUP` | Late tight game |
| `CLOSING_SEQUENCE` | Final minutes |
| `OVERTIME` | Extra period |

---

## Story Rendering

### Single AI Call Architecture

The system makes **one AI call** to render the complete story from the structured outline.

**Why Single Call:**
- Coherent narrative voice throughout
- Consistent story shape and flow
- Better control over length and pacing
- Faster generation (5-15 seconds vs 60-90 seconds for sequential)

### AI's Role (Strictly Limited)

**AI DOES:**
- Turn outline into prose
- Use headers verbatim
- Match target word count
- Add language polish

**AI DOES NOT:**
- Plan or restructure
- Infer importance
- Invent context
- Decide what matters
- Add drama not in input

### Prompt Rules

The AI prompt includes comprehensive rules for:

#### Opening Paragraph
- Establish TEXTURE, not summary
- Create curiosity rather than completeness
- Focus on game feel (rhythm, pressure, pace)
- No stats, totals, or point counts

#### Story Shape
Must reflect how pressure actually behaved:
- Build → Swing → Resolve (tight game, decided late)
- Early Break → Control → Fade (blowout)
- Trade → Trade → Decisive Push (back-and-forth)
- Surge → Stall → Late Separation (uneven momentum)

#### Narrative Flow
- Paragraphs BUILD on each other
- Carry tension forward
- Show cause and effect
- Middle paragraphs must do meaningful work

#### Layer Responsibility
Two layers exist:
- **Compact Story:** Overview layer — "What happened and how did it feel?"
- **Expanded Sections:** Detail layer — "How did that actually play out?"

The story invites curiosity. Expanded sections provide evidence.

#### Stat Usage
- 0-2 specific stats per section (max)
- Stats must be attached to moments
- No moment → no stat

#### Closing Paragraph
- Resolution matching the story's shape
- State final score clearly
- Connect back to earlier tension
- Land the story with closure

---

## Voice and Tone

### Confident Sports Writer

**Style:**
- Observational, confident, grounded
- Like someone who watched the game and understands what mattered
- Assured, post-game perspective

**Good Examples:**
- "The floor was tilting"
- "Neither side could create separation"
- "The trailing team clawed back"
- "The lead that emerged late held comfortably"

**Bad Examples:**
- "The Warriors scored 28 points in Q1" (stat dump)
- "At 8:42, Curry made a three-pointer" (play-by-play)
- "The game was exciting" (generic filler)
- "They struggled somewhat" (hedging)

---

## Prohibited Language

### Segment/Internal Language
Never expose internal structure:
- "stretch of scoring"
- "segment", "section", "phase"
- "in this section"
- "during the stretch"

### Hedging Language
No false balance or uncertainty:
- "somewhat", "to some degree"
- "arguably", "perhaps"
- Symmetric "both teams" framing when one side had the edge

### Quality Judgments
Don't infer beyond facts:
- "efficient", "inefficient"
- "struggled", "dominant"
- "impressive", "disappointing"
- "clutch", "choked"

---

## Validation

All AI-generated text is validated post-generation:

### Length Validation
- Target word count (section_count × 90 words)
- Per-section bounds: 60-120 words
- Deviation tolerance: ±50%

### Header Validation
- All headers present
- Headers in correct order
- Key words from headers appear in story

### Quality Checks
- Non-empty story
- Paragraph-based structure
- No prohibited phrases

**Failure Behavior:**
- Log exact errors
- Surface in Admin UI
- Retry once, then fail loudly

---

## Admin UI

### Story Generator Landing Page

**Route:** `/admin/sports/story-generator`

**Features:**
- List games with PBP data
- Bulk generation tool (date range + leagues)
- Link to individual game stories

### Game Story Detail Page

**Route:** `/admin/sports/story-generator/{gameId}`

**Features:**
- View complete game story
- Inspect sections (expand/collapse)
- View stats and notes per section
- Regeneration button
- Pipeline debug view

---

## Performance

### Deterministic Operations (Instant)
- Chapter generation: <1 second
- Section building: <1 second
- Header generation: <1 second
- Bulk chapter generation: ~22 games/second

### AI Operations (Single Call)
- Story rendering: ~5-15 seconds

**Example:** Full game story = ~5-20 seconds total

---

## Configuration

### Enable AI Generation

Add to `infra/.env`:
```bash
OPENAI_API_KEY=sk-proj-...your-key...
```

Restart API:
```bash
cd infra && docker compose restart api
```

### Without OpenAI Key

- ✅ Chapters and sections generate normally
- ✅ Headers generate normally
- ❌ Story rendering returns "API key not configured"

---

## Testing

### Test Structure Generation
```bash
curl -s http://localhost:8000/api/admin/sports/games/110536/story | jq '.section_count'
```

### Test Story Rendering
```bash
curl -X POST http://localhost:8000/api/admin/sports/games/110536/story/regenerate-all \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

### Test Bulk Generation
```bash
curl -X POST http://localhost:8000/api/admin/sports/games/bulk-generate \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2026-01-20",
    "end_date": "2026-01-20",
    "leagues": ["NBA"]
  }'
```

---

## Key Files

| File | Purpose |
|------|---------|
| `story_section.py` | Section building from chapters |
| `beat_classifier.py` | Beat type classification |
| `header_reset.py` | Deterministic header generation |
| `story_renderer.py` | Single AI call story rendering |
| `section_types.py` | Data structures |

---

## Related Documentation

**Core Concepts:**
- [Book + Chapters Model](BOOK_CHAPTERS_MODEL.md) — Architecture and definitions
- [NBA v1 Boundary Rules](NBA_V1_BOUNDARY_RULES.md) — Chapter boundary rules
- [Technical Flow](TECHNICAL_FLOW.md) — Complete pipeline details

**Implementation:**
- [Admin UI Guide](ADMIN_UI_STORY_GENERATOR.md) — Story Generator interface

---

## Summary

**Architecture:** Sections-first, single AI call
**AI Usage:** Rendering only (never structure)
**Performance:** ~5-15 seconds per game
**Status:** Production-ready for NBA v1
