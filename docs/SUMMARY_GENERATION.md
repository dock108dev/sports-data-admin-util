# Story Generation: Chapters-First System

> **Status:** Authoritative  
> **Last Updated:** 2026-01-22  
> **Scope:** NBA v1

---

## Overview

The story generation system converts play-by-play data into narrative stories for Scroll Down Sports.

**Architecture:** Chapters-First

A game is a book. Plays are pages. Chapters are scenes.

---

## Pipeline

```
Play-by-Play Data
    ↓
ChapterizerV1 (Deterministic)
    ↓
Chapters (Structure)
    ↓
StoryState Builder (Deterministic)
    ↓
AI Summary Generator (Sequential)
    ↓
AI Title Generator (Independent)
    ↓
AI Compact Story Generator (Full Arc)
    ↓
GameStory (Complete)
```

---

## Generation Modes

### Mode 1: Chapter Summaries (Sequential, Prior Context Only)

**Purpose:** Narrate each chapter in sequence

**Input:**
- Current chapter plays
- Prior chapter summaries (0..N-1)
- Story state from prior chapters

**Output:**
- Chapter summary (1-3 sentences)

**Rules:**
- ✅ May reference prior chapters
- ✅ May use "so far" stats
- ❌ No future knowledge
- ❌ No final totals

**Example:**
```
"After his hot start in Q1, LeBron cooled off in Q2 as the Celtics 
tightened their defense. He has 18 points through two quarters."
```

---

### Mode 2: Chapter Titles (Independent, Summary-Only)

**Purpose:** Generate scannable headlines

**Input:**
- Chapter summary only
- Optional metadata (period, time_range)

**Output:**
- Chapter title (3-8 words)

**Rules:**
- ✅ Derives from summary only
- ✅ No new information
- ❌ No numbers
- ❌ No timestamps

**Example:**
```
"Warriors Build Early Lead"
"Lakers Fight Back"
"Crunch Time Intensity"
```

---

### Mode 3: Compact Story (Full Arc, Hindsight Allowed)

**Purpose:** Generate complete game recap

**Input:**
- All chapter summaries (ordered)
- Optional chapter titles

**Output:**
- Compact story (4-12 min read)

**Rules:**
- ✅ Hindsight language allowed
- ✅ Final totals allowed
- ✅ Game result allowed
- ❌ No new facts (not in summaries)

**Example:**
```
"The Warriors defeated the Lakers 112-108 in a thrilling finish. 
After building an early lead, Golden State weathered a Lakers 
comeback before Curry hit a dagger 3-pointer with 3 minutes left. 
His 28 points led the Warriors to victory."
```

---

## Voice and Tone

### Sportscaster Voice

**Style:**
- Observational, energetic, grounded
- Like watching highlights for the first time
- No box-score listing
- No play-by-play regurgitation

**Good Examples:**
- "The Warriors came out firing"
- "LeBron kept them in it"
- "The game tightened late"

**Bad Examples:**
- "The Warriors scored 28 points in Q1" (stat dump)
- "At 8:42, Curry made a three-pointer" (too specific)
- "The game was exciting" (generic filler)

---

## Banned Phrases

### Spoiler Words (Unless Final Chapter)

**Forbidden in sequential generation:**
- "finished with"
- "sealed it"
- "the dagger"
- "would not recover"
- "ended the game"
- "closed it out"
- "put it away"
- "clinched"

**Allowed in:**
- Final chapter summary
- Compact story (full arc)

### Future Knowledge Phrases

**Always forbidden:**
- "later"
- "eventually"
- "from there"
- "that would prove"
- "on the way to"
- "would go on to"

---

## Validation

All AI-generated text is validated post-generation:

### Chapter Summary Validation
- ✅ 1-3 sentences
- ✅ No spoilers (unless final chapter)
- ✅ No future knowledge
- ✅ No bullet points

### Chapter Title Validation
- ✅ 3-8 words
- ✅ No numbers
- ✅ No punctuation (except apostrophes)
- ✅ No spoiler words

### Compact Story Validation
- ✅ Non-empty
- ✅ Paragraph-based
- ✅ No play-by-play listing
- ✅ No new entities

**Failure Behavior:**
- Log exact errors
- Surface in Admin UI
- Do not persist bad output
- Retry once, then fail loudly

---

## Admin UI

### Story Generator Landing Page

**Route:** `/admin/theory-bets/story-generator`

**Features:**
- List games with PBP data
- Bulk generation tool (date range + leagues)
- Link to individual game stories

### Game Story Detail Page

**Route:** `/admin/theory-bets/story-generator/{gameId}`

**Features:**
- View complete game story
- Inspect chapters (expand/collapse)
- View story state per chapter
- Regeneration buttons:
  - Regenerate Chapters
  - Regenerate Summaries
  - Regenerate Titles
  - Regenerate Compact Story
  - Regenerate All

**Chapter Inspector:**
- Collapsed: Title, summary, play count, reason codes
- Expanded: All raw plays, boundary explanation, debug info

---

## Performance

### Deterministic Operations (Instant)
- Chapter generation: <1 second
- Story state derivation: <1 second
- Bulk chapter generation: ~22 games/second

### AI Operations (Sequential)
- Chapter summaries: ~2-3 seconds per chapter
- Chapter titles: ~1-2 seconds per chapter
- Compact story: ~5-10 seconds

**Example:** 18-chapter game
- Chapters: <1 second
- Summaries: ~36-54 seconds
- Titles: ~18-36 seconds
- Compact story: ~5-10 seconds
- **Total:** ~60-100 seconds

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

- ✅ Chapters generate normally
- ✅ Story state derives normally
- ❌ AI endpoints return "API key not configured"

---

## Testing

### Test Chapter Generation
```bash
curl -s http://localhost:8000/api/admin/sports/games/110536/story | jq '.chapter_count'
# Returns: 18
```

### Test Story State
```bash
curl -s 'http://localhost:8000/api/admin/sports/games/110536/story-state?chapter=5' | jq '.players | keys'
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

### Test AI Generation (requires API key)
```bash
curl -X POST http://localhost:8000/api/admin/sports/games/110536/story/regenerate-all \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

---

## Related Documentation

**Core Concepts:**
- [Book + Chapters Model](BOOK_CHAPTERS_MODEL.md) — Architecture and definitions
- [NBA v1 Boundary Rules](NBA_V1_BOUNDARY_RULES.md) — Chapter boundary rules
- [AI Context Policy](AI_CONTEXT_POLICY.md) — What AI can/cannot see

**Implementation:**
- [AI Signals (NBA v1)](AI_SIGNALS_NBA_V1.md) — Exact signals exposed to AI
- [Admin UI Guide](ADMIN_UI_STORY_GENERATOR.md) — Story Generator interface
- [Technical Flow](TECHNICAL_FLOW.md) — Complete pipeline details

---

## Summary

**Architecture:** Chapters-First (structure before narrative)  
**AI Usage:** Narrative only (never structure)  
**Performance:** Chapters instant, AI ~60-90 seconds  
**Status:** Production-ready for NBA v1
