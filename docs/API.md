# Sports Data Admin API

> FastAPI backend for Scroll Down Sports: API, data scraper, admin UI.

**Base URL:** `/api`

---

## Table of Contents

1. [Health Check](#health-check)
2. [App Endpoints (Read-Only)](#app-endpoints-read-only)
3. [Admin Endpoints](#admin-endpoints)
   - [Story Generation](#story-generation)
   - [Games Management](#games-management)
   - [Timeline Generation](#timeline-generation)
   - [Teams](#teams)
   - [Scraper Runs](#scraper-runs)
   - [Diagnostics](#diagnostics)
4. [Social](#social)
5. [Reading Positions](#reading-positions)
6. [Response Models](#response-models)

---

## Health Check

### `GET /healthz`

```json
{ "status": "ok", "app": "ok", "db": "ok" }
```

---

## App Endpoints (Read-Only)

**Base path:** `/api`

These endpoints serve pre-computed data to mobile/web apps. **Apps should only use these endpoints.**

> **Design Principle:** App endpoints return stored/cached data only. No on-the-fly generation.

### `GET /api/games`

List games by time window.

| Parameter | Type | Description |
|-----------|------|-------------|
| `range` | `string` | `last2`, `current`, `next24` |
| `league` | `string` | Filter by league |

**Response:**
```json
{
  "range": "current",
  "games": [
    {
      "id": 123,
      "league": "NBA",
      "status": "final",
      "start_time": "2026-01-15T02:00:00Z",
      "home_team": {"id": 1, "name": "Warriors", "abbreviation": "GSW"},
      "away_team": {"id": 2, "name": "Lakers", "abbreviation": "LAL"},
      "has_pbp": true,
      "has_social": false,
      "last_updated_at": "2026-01-15T03:00:00Z"
    }
  ]
}
```

### `GET /api/games/{game_id}/pbp`

Play-by-play grouped by period.

**Response:**
```json
{
  "periods": [
    {
      "period": 1,
      "events": [
        {"index": 1, "clock": "12:00", "description": "Tipoff", "play_type": "tip"}
      ]
    }
  ]
}
```

### `GET /api/games/{game_id}/social`

Social posts with reveal levels (`pre`/`post`).

**Response:**
```json
{
  "posts": [
    {
      "id": 99,
      "team": {"id": 1, "name": "Warriors", "abbreviation": "GSW"},
      "content": "Game day.",
      "posted_at": "2026-01-15T02:00:00Z",
      "reveal_level": "pre"
    }
  ]
}
```

### `GET /api/games/{game_id}/timeline`

Full stored timeline artifact.

**Response:**
```json
{
  "game_id": 123,
  "sport": "NBA",
  "timeline_version": "v1",
  "generated_at": "2026-01-15T03:00:00Z",
  "timeline_json": [...],
  "game_analysis_json": {...},
  "summary_json": {...}
}
```

### `GET /api/games/{game_id}/timeline/compact`

Compressed timeline for efficient app display.

| Parameter | Type | Description |
|-----------|------|-------------|
| `level` | `int` | 1=highlights, 2=standard, 3=detailed |

---

## Admin Endpoints

**Base path:** `/api/admin/sports`

These endpoints are for admin UI and internal operations only. **Apps must not use these endpoints.**

---

### Story Generation

The chapters-first story generation system provides:
- **Chapters**: Deterministic structural units (contiguous play ranges)
- **Sections**: Narrative groupings with beat types (3-10 per game)
- **Compact Story**: Single AI-generated game recap

#### Architecture Overview

```
PBP Data → Chapterizer → Chapters → Sections → Headers → AI (single call) → Story
```

**Pipeline Stages:**
1. `build_chapters` — Deterministic chapter boundaries from play-by-play
2. `build_story_sections` — Collapse chapters into narrative sections
3. `generate_all_headers` — Deterministic one-sentence orientation anchors
4. `compute_quality_score` — Assess game quality (LOW/MEDIUM/HIGH)
5. `render_story` — **SINGLE AI CALL** turns outline into prose

#### `GET /games/{game_id}/story`

Get game story. Returns cached story if available, otherwise generates and caches.

| Parameter | Type | Description |
|-----------|------|-------------|
| `include_debug` | `bool` | Include debug info (fingerprints, boundary logs) |
| `force_regenerate` | `bool` | Bypass cache and regenerate |

**Response: `GameStoryResponse`**

```json
{
  "game_id": 12345,
  "sport": "NBA",
  "story_version": "2.0.0",
  "chapters": [...],
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
  "compact_story": "The Lakers and Celtics traded blows...",
  "word_count": 712,
  "target_word_count": 700,
  "quality": "MEDIUM",
  "reading_time_estimate_minutes": 3.56,
  "generated_at": "2026-01-22T15:30:00Z",
  "has_compact_story": true,
  "metadata": {...}
}
```

#### `GET /games/{game_id}/story/pipeline`

Get the story generation pipeline debug view. Shows full data transformation.

#### `POST /games/{game_id}/story/regenerate`

Regenerate story from scratch using chapters-first pipeline.

**Request:**
```json
{
  "force": true,
  "debug": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Generated story: 5 sections, 712 words",
  "story": { ... },
  "errors": []
}
```

#### `POST /games/bulk-generate-async`

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

#### `GET /games/bulk-generate-status/{job_id}`

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
  "skipped": 0,
  "result": null
}
```

**Job States:** `PENDING`, `PROGRESS`, `SUCCESS`, `FAILURE`

---

### Games Management

#### `GET /games`

List games with filtering and pagination.

| Parameter | Type | Description |
|-----------|------|-------------|
| `league` | `string[]` | Filter by league codes |
| `startDate` | `date` | Games on or after |
| `endDate` | `date` | Games on or before |
| `missingBoxscore` | `bool` | Games without boxscores |
| `limit` | `int` | Max results (1-200) |
| `offset` | `int` | Pagination offset |

#### `GET /games/{game_id}`

Full game detail including stats, odds, social, plays.

#### `POST /games/{game_id}/rescrape`

Trigger rescrape for a game.

#### `POST /games/{game_id}/resync-odds`

Resync odds for a game.

---

### Timeline Generation

#### `POST /timelines/generate/{game_id}`

Generate timeline for a game.

#### `GET /timelines/missing`

Games with PBP but no timeline.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `league_code` | `string` | Yes | NBA, NHL, NCAAB |
| `days_back` | `int` | No | Days to look back |

#### `POST /timelines/generate-batch`

Generate timelines for multiple games.

#### `GET /timelines/existing`

Games with timeline artifacts.

#### `POST /timelines/regenerate-batch`

Regenerate existing timelines.

---

### Teams

#### `GET /teams`

List teams.

#### `GET /teams/{team_id}`

Team detail with recent games.

#### `GET /teams/{team_id}/social`

Team social media info.

---

### Scraper Runs

#### `POST /scraper/runs`

Create scrape job.

#### `GET /scraper/runs`

List scrape runs.

#### `GET /scraper/runs/{run_id}`

Get run details.

#### `POST /scraper/runs/{run_id}/cancel`

Cancel pending job.

---

### Diagnostics

**Base path:** `/api/admin/sports/diagnostics`

#### `GET /missing-pbp`

Games missing play-by-play.

#### `GET /conflicts`

Unresolved game conflicts.

---

## Social

**Base path:** `/api/social`

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

**Base path:** `/api`

### `POST /api/users/{user_id}/games/{game_id}/reading-position`

Save reading position.

### `GET /api/users/{user_id}/games/{game_id}/resume`

Get reading position.

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

  // AI-generated compact story
  compact_story: string | null;
  word_count: number | null;
  target_word_count: number | null;
  quality: "LOW" | "MEDIUM" | "HIGH" | null;
  reading_time_estimate_minutes: number | null;

  // Metadata
  generated_at: string | null;
  has_compact_story: boolean;
  metadata: Record<string, any>;
}
```

### ChapterEntry

```typescript
interface ChapterEntry {
  chapter_id: string;              // "ch_001"
  index: number;
  play_start_idx: number;
  play_end_idx: number;
  play_count: number;
  reason_codes: string[];          // Why this chapter exists
  period: number | null;
  time_range: TimeRange | null;
  plays: PlayEntry[];
}
```

**Reason Codes:**
- `period_start` — Start of quarter/period
- `period_end` — End of quarter/period
- `timeout` — Timeout called
- `review` — Official review
- `overtime_start` — Start of overtime
- `game_end` — End of game

### SectionEntry

```typescript
interface SectionEntry {
  section_index: number;
  beat_type: BeatType;
  header: string;                  // Deterministic one-sentence anchor
  chapters_included: string[];
  start_score: { home: number; away: number };
  end_score: { home: number; away: number };
  notes: string[];
}
```

### Beat Types

| Beat Type | Description |
|-----------|-------------|
| `FAST_START` | Early energy, both teams scoring quickly |
| `BACK_AND_FORTH` | Tied or alternating leads |
| `EARLY_CONTROL` | One team gaining edge |
| `RUN` | Consecutive scoring (8+ unanswered) |
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
  game_clock: string | null;
  play_type: string | null;
  description: string;
  team: string | null;
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

---

## Consumers

- `scroll-down-app` (iOS)
- `scroll-down-sports-ui` (Web)

## Contract

Implements `scroll-down-api-spec`. Schema changes require spec update first.
