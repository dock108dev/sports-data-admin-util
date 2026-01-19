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
  "total_count": 15
}
```

**Moment Types:**

| Type | Description | Notable? |
|------|-------------|----------|
| `LEAD_BUILD` | Lead tier increased (team extending control) | If tier change ≥ 2 |
| `CUT` | Lead tier decreased (opponent cutting in) | If tier change ≥ 2 |
| `TIE` | Game returned to even | Always |
| `FLIP` | Leader changed | Always |
| `CLOSING_CONTROL` | Late-game lock-in (dagger) | Always |
| `MOMENTUM_SHIFT` | Significant scoring run causing tier change | Always |
| `HIGH_IMPACT` | Ejection, injury, flagrant | Always |
| `NEUTRAL` | Normal flow, no tier changes | Never |
| `HALFTIME_RECAP` | Halftime contextual summary | Always |
| `PERIOD_RECAP` | End of period summary (NHL P1/P2/P3, MLB 5th/9th) | Always |
| `GAME_RECAP` | Final game summary | Always |
| `OVERTIME_RECAP` | Overtime period summary | Always |

**Optional Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `run_info` | object | Run metadata if a run contributed to this moment |
| `run_info.team` | string | "home" or "away" |
| `run_info.points` | int | Points scored in run |
| `run_info.unanswered` | bool | Always true (runs are unanswered by definition) |
| `run_info.play_ids` | int[] | Indices of scoring plays in run |
| `ladder_tier_before` | int | Lead Ladder tier at start |
| `ladder_tier_after` | int | Lead Ladder tier at end |
| `team_in_control` | string | "home", "away", or null |
| `is_recap` | bool | True for recap moments (zero-width contextual summaries) |
| `recap_context` | object | Contextual data for recap moments (see RecapContext below) |
| `score_context` | object | Structured score info with current/start scores, margin, leader |
| `key_players` | array | Top 3 players with meaningful contributions (filtered from players) |
| `importance_score` | float | Calculated importance score (0-100) |
| `importance_factors` | object | Factors contributing to importance score |
| `display_weight` | string | "high", "medium", or "low" - rendering prominence hint |
| `display_icon` | string | Suggested icon name for this moment type |
| `display_color_hint` | string | Color intent: "tension", "positive", "negative", "neutral", "recap" |

**Key Fields:**
- `is_notable` — True for notable moments (key game events)
- `start_play` / `end_play` — Play indices (recap moments have start_play = end_play, play_count = 0)
- `players` — All players with contributions in this moment
- `key_players` — Top 3 players with meaningful stats (pts, ast, blk, stl, reb)
- `is_recap` — True for recap moments (HALFTIME_RECAP, PERIOD_RECAP, GAME_RECAP, OVERTIME_RECAP)

**Recap Moments:**

Recap moments are special "zero-width" contextual summaries inserted at key game boundaries:
- **NBA**: Halftime (after Q2) and Final
- **NHL**: After each period (P1, P2, P3) and Final, plus Overtime if applicable
- **MLB**: After 5th inning, after 9th inning (or end of regulation), and Final

Recap moments:
- Have `play_count = 0` and `start_play = end_play` (they don't own plays)
- Provide contextual summaries via `recap_context` field
- Are always `is_notable = true`
- Help clarify late back-and-forths and momentum shifts
- Display with subtle visual distinction (10-15% more border via `display_color_hint = "recap"`)

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

## Response Models

### MomentEntry

```typescript
{
  id: string;           // "m_001"
  type: string;         // See Moment Types table above
  start_play: number;
  end_play: number;
  play_count: number;   // 0 for recap moments
  teams: string[];
  primary_team: string | null;   // The team that drove the narrative
  players: PlayerContribution[]; // All players with contributions
  key_players: PlayerContribution[]; // Top 3 players with meaningful stats
  score_start: string;  // "12–15" (away–home format)
  score_end: string;    // "12–15" (away–home format)
  clock: string;        // "Q2 8:45–6:12" or "Q2 Recap" for recap moments
  is_notable: boolean;  // Filter by this for highlights
  is_period_start: boolean; // True if this moment starts a new period
  is_recap: boolean;    // True for recap moments (zero-width summaries)
  note: string | null;
  headline: string;     // AI-generated headline (max 60 chars)
  summary: string;      // AI-generated summary (max 150 chars)
  
  // Display hints
  display_weight: string;      // "high", "medium", "low"
  display_icon: string;        // Suggested icon name
  display_color_hint: string;  // "tension", "positive", "negative", "neutral", "recap"
  
  // Optional fields
  run_info?: RunInfo;            // If a run contributed to this moment
  ladder_tier_before?: number;   // Lead Ladder tier at moment start
  ladder_tier_after?: number;    // Lead Ladder tier at moment end
  team_in_control?: string;      // "home", "away", or null
  key_play_ids?: number[];       // Notable plays within moment
  importance_score?: number;     // Calculated importance (0-100)
  importance_factors?: object;   // Factors contributing to score
  
  // Structured score info
  score_context?: {
    current: { home: number; away: number; formatted: string };
    start: { home: number; away: number; formatted: string };
    margin: number;
    leader: string | null;
  };
  
  // Recap context (only for recap moments)
  recap_context?: RecapContext;
  
  // Reason for moment existence
  reason?: {
    trigger: string;           // "tier_cross", "flip", "tie", "closing_lock", etc.
    control_shift: string | null; // "home", "away", or null
    narrative_delta: string;   // "tension ↑", "control gained", etc.
  };
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
  stats: { pts?: number; ast?: number; stl?: number; blk?: number; reb?: number };
  summary: string | null;  // "8 pts, 2 ast"
}
```

### RecapContext

Contextual summary data for recap moments (HALFTIME_RECAP, PERIOD_RECAP, GAME_RECAP, OVERTIME_RECAP).

Fields are prioritized in order of importance:

```typescript
{
  // Priority 1: Momentum and control (most important)
  momentum_summary: string;      // "Lakers finished strong" or "Back-and-forth battle"
  who_has_control: string | null; // "home", "away", or null (tied/unclear)
  
  // Priority 2: Key runs
  key_runs: Array<{
    team: string;                 // "home" or "away"
    points: number;               // Points in the run
    description: string;          // "14-2 run to close the half"
  }>;
  
  // Priority 3: Largest lead
  largest_lead: number;           // Biggest lead in the period
  largest_lead_team: string | null; // "home" or "away"
  
  // Priority 4: Lead changes
  lead_changes_count: number;     // Times the lead changed hands
  
  // Priority 5: Running score
  running_score: [number, number]; // [home, away] current game score
  
  // Priority 6: Top performers
  top_performers: Array<{
    name: string;
    team: string;                 // "home" or "away"
    stats: { pts?: number; ast?: number; reb?: number; stl?: number; blk?: number };
  }>;
  
  // Priority 7: Period score
  period_score: [number, number]; // [home, away] scoring in this period only
}
```

---

## Consumers

- `scroll-down-app` (iOS)
- `scroll-down-sports-ui` (Web)

## Contract

Implements `scroll-down-api-spec`. Schema changes require spec update first.
