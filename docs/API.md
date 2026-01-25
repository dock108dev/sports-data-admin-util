# Sports Data Admin API

> FastAPI backend for Scroll Down Sports: API, data scraper, admin UI.

**Base URL:** `/api`

---

## Table of Contents

1. [Health Check](#health-check)
2. [Story Generation (Chapters-First)](#story-generation-chapters-first) ← **NEW (v2.0)**
3. [Games — Admin](#games--admin)
4. [Games — Snapshots (App)](#games--snapshots-app)
5. [Timeline Generation](#timeline-generation)
6. [Teams](#teams)
7. [Scraper Runs](#scraper-runs)
8. [Job Runs](#job-runs)
9. [Diagnostics](#diagnostics)
10. [Social](#social)
11. [Reading Positions](#reading-positions)
12. [Migration Guide: Moments → Story](#migration-guide-moments--story)

---

## Health Check

### `GET /healthz`

```json
{ "status": "ok", "app": "ok", "db": "ok" }
```

---

## Story Generation (Chapters-First)

**Base path:** `/api/admin/sports`

The chapters-first story generation system replaces the legacy "moments" approach. It provides:
- **Chapters**: Deterministic structural units (contiguous play ranges)
- **Sections**: Narrative groupings with beat types (3-10 per game)
- **Compact Story**: Single AI-generated game recap

### Architecture Overview

```
PBP Data → Chapterizer → Chapters → StoryState → AI (single call) → GameStory
```

**Pipeline Stages:**
1. `build_chapters` — Deterministic chapter boundaries from play-by-play
2. `build_running_snapshots` — Cumulative team/player stats at chapter ends
3. `classify_all_chapters` — Assign beat type to each chapter
4. `build_story_sections` — Collapse chapters into 3-10 narrative sections
5. `generate_all_headers` — Deterministic one-sentence orientation anchors
6. `compute_quality_score` — Assess game quality (LOW/MEDIUM/HIGH)
7. `select_target_word_count` — Quality → word count (400/700/1050)
8. `validate_pre_render` — Check section ordering, stat consistency
9. `render_story` — **SINGLE AI CALL** turns outline into prose
10. `validate_post_render` — Check word count, no player inventions

### `GET /games/{game_id}/story`

Get game story using chapters-first pipeline.

| Parameter | Type | Description |
|-----------|------|-------------|
| `include_debug` | `bool` | Include debug info (fingerprints, boundary logs) |

**Response: `GameStoryResponse`**

```json
{
  "game_id": 12345,
  "sport": "NBA",
  "story_version": "2.0.0",

  "chapters": [
    {
      "chapter_id": "ch_001",
      "index": 0,
      "play_start_idx": 0,
      "play_end_idx": 15,
      "play_count": 16,
      "reason_codes": ["period_start", "timeout"],
      "period": 1,
      "time_range": { "start": "12:00", "end": "8:45" },
      "plays": [...]
    }
  ],
  "chapter_count": 8,
  "total_plays": 245,

  "sections": [
    {
      "section_index": 0,
      "beat_type": "FAST_START",
      "header": "Both teams opened at a fast pace.",
      "chapters_included": ["ch_001", "ch_002"],
      "start_score": { "home": 0, "away": 0 },
      "end_score": { "home": 24, "away": 22 },
      "notes": ["Lakers scored first 8 points", "12 lead changes"]
    }
  ],
  "section_count": 5,

  "compact_story": "The Lakers and Celtics traded blows in an instant classic...",
  "word_count": 712,
  "target_word_count": 700,
  "quality": "MEDIUM",
  "reading_time_estimate_minutes": 3.56,

  "generated_at": "2026-01-22T15:30:00Z",
  "has_compact_story": true,
  "metadata": {
    "quality_score": 6.5,
    "quality_signals": {...}
  }
}
```

### `POST /games/{game_id}/story/regenerate`

Regenerate story from scratch using chapters-first pipeline.

**Request:**

```json
{
  "force": true,
  "debug": false
}
```

**Response: `RegenerateResponse`**

```json
{
  "success": true,
  "message": "Generated story: 5 sections, 712 words",
  "story": { ... GameStoryResponse ... },
  "errors": []
}
```

### `POST /games/bulk-generate-async`

Start bulk story generation for games in a date range.

**Request:**

```json
{
  "start_date": "2026-01-15",
  "end_date": "2026-01-22",
  "leagues": ["NBA", "NHL"],
  "force": false
}
```

**Response:**

```json
{
  "job_id": "abc-123-def",
  "message": "Bulk generation started",
  "status_url": "/api/admin/sports/games/bulk-generate-status/abc-123-def"
}
```

### `GET /games/bulk-generate-status/{job_id}`

Poll status of bulk generation job.

**Response:**

```json
{
  "job_id": "abc-123-def",
  "state": "PROGRESS",
  "current": 5,
  "total": 20,
  "status": "Processing game 12345",
  "successful": 4,
  "failed": 0,
  "cached": 0,
  "result": null
}
```

**Job States:** `PENDING`, `PROGRESS`, `SUCCESS`, `FAILURE`

---

## Response Models

### GameStoryResponse

```typescript
interface GameStoryResponse {
  game_id: number;
  sport: string;
  story_version: string;           // "2.0.0"

  // Structural data
  chapters: ChapterEntry[];
  chapter_count: number;
  total_plays: number;

  // Narrative sections (3-10 per game)
  sections: SectionEntry[];
  section_count: number;

  // AI-generated compact story (SINGLE AI CALL)
  compact_story: string | null;
  word_count: number | null;
  target_word_count: number | null;
  quality: "LOW" | "MEDIUM" | "HIGH" | null;
  reading_time_estimate_minutes: number | null;

  // Metadata
  generated_at: string | null;     // ISO datetime
  has_compact_story: boolean;
  metadata: Record<string, any>;
}
```

### ChapterEntry

Chapters are **structural units** — deterministic, contiguous play ranges.

```typescript
interface ChapterEntry {
  chapter_id: string;              // "ch_001"
  index: number;                   // Explicit ordering for UI

  // Play range (inclusive)
  play_start_idx: number;
  play_end_idx: number;
  play_count: number;

  // Boundary explanation
  reason_codes: string[];          // Why this chapter exists

  // Metadata
  period: number | null;           // Quarter/period number
  time_range: TimeRange | null;

  // Expanded plays
  plays: PlayEntry[];

  // Debug only
  chapter_fingerprint?: string;
  boundary_logs?: object[];
}
```

**Reason Codes:**
- `period_start` — Start of quarter/period
- `period_end` — End of quarter/period
- `timeout` — Timeout called
- `review` — Official review
- `run_boundary` — Scoring run triggered new chapter
- `overtime_start` — Start of overtime
- `game_end` — End of game

### SectionEntry

Sections are **narrative units** — collapsed chapters with beat types.

```typescript
interface SectionEntry {
  section_index: number;           // 0-based ordering
  beat_type: BeatType;             // See Beat Types below
  header: string;                  // Deterministic one-sentence anchor
  chapters_included: string[];     // Chapter IDs in this section

  // Score bookends
  start_score: { home: number; away: number };
  end_score: { home: number; away: number };

  // Deterministic notes
  notes: string[];                 // Machine-generated bullets
}
```

### Beat Types (Locked)

| Beat Type | Description |
|-----------|-------------|
| `FAST_START` | Early energy, both teams scoring quickly |
| `BACK_AND_FORTH` | Tied or alternating leads |
| `EARLY_CONTROL` | One team gaining edge |
| `RUN` | Consecutive scoring (6+ unanswered) |
| `RESPONSE` | Catch-up attempt after run |
| `STALL` | Slowed action, scoring drought |
| `CRUNCH_SETUP` | Late-game tightening (final 5 min, within 5 pts) |
| `CLOSING_SEQUENCE` | Final minutes determining outcome |
| `OVERTIME` | Overtime period play |

### PlayEntry

```typescript
interface PlayEntry {
  play_index: number;
  quarter: number | null;
  game_clock: string | null;       // "8:45"
  play_type: string | null;        // "shot", "turnover", etc.
  description: string;
  team: string | null;             // Team abbreviation
  score_home: number | null;
  score_away: number | null;
}
```

### Quality & Word Count

| Quality | Target Words | Word Range |
|---------|--------------|------------|
| `LOW` | 400 | 300-500 |
| `MEDIUM` | 700 | 600-800 |
| `HIGH` | 1050 | 900-1200 |

Quality is determined by:
- Lead changes frequency
- Crunch time presence
- Overtime presence
- Final margin closeness
- Run/response patterns

---

## Games — Admin

Base path: `/api/admin/sports`

### `GET /games`

List games with filtering and pagination.

| Parameter | Type | Description |
|-----------|------|-------------|
| `league` | `string[]` | Filter by league codes |
| `startDate` | `date` | Games on or after |
| `endDate` | `date` | Games on or before |
| `missingBoxscore` | `bool` | Games without boxscores |
| `limit` | `int` | Max results (1-200) |
| `offset` | `int` | Pagination offset |

### `GET /games/{game_id}`

Full game detail.

```json
{
  "game": GameMeta,
  "team_stats": [...],
  "player_stats": [...],
  "odds": [...],
  "social_posts": [...],
  "plays": [...],
  "derived_metrics": {...}
}
```

### `POST /games/{game_id}/rescrape`

Trigger rescrape for a game.

### `POST /games/{game_id}/resync-odds`

Resync odds for a game.

---

## Games — Snapshots (App)

Base path: `/api`

For mobile/web app consumption.

### `GET /api/games`

List games by time window.

| Parameter | Type | Description |
|-----------|------|-------------|
| `range` | `string` | `last2`, `current`, `next24` |
| `league` | `string` | Filter by league |

### `GET /api/games/{game_id}/pbp`

Play-by-play grouped by period.

### `GET /api/games/{game_id}/social`

Social posts with reveal levels (`pre`/`post`).

### `GET /api/games/{game_id}/timeline`

Full stored timeline artifact.

### `GET /api/games/{game_id}/timeline/compact`

Compressed timeline for efficient app display.

| Parameter | Type | Description |
|-----------|------|-------------|
| `level` | `int` | 1=notable moments, 2=standard, 3=detailed |

### `GET /api/games/{game_id}/recap`

Generate recap at reveal level.

---

## Timeline Generation

Base path: `/api/admin/sports`

### `POST /timelines/generate/{game_id}`

Generate timeline for a game.

### `GET /timelines/missing`

Games with PBP but no timeline.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `league_code` | `string` | Yes | NBA, NHL, NCAAB |
| `days_back` | `int` | No | Days to look back |

### `POST /timelines/generate-batch`

Generate timelines for multiple games.

### `GET /timelines/existing`

Games with timeline artifacts.

### `POST /timelines/regenerate-batch`

Regenerate existing timelines.

---

## Teams

Base path: `/api/admin/sports`

### `GET /teams`

List teams.

### `GET /teams/{team_id}`

Team detail with recent games.

### `GET /teams/{team_id}/social`

Team social media info.

---

## Scraper Runs

Base path: `/api/admin/sports`

### `POST /scraper/runs`

Create scrape job.

### `GET /scraper/runs`

List scrape runs.

### `GET /scraper/runs/{run_id}`

Get run details.

### `POST /scraper/runs/{run_id}/cancel`

Cancel pending job.

---

## Job Runs

Base path: `/api/admin/sports`

### `GET /jobs`

List job run history.

---

## Diagnostics

Base path: `/api/admin/sports/diagnostics`

### `GET /missing-pbp`

Games missing play-by-play.

### `GET /conflicts`

Unresolved game conflicts.

---

## Social

Base path: `/api/social`

### `GET /posts`

List social posts.

### `GET /posts/game/{game_id}`

Posts for a game.

### `POST /posts`

Create post.

### `POST /posts/bulk`

Bulk create posts.

### `DELETE /posts/{post_id}`

Delete post.

### `GET /accounts`

List social accounts.

### `POST /accounts`

Create/update account.

---

## Reading Positions

Base path: `/api`

### `POST /api/users/{user_id}/games/{game_id}/reading-position`

Save reading position.

### `GET /api/users/{user_id}/games/{game_id}/resume`

Get reading position.

---

## Consumers

- `scroll-down-app` (iOS)
- `scroll-down-sports-ui` (Web)

## Contract

Implements `scroll-down-api-spec`. Schema changes require spec update first.
