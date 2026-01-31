# Sports Data Admin API

> FastAPI backend for Sports Data Admin: centralized sports data hub.

**Base URL:** `/api`

---

## Table of Contents

1. [Date & Time Convention](#date--time-convention)
2. [External App Integration Guide](#external-app-integration-guide)
3. [Health Check](#health-check)
4. [App Endpoints (Read-Only)](#app-endpoints-read-only)
5. [Admin Endpoints](#admin-endpoints)
   - [Games Management](#games-management)
   - [Story Pipeline](#story-pipeline)
   - [Timeline Generation](#timeline-generation)
   - [Teams](#teams)
   - [Scraper Runs](#scraper-runs)
   - [Diagnostics](#diagnostics)
   - [Jobs](#jobs)
   - [PBP Inspection](#pbp-inspection)
   - [Entity Resolution](#entity-resolution)
6. [Social](#social)
7. [FairBet](#fairbet)
8. [Reading Positions](#reading-positions)
9. [Response Models](#response-models)

---

## Date & Time Convention

### Game Dates (Request Parameters)

**All date parameters use Eastern Time (America/New_York).**

This represents "game day" as fans understand it:
- A 10:00 PM ET game on January 22 is a **"January 22 game"**
- Even though it's January 23 in UTC

Eastern Time automatically handles EST ↔ EDT transitions.

### Timestamps (Response Fields)

**All datetime fields in responses are UTC (ISO 8601).**

| Field | Timezone | Example |
|-------|----------|---------|
| `start_date` (request) | Eastern | `2026-01-22` |
| `end_date` (request) | Eastern | `2026-01-22` |
| `start_time` (response) | UTC | `2026-01-23T03:00:00Z` |
| `last_updated_at` (response) | UTC | `2026-01-23T05:30:00Z` |

### Client Display

For user-facing display, convert UTC to device local time:
```javascript
// JavaScript
new Date(game.start_time).toLocaleString()
```

---

## External App Integration Guide

This section is for **external Dock108 apps** consuming sports data. Use only the app endpoints (`/api/*`) listed here.

### Quick Start

**Recommended integration pattern:**

```
1. GET /api/games?start_date=2026-01-22&end_date=2026-01-22&league=NBA
   → List games for a specific day

2. GET /api/games/{game_id}                    → Get single game details
3. GET /api/games/{game_id}/pbp                → Get play-by-play
4. GET /api/games/{game_id}/social             → Get social posts
5. GET /api/games/{game_id}/story              → Get AI-generated narrative
6. GET /api/games/{game_id}/timeline           → Get full timeline artifact
```

**Common date queries:**
```
# Today's games (client determines "today" in Eastern Time)
GET /api/games?start_date=2026-01-22&end_date=2026-01-22

# Yesterday's games
GET /api/games?start_date=2026-01-21&end_date=2026-01-21

# Date range (weekend games)
GET /api/games?start_date=2026-01-18&end_date=2026-01-19

# All historical games (no end date)
GET /api/games?end_date=2026-01-21

# Include live games regardless of date
GET /api/games?start_date=2026-01-22&end_date=2026-01-22&include_live=true
```

### Supported Sports

| League | Code | Data Available |
|--------|------|----------------|
| NBA | `NBA` | Boxscores, PBP, Social, Odds, Stories, Timelines |
| NHL | `NHL` | Boxscores, PBP, Social, Odds, Timelines |
| NCAAB | `NCAAB` | Boxscores, PBP, Social, Odds, Timelines |

### Getting Games with All Data

**Step 1: List available games**
```http
GET /api/games?start_date=2026-01-22&end_date=2026-01-22&league=NBA
```

Response includes `has_pbp`, `has_social`, and `has_story` flags to indicate data availability.

**Step 2: Check what's available per game**
- `has_pbp: true` → Play-by-play is available at `/api/games/{id}/pbp`
- `has_social: true` → Social posts available at `/api/games/{id}/social`
- `has_story: true` → AI-generated story available at `/api/games/{id}/story`

**Step 3: Fetch detailed data**
Use the endpoints below to fetch PBP, social, timeline, and story data.

### Sport-Specific Display Considerations

#### NBA
- **Periods**: 4 quarters (1-4), overtime periods (5+)
- **Clock format**: `MM:SS` (12:00 → 0:00 per period)
- **Story support**: Full narrative stories available via `/api/games/{id}/story`
- **PBP play types**: `tip`, `made_shot`, `missed_shot`, `rebound`, `turnover`, `foul`, `free_throw`, etc.

#### NHL
- **Periods**: 3 periods (1-3), overtime (4), shootout (5)
- **Clock format**: `MM:SS` (20:00 → 0:00 per period)
- **Player stats**: Separate models for skaters vs goalies
- **PBP event types**: `faceoff`, `shot`, `goal`, `penalty`, `hit`, `block`, `giveaway`, `takeaway`, etc.

#### NCAAB
- **Periods**: 2 halves (1-2), overtime periods (3+)
- **Clock format**: `MM:SS` (20:00 → 0:00 per half)
- **Team names**: May include seeding info (e.g., "(1) Duke")
- **PBP play types**: Similar to NBA

### Stories vs Play-by-Play (NBA Flows)

**What are Stories?**

Stories are AI-generated narrative summaries built from play-by-play data. They condense a game into "moments" - small groups of related plays with narrative text.

**When to use Stories:**
- Display a readable game summary
- Show key moments without full PBP detail
- Provide spoiler-safe progressive reveal

**When to use raw PBP:**
- Build custom visualizations
- Show complete game timeline
- Need play-level granularity

**Story structure:**
```json
{
  "moments": [
    {
      "period": 1,
      "start_clock": "12:00",
      "end_clock": "10:45",
      "score_before": {"home": 0, "away": 0},
      "score_after": {"home": 5, "away": 2},
      "narrative": "The Lakers came out strong with a quick 5-0 run...",
      "play_count": 3
    }
  ]
}
```

**Availability:**
- NBA: Stories generated daily for recent games (via scheduled pipeline)
- NHL/NCAAB: Timeline artifacts available, stories coming soon

### Timeline vs Story

| Feature | Timeline | Story |
|---------|----------|-------|
| Purpose | Merged PBP + Social events | AI narrative moments |
| Granularity | Individual events | Grouped moments |
| Social included | Yes | No |
| Narrative text | No | Yes |
| Use case | Full chronological view | Summary/highlights |

### Data Freshness

| Data Type | Update Frequency |
|-----------|------------------|
| Game list | Real-time |
| Boxscores | Post-game (within ~30 min of final) |
| Play-by-play | Post-game (historical) or live polling |
| Social posts | 24-hour game window |
| Stories | Daily batch (7:15 AM ET for NBA) |
| Timelines | Daily batch (7:00 AM ET) |

### Error Handling

All endpoints return standard HTTP status codes:
- `200` - Success
- `404` - Game or resource not found
- `400` - Invalid parameters
- `500` - Server error

**Best practice:** Always check for `404` when fetching PBP, social, story, or timeline. Not all games have all data types.

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

List games by date range.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | `date` | No | Games on or after this date (Eastern Time) |
| `end_date` | `date` | No | Games on or before this date (Eastern Time) |
| `league` | `string` | No | Filter by league code (`NBA`, `NHL`, `NCAAB`) |
| `include_live` | `bool` | No | Include live games regardless of date filter |

**Date Format:** `YYYY-MM-DD` (e.g., `2026-01-22`)

**Important:** Dates are interpreted as **Eastern Time** (America/New_York). A game at 10pm ET on Jan 22 is a "Jan 22 game" even though it's Jan 23 in UTC.

**Example Requests:**
```http
# Single day
GET /api/games?start_date=2026-01-22&end_date=2026-01-22

# NBA games on a specific day
GET /api/games?start_date=2026-01-22&end_date=2026-01-22&league=NBA

# Date range
GET /api/games?start_date=2026-01-18&end_date=2026-01-22

# All games from a date onward
GET /api/games?start_date=2026-01-01

# All games up to a date
GET /api/games?end_date=2026-01-22

# Today's games plus any currently live
GET /api/games?start_date=2026-01-22&end_date=2026-01-22&include_live=true
```

**Response:**
```json
{
  "start_date": "2026-01-22",
  "end_date": "2026-01-22",
  "games": [
    {
      "id": 123,
      "league": "NBA",
      "status": "final",
      "start_time": "2026-01-23T00:00:00Z",
      "home_team": {"id": 1, "name": "Warriors", "abbreviation": "GSW"},
      "away_team": {"id": 2, "name": "Lakers", "abbreviation": "LAL"},
      "has_pbp": true,
      "has_social": false,
      "has_story": true,
      "last_updated_at": "2026-01-23T03:00:00Z"
    }
  ]
}
```

**Note:** `start_time` is UTC. The game above shows `2026-01-23T00:00:00Z` (midnight UTC) which is 7:00 PM ET on January 22. The request used `start_date=2026-01-22` (Eastern) to find this game.
```

### `GET /api/games/{game_id}`

Get a single game by ID.

**Response:**
```json
{
  "id": 123,
  "league": "NBA",
  "status": "final",
  "start_time": "2026-01-15T02:00:00Z",
  "home_team": {"id": 1, "name": "Warriors", "abbreviation": "GSW"},
  "away_team": {"id": 2, "name": "Lakers", "abbreviation": "LAL"},
  "has_pbp": true,
  "has_social": true,
  "has_story": true,
  "last_updated_at": "2026-01-15T05:00:00Z"
}
```

**Response (404):** Game not found or has missing team mappings.

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

### `GET /api/games/{game_id}/story`

Get the pre-generated story (AI narrative) for a game.

**Response (200):**
```json
{
  "game_id": 123,
  "sport": "NBA",
  "story_version": "v2-moments",
  "moments": [
    {
      "period": 1,
      "start_clock": "12:00",
      "end_clock": "10:45",
      "score_before": {"home": 0, "away": 0},
      "score_after": {"home": 5, "away": 2},
      "narrative": "The Lakers came out strong with a quick 5-0 run...",
      "play_count": 3
    }
  ],
  "moment_count": 15,
  "generated_at": "2026-01-22T15:30:00Z",
  "has_story": true
}
```

**Response (404):** Story not found. Stories are generated via admin pipeline.

**Notes:**
- This is a READ-ONLY endpoint returning cached stories
- Stories are generated daily for NBA games (7:15 AM ET)
- NHL/NCAAB story support coming soon
- Use `moments` array for progressive display
- `score_before`/`score_after` use `{home, away}` format in app endpoint

### `GET /api/games/{game_id}/timeline/diagnostic`

Diagnostic endpoint to inspect timeline artifact contents (for debugging).

Returns event type breakdown, first/last events, and timestamp ranges.

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
  "plays": [
    {
      "playId": 1,
      "playIndex": 1,
      "period": 1,
      "clock": "11:42",
      "playType": "3pt",
      "description": "K. Durant makes 3-pt shot from 24 ft",
      "homeScore": 0,
      "awayScore": 3
    }
  ],
  "validationPassed": true,
  "validationErrors": []
}
```

**Important Notes:**
- `playId` equals `playIndex` (the sequential play number, not a database ID)
- To join moments to plays: `plays.filter(p => moment.playIds.includes(p.playId))`
- `scoreBefore`/`scoreAfter` arrays are `[awayScore, homeScore]`
- `explicitlyNarratedPlayIds` are the key plays that the narrative must reference

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

#### `POST /bulk-generate-async`

Start bulk story generation for games in a date range.

**Request:**
```json
{
  "start_date": "2026-01-15",
  "end_date": "2026-01-20",
  "leagues": ["NBA", "NHL"],
  "force": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `start_date` | `string` | Start date (YYYY-MM-DD) |
| `end_date` | `string` | End date (YYYY-MM-DD) |
| `leagues` | `string[]` | League codes to include |
| `force` | `bool` | Regenerate existing stories |

**Response:**
```json
{
  "job_id": "abc-123-def-456",
  "message": "Bulk generation job started",
  "status_url": "/api/admin/sports/pipeline/bulk-generate-status/abc-123-def-456"
}
```

#### `GET /bulk-generate-status/{job_id}`

Get bulk generation job progress.

**Response:**
```json
{
  "job_id": "abc-123-def-456",
  "state": "PROGRESS",
  "current": 5,
  "total": 20,
  "successful": 4,
  "failed": 0,
  "skipped": 1,
  "result": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `state` | `string` | `PENDING`, `PROGRESS`, `SUCCESS`, `FAILURE` |
| `current` | `int` | Current game being processed |
| `total` | `int` | Total games to process |
| `successful` | `int` | Games with stories generated |
| `failed` | `int` | Games that failed |
| `skipped` | `int` | Games already having stories (when force=false) |
| `result` | `object\|null` | Final summary when complete |

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

### Jobs

**Base path:** `/api/admin/sports`

#### `GET /jobs`

List job runs (timeline generation, story generation, etc.).

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | `int` | Max results (1-200, default 50) |
| `phase` | `string` | Filter by phase: `timeline_generation`, `story_generation` |

**Response:**
```json
[
  {
    "id": 123,
    "phase": "timeline_generation",
    "leagues": ["NBA", "NHL"],
    "status": "completed",
    "started_at": "2026-01-22T12:00:00Z",
    "finished_at": "2026-01-22T12:05:00Z",
    "duration_seconds": 300,
    "error_summary": null,
    "created_at": "2026-01-22T12:00:00Z"
  }
]
```

---

### PBP Inspection

**Base path:** `/api/admin/sports/pbp`

Endpoints for inspecting play-by-play data at every stage of processing.

#### `GET /pbp/game/{game_id}`

Get current PBP for a game from `sports_game_plays` table.

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | `int` | Max plays (1-1000, default 500) |
| `offset` | `int` | Starting play index |

#### `GET /pbp/game/{game_id}/detail`

Get detailed PBP including raw data for each play.

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | `int` | Max plays (1-500, default 100) |
| `offset` | `int` | Starting play index |
| `quarter` | `int` | Filter by quarter (1-10) |

#### `GET /pbp/game/{game_id}/play/{play_index}`

Get a single play by index with full details.

#### `GET /pbp/game/{game_id}/snapshots`

List all PBP snapshots (raw, normalized, resolved) for a game.

#### `GET /pbp/snapshot/{snapshot_id}`

Get full details of a PBP snapshot including all plays.

#### `GET /pbp/pipeline-run/{run_id}`

Get PBP data associated with a specific pipeline run.

#### `GET /pbp/game/{game_id}/compare`

Compare current PBP with a specific snapshot.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `snapshot_id` | `int` | Yes | Snapshot to compare against |

#### `GET /pbp/game/{game_id}/resolution-issues`

List plays with resolution issues (missing team, player, etc.).

| Parameter | Type | Description |
|-----------|------|-------------|
| `issue_type` | `string` | Type: `team`, `player`, `score`, `all` |

---

### Entity Resolution

**Base path:** `/api/admin/sports/resolution`

Endpoints for inspecting how teams and players are resolved from source identifiers.

#### `GET /resolution/game/{game_id}`

Get entity resolution summary for a game from persisted records.

**Response:**
```json
{
  "game_id": 123,
  "pipeline_run_id": 456,
  "game_info": {
    "game_date": "2026-01-22",
    "home_team": "Lakers",
    "away_team": "Warriors"
  },
  "teams": {
    "total": 10,
    "resolved": 10,
    "failed": 0,
    "resolution_rate": 100.0
  },
  "players": {
    "total": 24,
    "resolved": 24,
    "failed": 0,
    "resolution_rate": 100.0
  },
  "team_resolutions": [...],
  "player_resolutions": [...],
  "issues": {
    "unresolved_teams": [],
    "ambiguous_teams": [],
    "unresolved_players": []
  }
}
```

#### `GET /resolution/game/{game_id}/live`

Analyze current PBP data for resolution issues without persisted records.

#### `GET /resolution/pipeline-run/{run_id}`

Get entity resolution summary for a specific pipeline run.

#### `GET /resolution/game/{game_id}/entity/{entity_type}/{source_identifier}`

Get detailed resolution for a specific entity.

| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_type` | `string` | `team` or `player` |
| `source_identifier` | `string` | Source identifier to look up |

#### `GET /resolution/issues`

List games with resolution issues.

| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_type` | `string` | Filter by type: `team` or `player` |
| `status_filter` | `string` | Filter: `failed`, `ambiguous`, or `all` |
| `limit` | `int` | Max results (1-200, default 50) |

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

## FairBet

**Base path:** `/api/fairbet`

Bet-centric odds comparison endpoints for the FairBet product.

### `GET /odds`

Get bet-centric odds for cross-book comparison.

| Parameter | Type | Description |
|-----------|------|-------------|
| `league` | `string` | Filter by league code (NBA, NHL, NCAAB) |
| `limit` | `int` | Max results (1-500, default 100) |
| `offset` | `int` | Pagination offset |

**Response:**
```json
{
  "bets": [
    {
      "game_id": 123,
      "league_code": "NBA",
      "home_team": "Lakers",
      "away_team": "Warriors",
      "game_date": "2026-01-22T03:00:00Z",
      "market_key": "spreads",
      "selection_key": "team:lakers",
      "line_value": -5.5,
      "books": [
        {
          "book": "draftkings",
          "price": -110,
          "observed_at": "2026-01-22T02:30:00Z"
        },
        {
          "book": "fanduel",
          "price": -108,
          "observed_at": "2026-01-22T02:30:00Z"
        }
      ]
    }
  ],
  "total": 250,
  "books_available": ["draftkings", "fanduel", "betmgm", "caesars"]
}
```

**Notes:**
- Only includes non-final games (scheduled, live)
- Bets are grouped by definition (game + market + selection + line)
- Books within each bet are sorted by best odds
- `line_value` of 0 is sentinel for moneyline (no line)
- `selection_key` format: `{entity_type}:{entity_slug}` (e.g., `team:lakers`, `total:over`)

**Data Source:** `fairbet_game_odds_work` table, populated during odds ingestion for non-completed games.

---

## Reading Positions

**Base path:** `/api`

### `POST /api/users/{user_id}/games/{game_id}/reading-position`

Save reading position.

### `GET /api/users/{user_id}/games/{game_id}/resume`

Get reading position.

---

## Response Models

### App Endpoint Models

These models are returned by the `/api/*` endpoints that external apps should use.

#### GameSnapshotResponse (from `GET /api/games`)

```typescript
interface GameSnapshotResponse {
  start_date: string | null;  // Filter start date (Eastern Time), YYYY-MM-DD
  end_date: string | null;    // Filter end date (Eastern Time), YYYY-MM-DD
  games: GameSnapshot[];
}
```

#### GameSnapshot (from `GET /api/games` and `GET /api/games/{game_id}`)

```typescript
interface GameSnapshot {
  id: number;
  league: string;           // "NBA", "NHL", "NCAAB"
  status: string;           // "scheduled", "live", "final"
  start_time: string;       // ISO 8601 datetime (UTC)
  home_team: TeamSnapshot;
  away_team: TeamSnapshot;
  has_pbp: boolean;         // PBP data available
  has_social: boolean;      // Social posts available
  has_story: boolean;       // AI-generated story available
  last_updated_at: string;  // ISO 8601 datetime (UTC)
}

interface TeamSnapshot {
  id: number;
  name: string;
  abbreviation: string | null;
}
```

**Timezone Note:** `start_time` and `last_updated_at` are UTC. Use request date parameters (Eastern Time) to understand "game day".
```

#### PbpResponse (from `GET /api/games/{id}/pbp`)

```typescript
interface PbpResponse {
  periods: PbpPeriod[];
}

interface PbpPeriod {
  period: number | null;    // 1-4 for NBA, 1-3 for NHL, 1-2 for NCAAB
  events: PbpEvent[];
}

interface PbpEvent {
  index: number;            // Sequential play index
  clock: string | null;     // "MM:SS" format
  description: string | null;
  play_type: string | null; // Sport-specific play type
}
```

#### SocialResponse (from `GET /api/games/{id}/social`)

```typescript
interface SocialResponse {
  posts: SocialPostSnapshot[];
}

interface SocialPostSnapshot {
  id: number;
  team: TeamSnapshot;
  content: string | null;
  posted_at: string;        // ISO 8601 datetime
  reveal_level: "pre" | "post";  // "pre" = safe, "post" = may contain spoilers
}
```

#### GameStorySnapshot (from `GET /api/games/{id}/story`)

```typescript
interface GameStorySnapshot {
  game_id: number;
  sport: string;
  story_version: string;    // e.g., "v2-moments"
  moments: MomentSnapshot[];
  moment_count: number;
  generated_at: string | null;
  has_story: boolean;
}

interface MomentSnapshot {
  period: number;
  start_clock: string | null;
  end_clock: string | null;
  score_before: { home: number; away: number };
  score_after: { home: number; away: number };
  narrative: string;        // AI-generated text
  play_count: number;       // Number of plays in this moment
}
```

#### TimelineArtifactStoredResponse (from `GET /api/games/{id}/timeline`)

```typescript
interface TimelineArtifactStoredResponse {
  game_id: number;
  sport: string;
  timeline_version: string;
  generated_at: string;
  timeline_json: TimelineEvent[];     // Ordered events
  game_analysis_json: object;         // Analysis metadata
  summary_json: object;               // Summary data
}

interface TimelineEvent {
  event_type: "pbp" | "tweet";
  synthetic_timestamp: string;        // For ordering
  // Additional fields vary by event_type
}
```

#### CompactTimelineResponse (from `GET /api/games/{id}/timeline/compact`)

```typescript
interface CompactTimelineResponse {
  game_id: number;
  sport: string;
  timeline_version: string;
  compression_level: number;          // 1=highlights, 2=standard, 3=detailed
  original_event_count: number;
  compressed_event_count: number;
  retention_rate: number;             // 0.0-1.0
  timeline_json: TimelineEvent[];
  summary_json: object | null;
}
```

### Admin Endpoint Models

These models are for admin operations only. External apps should not use these.

#### PlayEntry (Admin)

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

#### GameSummary (Admin)

```typescript
interface GameSummary {
  id: number;
  league_code: string;
  game_date: string;
  home_team: string;
  away_team: string;
  home_score: number | null;
  away_score: number | null;
  has_boxscore: boolean;
  has_player_stats: boolean;
  has_odds: boolean;
  has_social: boolean;
  has_pbp: boolean;
  has_story: boolean;
  play_count: number;
  social_post_count: number;
  has_required_data: boolean;
  scrape_version: number | null;
  last_scraped_at: string | null;
  last_ingested_at: string | null;
  last_pbp_at: string | null;
  last_social_at: string | null;
}
```

#### NHL-Specific Player Stats (Admin)

```typescript
// NHL uses separate models for skaters and goalies
interface NHLSkaterStat {
  team: string;
  player_name: string;
  toi: string | null;          // "MM:SS"
  goals: number | null;
  assists: number | null;
  points: number | null;
  shots_on_goal: number | null;
  plus_minus: number | null;
  penalty_minutes: number | null;
  hits: number | null;
  blocked_shots: number | null;
  raw_stats: object;
}

interface NHLGoalieStat {
  team: string;
  player_name: string;
  toi: string | null;          // "MM:SS"
  shots_against: number | null;
  saves: number | null;
  goals_against: number | null;
  save_percentage: number | null;
  raw_stats: object;
}
```

---

## Consumers

- Dock108 iOS apps (use `/api/*` endpoints only)
- Dock108 web apps (use `/api/*` endpoints only)
- Admin UI (uses `/api/admin/*` endpoints)

## Contract

Implements `scroll-down-api-spec`. Schema changes require spec update first.

---

## Appendix: Play Types by Sport

### NBA Play Types
- `tip` - Jump ball / tip-off
- `made_shot` - Made field goal
- `missed_shot` - Missed field goal
- `3pt` - Three-point shot
- `free_throw` - Free throw attempt
- `rebound` - Offensive or defensive rebound
- `turnover` - Turnover
- `steal` - Steal
- `block` - Blocked shot
- `foul` - Personal foul
- `timeout` - Timeout
- `substitution` - Player substitution
- `period_end` - End of period

### NHL Event Types
- `faceoff` - Face-off
- `shot` - Shot on goal
- `goal` - Goal scored
- `save` - Goalie save
- `miss` - Missed shot
- `block` - Blocked shot
- `hit` - Body check
- `penalty` - Penalty called
- `giveaway` - Puck giveaway
- `takeaway` - Puck takeaway
- `period_start` - Period start
- `period_end` - Period end
- `stoppage` - Play stoppage

### NCAAB Play Types
- Similar to NBA play types
- `made_shot`, `missed_shot`, `3pt`, `free_throw`
- `rebound`, `turnover`, `steal`, `block`, `foul`
- `timeout`, `substitution`
