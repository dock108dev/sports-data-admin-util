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

**Purpose:** List games with story generation status

**Displays:**
- Grid of games with PBP data
- Game matchup and score
- Play count
- Link to individual game story

**Actions:**
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
- Regenerate chapters
- Regenerate chapter summaries
- Regenerate compact story
- Regenerate all (chapters → summaries → compact)

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

## API Endpoints (Expected)

### GET /api/sports-admin/games/{gameId}/story

Returns `GameStoryResponse` with chapters, summaries, and compact story.

### GET /api/sports-admin/games/{gameId}/story-state?chapter={N}

Returns `StoryStateResponse` for the state before Chapter N.

### POST /api/sports-admin/games/{gameId}/story/regenerate-chapters

Regenerates chapters (resets summaries and compact story).

### POST /api/sports-admin/games/{gameId}/story/regenerate-summaries

Regenerates chapter summaries (preserves chapters, resets compact story).

### POST /api/sports-admin/games/{gameId}/story/regenerate-compact

Regenerates compact story only (preserves chapters and summaries).

### POST /api/sports-admin/games/{gameId}/story/regenerate-all

Regenerates everything (chapters → summaries → compact story).

---

## Removed/Archived

The following legacy Moments-based UI elements are deprecated:

### Removed:
- ❌ Moments timeline view
- ❌ Ladder / tier graphs
- ❌ Moment merge / coherence panels
- ❌ Moment-level AI diagnostics

### Archived (Legacy):
- Moments pages moved to `/admin/theory-bets/moments` (marked "Legacy")
- Still accessible for comparison during transition
- Will be removed in future cleanup

---

## Testing

### Unit Tests

**Location:** `web/src/app/admin/theory-bets/games/[gameId]/__tests__/ChaptersSection.test.tsx`

**Tests:**
1. Chapters Render Test
   - Correct chapter count
   - Chapters in order
   - Summaries displayed

2. Expand Chapter Test
   - Expanding shows all plays
   - Plays in correct order
   - Play indices correct

3. Metadata Display Test
   - Reason codes displayed
   - Play range displayed
   - Time range displayed

4. Debug View Test
   - Debug toggle works
   - Debug info shown when enabled

**Run tests:**
```bash
cd web
npm test ChaptersSection.test.tsx
```

---

## Migration Notes

### For Developers

1. **New Primary Unit:** Chapters (not moments)
2. **No Ladder Logic:** Reason codes replace tier crossings
3. **Sequential AI:** Each chapter uses prior context only
4. **Compact Story:** Synthesized from summaries, not raw plays

### For Admins

1. **Story Generator** is the new default
2. **Moments (Legacy)** still available for comparison
3. **Regeneration** is safe and explicit
4. **Debug views** show exact AI inputs

---

## Future Enhancements

- Real-time story generation status
- Diff view for regeneration
- AI prompt viewer per chapter
- Spoiler detection warnings in UI
- Batch regeneration for multiple games
- Export story as JSON/Markdown

---

## Success Criteria

✅ Admin UI no longer depends on moments engine  
✅ Chapters + stories are inspectable end-to-end  
✅ AI inputs and outputs are transparent  
✅ Engineers can debug story quality without reading logs  
✅ Regeneration is safe and explicit  
✅ No moments terminology in new UI  
