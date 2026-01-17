# Sports Data Admin API

> FastAPI backend for Scroll Down Sports: API, data scraper, admin UI.

**Base URL:** `/api`

---

## Table of Contents

1. [Health Check](#health-check)
2. [Games — Admin](#games--admin)
3. [Games — Moments](#games--moments)
4. [Games — Snapshots (App)](#games--snapshots-app)
5. [Timeline Generation](#timeline-generation)
6. [Teams](#teams)
7. [Scraper Runs](#scraper-runs)
8. [Job Runs](#job-runs)
9. [Diagnostics](#diagnostics)
10. [Social](#social)
11. [Reading Positions](#reading-positions)

---

## Health Check

### `GET /healthz`

```json
{ "status": "ok", "app": "ok", "db": "ok" }
```

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

Full game detail including moments.

```json
{
  "game": GameMeta,
  "team_stats": [...],
  "player_stats": [...],
  "odds": [...],
  "social_posts": [...],
  "plays": [...],
  "moments": [MomentEntry],
  "derived_metrics": {...}
}
```

### `POST /games/{game_id}/rescrape`

Trigger rescrape for a game.

### `POST /games/{game_id}/resync-odds`

Resync odds for a game.

---

## Games — Moments

Base path: `/api/admin/sports`

Moments partition the entire game timeline. Every play belongs to exactly one moment. **Highlights are moments where `is_notable=true`** — filter client-side.

### `GET /games/{game_id}/moments`

Get all moments for a game.

```json
{
  "game_id": 12345,
  "generated_at": "2026-01-16T19:42:00Z",
  "moments": [
    {
      "id": "m_003",
      "type": "FLIP",
      "start_play": 21,
      "end_play": 34,
      "play_count": 14,
      "teams": ["DEN", "BOS"],
      "players": [
        { "name": "N. Jokic", "stats": { "pts": 8 }, "summary": "8 pts" }
      ],
      "score_start": "9–12",
      "score_end": "9–18",
      "clock": "Q1 9:12–7:48",
      "is_notable": true,
      "note": "Lead changes hands",
      "run_info": {
        "team": "away",
        "points": 10,
        "unanswered": true,
        "play_ids": [22, 25, 28, 31]
      }
    }
  ],
  "total_count": 15,
  "highlight_count": 5
}
```

**Moment Types (Lead Ladder v2):**

> ⚠️ **MIGRATION (2026-01):** MomentTypes changed from the old system to Lead Ladder-based types.
> See [Migration Notes](#moment-type-migration) below.

| Type | Description | Notable? |
|------|-------------|----------|
| `LEAD_BUILD` | Lead tier increased (team extending control) | If tier change ≥ 2 |
| `CUT` | Lead tier decreased (opponent cutting in) | If tier change ≥ 2 |
| `TIE` | Game returned to even | Always |
| `FLIP` | Leader changed | Always |
| `CLOSING_CONTROL` | Late-game lock-in (dagger) | Always |
| `HIGH_IMPACT` | Ejection, injury, flagrant | Always |
| `OPENER` | First plays of a period | If strong lead |
| `NEUTRAL` | Normal flow, no tier changes | Never |

**New Optional Fields (v2):**

| Field | Type | Description |
|-------|------|-------------|
| `run_info` | object | Run metadata if a run contributed to this moment |
| `run_info.team` | string | "home" or "away" |
| `run_info.points` | int | Points scored in run |
| `run_info.unanswered` | bool | Always true (runs are unanswered by definition) |
| `run_info.play_ids` | int[] | Indices of scoring plays in run |
| `ladder_tier_before` | int | Lead Ladder tier at start (optional) |
| `ladder_tier_after` | int | Lead Ladder tier at end (optional) |
| `team_in_control` | string | "home", "away", or null |

**Key Fields:**
- `is_notable` — True for highlights (**unchanged, still the primary filter**)
- `start_play` / `end_play` — Play indices
- `players` — Stats within this moment (pts, ast, blk, stl)

### Moment Type Migration

**Deprecated Types (removed in v2):**

| Old Type | New Equivalent | Notes |
|----------|---------------|-------|
| `RUN` | ❌ Removed | Runs are now `run_info` metadata on LEAD_BUILD/CUT/FLIP moments |
| `BATTLE` | `FLIP`, `TIE`, `CUT` | Replaced by specific Lead Ladder crossing types |
| `CLOSING` | `CLOSING_CONTROL` | Renamed for clarity |

**Consumer Migration:**

1. **If filtering by `type`**: Update filters to handle new types
2. **If filtering by `is_notable`**: ✅ No changes needed (still works)
3. **If displaying `type`**: Update UI labels for new types
4. **New fields are additive**: Existing parsing will continue to work

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
| `level` | `int` | 1=highlights, 2=standard, 3=detailed |

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

## Response Models

### MomentEntry

```typescript
{
  id: string;           // "m_001"
  type: string;         // LEAD_BUILD, CUT, TIE, FLIP, CLOSING_CONTROL, HIGH_IMPACT, OPENER, NEUTRAL
  start_play: number;
  end_play: number;
  play_count: number;
  teams: string[];
  players: PlayerContribution[];
  score_start: string;  // "12–15"
  score_end: string;
  clock: string;        // "Q2 8:45–6:12"
  is_notable: boolean;  // Filter by this for highlights
  note: string | null;
  
  // New in v2 (optional, may not be present on older timelines)
  run_info?: RunInfo;            // If a run contributed to this moment
  ladder_tier_before?: number;   // Lead Ladder tier at moment start
  ladder_tier_after?: number;    // Lead Ladder tier at moment end
  team_in_control?: string;      // "home", "away", or null
  key_play_ids?: number[];       // Notable plays within moment
}
```

### RunInfo

```typescript
{
  team: string;         // "home" or "away"
  points: number;       // Points scored in the run
  unanswered: boolean;  // Always true (runs are unanswered)
  play_ids: number[];   // Indices of scoring plays in the run
}
```

### PlayerContribution

```typescript
{
  name: string;
  stats: { pts?: number; ast?: number; stl?: number; blk?: number };
  summary: string | null;  // "8 pts, 2 ast"
}
```

---

## Consumers

- `scroll-down-app` (iOS)
- `scroll-down-sports-ui` (Web)

## Contract

Implements `scroll-down-api-spec`. Schema changes require spec update first.
