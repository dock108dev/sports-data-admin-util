# Sports Data Admin API

> FastAPI backend for Sports Data Admin: centralized sports data hub.

**Base URL:** `/api`

---

## Table of Contents

1. [Health Check](#health-check)
2. [App Endpoints (Read-Only)](#app-endpoints-read-only)
3. [Admin Endpoints](#admin-endpoints)
   - [Games Management](#games-management)
   - [Story Pipeline](#story-pipeline)
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

#### `GET /games/{game_id}/story`

Get the story for a game (v2-moments format).

**Response (200):**
```json
{
  "gameId": 123,
  "story": {
    "moments": [
      {
        "playIds": [1, 2, 3],
        "explicitlyNarratedPlayIds": [2],
        "period": 1,
        "startClock": "11:42",
        "endClock": "11:00",
        "scoreBefore": [0, 0],
        "scoreAfter": [3, 0],
        "narrative": "Durant sinks a three-pointer from the corner..."
      }
    ]
  },
  "plays": [...],
  "validationPassed": true,
  "validationErrors": []
}
```

**Response (404):** No story exists for this game.

---

### Story Pipeline

**Base path:** `/api/admin/sports/pipeline`

Endpoints for managing the story generation pipeline.

#### `POST /runs`

Start a new pipeline run for a game.

**Request:**
```json
{
  "game_id": 123,
  "auto_chain": true
}
```

**Response:**
```json
{
  "run_id": 456,
  "run_uuid": "abc-123-def",
  "status": "pending",
  "message": "Pipeline run created"
}
```

#### `GET /runs/{run_id}`

Get pipeline run status and stage details.

**Response:**
```json
{
  "run_id": 456,
  "run_uuid": "abc-123-def",
  "game_id": 123,
  "status": "running",
  "current_stage": "GENERATE_MOMENTS",
  "stages": [
    {
      "stage": "NORMALIZE_PBP",
      "status": "success",
      "started_at": "...",
      "finished_at": "...",
      "has_output": true
    },
    ...
  ],
  "stages_completed": 2,
  "stages_total": 6,
  "progress_percent": 33
}
```

#### `POST /runs/{run_id}/advance`

Advance to the next stage (when not using auto_chain).

#### `POST /batch`

Run pipeline for multiple games.

**Request:**
```json
{
  "game_ids": [123, 124, 125],
  "auto_chain": true
}
```

#### `GET /stages`

Get pipeline stage definitions and descriptions.

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

### GameSummary

```typescript
interface GameSummary {
  game_id: number;
  sport: string;
  status: string;
  game_date: string;
  home_team: TeamSummary;
  away_team: TeamSummary;
  home_score: number | null;
  away_score: number | null;
  has_pbp: boolean;
  has_social: boolean;
  play_count: number;
}
```

### TeamSummary

```typescript
interface TeamSummary {
  team_id: number;
  name: string;
  abbreviation: string;
}
```

---

## Consumers

- Dock108 iOS apps
- Dock108 web apps

## Contract

Implements `scroll-down-api-spec`. Schema changes require spec update first.
