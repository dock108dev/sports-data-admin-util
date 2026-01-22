# Admin UI: Story Generator (Chapters-First)

**Issue 13: Rebuild Admin UI Story Generator Pages**

This document describes the new Story Generator admin experience built around the Book + Chapters model.

---

## Overview

The Story Generator admin UI replaces the legacy Moments-based interface with a Chapters-First inspection and debugging surface.

**Purpose:**
- Inspect how games are split into chapters
- Read chapter summaries and titles
- Expand chapters to see underlying plays
- View story state and AI inputs per chapter
- Regenerate chapters or stories safely

**Key Question:**
> "Why did the story come out this way?"

---

## Pages

### 1. Story Generator Landing Page

**Route:** `/admin/theory-bets/story-generator`

**Purpose:** List games and provide bulk generation tools

**Displays:**
- Bulk generation panel (date range + league selection)
- Grid of games with PBP data
- Game matchup and score
- Play count
- Link to individual game story

**Actions:**
- Bulk Generate Stories — Generate chapters for all games in date range
- Click game to open Story Generator detail page

---

### 2. Story Generator — Game Overview Page

**Route:** `/admin/theory-bets/story-generator/[gameId]`

**Purpose:** Single-game inspection and control

**Displays:**
- Game metadata (teams, date, sport)
- Chapter count
- Reading time estimate
- Compact Story output (full book)
- Story generation status:
  - ✓/✗ Chapters generated
  - ✓/✗ Summaries generated
  - ✓/✗ Compact story generated

**Actions:**
- Regenerate Chapters — Rebuild structural boundaries
- Regenerate Summaries — Generate AI chapter summaries (requires OpenAI)
- Regenerate Titles — Generate AI chapter titles from summaries (requires OpenAI)
- Regenerate Compact Story — Generate full game recap (requires OpenAI)
- Regenerate All — Full pipeline (chapters → summaries → titles → compact)

---

### 3. Chapter Inspector (Embedded)

**Location:** Within Game Overview Page

**Purpose:** Deep chapter-level inspection

**Collapsed View Shows:**
- Chapter index
- Chapter title
- Chapter summary
- Play count
- Reason codes (as icons)
- Time range

**Expanded View Shows:**
- All raw plays in order
- Boundary explanation:
  - Reason codes
  - Triggering play(s)
- Debug info (optional toggle):
  - Chapter fingerprint
  - Boundary logs
  - Play indices

**Interaction:**
- Click chapter header to expand/collapse
- Toggle "Show Debug Info" for technical details
- Plays displayed in scrollable list

---

### 4. Story State Inspector (Embedded)

**Location:** Within Game Overview Page (on demand)

**Purpose:** Verify AI context correctness

**Displays for Chapter N:**
- StoryState before Chapter N
- Player signals exposed to AI (top 6)
- Team signals (score, momentum)
- Theme signals
- Constraints validation

**Shows:**
- ✓ no_future_knowledge: true
- ✓ source: derived_from_prior_chapters_only

**Makes Obvious:**
- No future context included
- Signals are bounded and deterministic

---

## Components

### ChaptersSection.tsx

Replaces `MomentsSection.tsx`

**Props:**
```typescript
interface ChaptersSectionProps {
  chapters: ChapterEntry[];
  gameId: number;
}
```

**Features:**
- Expandable chapter cards
- Inline summaries
- Reason code icons
- Debug toggle
- Play-level inspection

---

## Data Types

### ChapterEntry

```typescript
type ChapterEntry = {
  chapter_id: string;
  play_start_idx: number;
  play_end_idx: number;
  play_count: number;
  reason_codes: string[];
  period: number | null;
  time_range: { start: string; end: string; } | null;
  chapter_summary: string | null;
  chapter_title: string | null;
  plays: PlayEntry[];
};
```

### GameStoryResponse

```typescript
type GameStoryResponse = {
  game_id: number;
  sport: string;
  chapters: ChapterEntry[];
  chapter_count: number;
  total_plays: number;
  compact_story: string | null;
  reading_time_estimate_minutes: number | null;
  generated_at: string | null;
  metadata: Record<string, unknown>;
};
```

### StoryStateResponse

```typescript
type StoryStateResponse = {
  chapter_index_last_processed: number;
  players: Record<string, PlayerStoryState>;
  teams: Record<string, TeamStoryState>;
  momentum_hint: "surging" | "steady" | "slipping" | "volatile" | "unknown";
  theme_tags: string[];
  constraints: {
    no_future_knowledge: boolean;
    source: string;
  };
};
```

---

## API Endpoints

### GET /api/admin/sports/games/{gameId}/story

Returns `GameStoryResponse` with chapters, summaries, and compact story.

### GET /api/admin/sports/games/{gameId}/story-state?chapter={N}

Returns `StoryStateResponse` for the state before Chapter N.

### POST /api/admin/sports/games/{gameId}/story/regenerate-chapters

Regenerates chapters (deterministic, instant).

### POST /api/admin/sports/games/{gameId}/story/regenerate-summaries

Regenerates chapter summaries (requires OpenAI API key, ~30-60s).

### POST /api/admin/sports/games/{gameId}/story/regenerate-titles

Regenerates chapter titles from summaries (requires OpenAI API key, ~10-20s).

### POST /api/admin/sports/games/{gameId}/story/regenerate-compact

Regenerates compact story from summaries (requires OpenAI API key, ~5-10s).

### POST /api/admin/sports/games/{gameId}/story/regenerate-all

Regenerates everything (chapters → summaries → titles → compact story, ~60-90s).

### POST /api/admin/sports/games/bulk-generate

Bulk generate chapters for games in a date range.

**Request:**
```json
{
  "start_date": "2026-01-20",
  "end_date": "2026-01-20",
  "leagues": ["NBA", "NHL"],
  "force": false
}
```

**Response:**
```json
{
  "success": true,
  "total_games": 22,
  "successful": 22,
  "failed": 0,
  "results": [...]
}
```

---

## Removed Concepts

The following legacy concepts have been removed:

- ❌ Moments engine
- ❌ Ladder / tier logic
- ❌ Moment merge / coherence passes
- ❌ Importance scoring

**Current System:** Chapters-First (deterministic structure + AI narrative)

---

## OpenAI Configuration

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

- ✅ Chapters generate normally (deterministic, instant)
- ✅ Story state derives normally
- ✅ UI shows chapter structure
- ❌ AI generation buttons return "API key not configured"

---

## Performance

### Deterministic Operations (Instant)
- Chapter generation: <1 second
- Bulk generation: ~22 games/second

### AI Operations (With OpenAI Key)
- Chapter summaries: ~2-3 seconds per chapter
- Chapter titles: ~1-2 seconds per chapter
- Compact story: ~5-10 seconds

**Example:** 18-chapter game = ~60-90 seconds total

---

## Success Criteria

✅ Admin UI no longer depends on moments engine  
✅ Chapters + stories are inspectable end-to-end  
✅ AI inputs and outputs are transparent  
✅ Engineers can debug story quality without reading logs  
✅ Regeneration is safe and explicit  
✅ No moments terminology in new UI  
