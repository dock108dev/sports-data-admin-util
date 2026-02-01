# Sports Data Admin API

> FastAPI backend for Sports Data Admin: centralized sports data hub.

**Base URL:** `/api/admin/sports`

---

## Table of Contents

1. [Date & Time Convention](#date--time-convention)
2. [Quick Start](#quick-start)
3. [Health Check](#health-check)
4. [Games](#games)
5. [Stories](#stories)
6. [Timeline Generation](#timeline-generation)
7. [Teams](#teams)
8. [Scraper Runs](#scraper-runs)
9. [Story Pipeline](#story-pipeline)
10. [Diagnostics](#diagnostics)
11. [Jobs](#jobs)
12. [PBP Inspection](#pbp-inspection)
13. [Entity Resolution](#entity-resolution)
14. [Social](#social)
15. [FairBet](#fairbet)
16. [Reading Positions](#reading-positions)
17. [Response Models](#response-models)

---

## Date & Time Convention

### Request Parameters

Date parameters use **Eastern Time (America/New_York)**.

This represents "game day" as fans understand it:
- A 10:00 PM ET game on January 22 is a **"January 22 game"**
- Even though it's January 23 in UTC

### Response Fields

All datetime fields in responses are **UTC (ISO 8601)**.

| Field | Format | Example |
|-------|--------|---------|
| `startDate` (request) | Eastern | `2026-01-22` |
| `gameDate` (response) | UTC | `2026-01-23T03:00:00Z` |
| `lastScrapedAt` (response) | UTC | `2026-01-23T05:30:00Z` |

---

## Quick Start

**List games for a date:**
```http
GET /api/admin/sports/games?startDate=2026-01-22&endDate=2026-01-22&league=NBA
```

**Get game details:**
```http
GET /api/admin/sports/games/123
```

**Get game story:**
```http
GET /api/admin/sports/games/123/story
```

### Supported Leagues

| League | Code | Data Available |
|--------|------|----------------|
| NBA | `NBA` | Boxscores, PBP, Social, Odds, Stories, Timelines |
| NHL | `NHL` | Boxscores, PBP, Social, Odds, Timelines |
| NCAAB | `NCAAB` | Boxscores, PBP, Social, Odds, Timelines |

---

## Health Check

### `GET /healthz`

```json
{ "status": "ok", "app": "ok", "db": "ok" }
```

---

## Games

**Base path:** `/api/admin/sports`

### `GET /games`

List games with filtering and pagination.

| Parameter | Type | Description |
|-----------|------|-------------|
| `league` | `string[]` | Filter by league codes (NBA, NHL, NCAAB) |
| `season` | `int` | Filter by season year |
| `team` | `string` | Filter by team name (partial match) |
| `startDate` | `date` | Games on or after (Eastern Time) |
| `endDate` | `date` | Games on or before (Eastern Time) |
| `missingBoxscore` | `bool` | Games without boxscores |
| `missingPlayerStats` | `bool` | Games without player stats |
| `missingOdds` | `bool` | Games without odds |
| `missingSocial` | `bool` | Games without social posts |
| `missingAny` | `bool` | Games missing any data type |
| `safe` | `bool` | Exclude games with conflicts or missing team mappings |
| `limit` | `int` | Max results (1-200, default 50) |
| `offset` | `int` | Pagination offset |

**Response:**
```json
{
  "games": [
    {
      "id": 123,
      "leagueCode": "NBA",
      "gameDate": "2026-01-23T03:00:00Z",
      "homeTeam": "Lakers",
      "awayTeam": "Warriors",
      "homeScore": 112,
      "awayScore": 108,
      "hasBoxscore": true,
      "hasPlayerStats": true,
      "hasOdds": true,
      "hasSocial": true,
      "hasPbp": true,
      "hasStory": true,
      "playCount": 450,
      "socialPostCount": 12,
      "hasRequiredData": true,
      "scrapeVersion": 2,
      "lastScrapedAt": "2026-01-23T05:00:00Z",
      "lastIngestedAt": "2026-01-23T05:00:00Z",
      "lastPbpAt": "2026-01-23T05:00:00Z",
      "lastSocialAt": "2026-01-23T04:00:00Z"
    }
  ],
  "total": 245,
  "nextOffset": 50,
  "withBoxscoreCount": 240,
  "withPlayerStatsCount": 238,
  "withOddsCount": 245,
  "withSocialCount": 200,
  "withPbpCount": 230,
  "withStoryCount": 180
}
```

### `GET /games/{gameId}`

Full game detail including stats, odds, social posts, and plays.

**Response:**
```json
{
  "game": {
    "id": 123,
    "leagueCode": "NBA",
    "season": 2026,
    "seasonType": "regular",
    "gameDate": "2026-01-23T03:00:00Z",
    "homeTeam": "Lakers",
    "awayTeam": "Warriors",
    "homeScore": 112,
    "awayScore": 108,
    "status": "final",
    "hasBoxscore": true,
    "hasPlayerStats": true,
    "hasOdds": true,
    "hasSocial": true,
    "hasPbp": true,
    "hasStory": true,
    "playCount": 450,
    "socialPostCount": 12,
    "homeTeamXHandle": "@Lakers",
    "awayTeamXHandle": "@warriors"
  },
  "teamStats": [...],
  "playerStats": [...],
  "nhlSkaters": null,
  "nhlGoalies": null,
  "odds": [...],
  "socialPosts": [...],
  "plays": [...],
  "derivedMetrics": {...},
  "rawPayloads": {...},
  "dataHealth": null
}
```

### `POST /games/{gameId}/rescrape`

Trigger rescrape for a game.

**Response:**
```json
{
  "runId": 456,
  "jobId": "abc-123",
  "message": "Job enqueued"
}
```

### `POST /games/{gameId}/resync-odds`

Resync odds for a game.

---

## Stories

### `GET /games/{gameId}/story`

Get the AI-generated story for a game.

**Response:**
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
        "narrative": "Durant sinks a three-pointer from the corner...",
        "cumulativeBoxScore": {
          "home": {
            "team": "Lakers",
            "score": 0,
            "players": [],
            "goalie": null
          },
          "away": {
            "team": "Suns",
            "score": 3,
            "players": [
              {"name": "Kevin Durant", "pts": 3, "reb": 0, "ast": 0, "3pm": 1}
            ],
            "goalie": null
          }
        }
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

**Key Notes:**
- `playId` equals `playIndex` (sequential play number)
- To join moments to plays: `plays.filter(p => moment.playIds.includes(p.playId))`
- `scoreBefore`/`scoreAfter` arrays are `[awayScore, homeScore]`
- `explicitlyNarratedPlayIds` are the key plays referenced in the narrative
- `cumulativeBoxScore` contains running team scores and top player stats at this moment

**Response (404):** No story exists for this game.

### Story Structure

Stories are AI-generated narrative summaries built from play-by-play data. They condense a game into "moments" - small groups of related plays with narrative text.

**When to use Stories:**
- Display a readable game summary
- Show key moments without full PBP detail
- Provide progressive reveal of game events

---

## Timeline Generation

### `POST /timelines/generate/{gameId}`

Generate timeline artifact for a game.

**Response:**
```json
{
  "gameId": 123,
  "sport": "NBA",
  "timelineVersion": "v1",
  "generatedAt": "2026-01-23T05:00:00Z",
  "timeline": [...],
  "summary": {...},
  "gameAnalysis": {...}
}
```

### `GET /timelines/missing`

Games with PBP but no timeline.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `league_code` | `string` | Yes | NBA, NHL, NCAAB |
| `days_back` | `int` | No | Days to look back (default 7) |

### `POST /timelines/generate-batch`

Generate timelines for multiple games.

**Request:**
```json
{
  "game_ids": [123, 124, 125]
}
```

### `GET /timelines/existing`

Games with timeline artifacts.

### `POST /timelines/regenerate-batch`

Regenerate existing timelines.

---

## Teams

### `GET /teams`

List teams with game counts.

**Response:**
```json
{
  "teams": [
    {
      "id": 1,
      "name": "Los Angeles Lakers",
      "shortName": "Lakers",
      "abbreviation": "LAL",
      "leagueCode": "NBA",
      "gamesCount": 45
    }
  ],
  "total": 30
}
```

### `GET /teams/{teamId}`

Team detail with recent games.

### `GET /teams/{teamId}/social`

Team social media info.

---

## Scraper Runs

### `POST /scraper/runs`

Create scrape job.

**Request:**
```json
{
  "config": {
    "leagueCode": "NBA",
    "startDate": "2026-01-22",
    "endDate": "2026-01-22",
    "boxscores": true,
    "odds": true,
    "social": false,
    "pbp": false
  }
}
```

### `GET /scraper/runs`

List scrape runs.

### `GET /scraper/runs/{runId}`

Get run details.

### `POST /scraper/runs/{runId}/cancel`

Cancel pending job.

---

## Story Pipeline

**Base path:** `/api/admin/sports/pipeline`

### `POST /runs`

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

### `GET /runs/{runId}`

Get pipeline run status.

**Response:**
```json
{
  "run_id": 456,
  "run_uuid": "abc-123-def",
  "game_id": 123,
  "status": "running",
  "current_stage": "GENERATE_MOMENTS",
  "stages": [...],
  "stages_completed": 2,
  "stages_total": 6,
  "progress_percent": 33
}
```

### `POST /runs/{runId}/advance`

Advance to the next stage (when not using auto_chain).

### `POST /batch`

Run pipeline for multiple games.

### `GET /stages`

Get pipeline stage definitions.

### `POST /bulk-generate-async`

Start bulk story generation.

**Request:**
```json
{
  "start_date": "2026-01-15",
  "end_date": "2026-01-20",
  "leagues": ["NBA", "NHL"],
  "force": false
}
```

### `GET /bulk-generate-status/{jobId}`

Get bulk generation job progress.

---

## Diagnostics

**Base path:** `/api/admin/sports`

### `GET /missing-pbp`

Games missing play-by-play.

### `GET /conflicts`

Unresolved game conflicts.

---

## Jobs

### `GET /jobs`

List job runs.

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | `int` | Max results (1-200, default 50) |
| `phase` | `string` | Filter: `timeline_generation`, `story_generation` |

---

## PBP Inspection

**Base path:** `/api/admin/sports/pbp`

### `GET /pbp/game/{gameId}`

Get current PBP for a game.

### `GET /pbp/game/{gameId}/detail`

Get detailed PBP including raw data.

### `GET /pbp/game/{gameId}/play/{playIndex}`

Get a single play by index.

### `GET /pbp/game/{gameId}/snapshots`

List all PBP snapshots for a game.

### `GET /pbp/snapshot/{snapshotId}`

Get full snapshot details.

### `GET /pbp/game/{gameId}/compare`

Compare current PBP with a snapshot.

### `GET /pbp/game/{gameId}/resolution-issues`

List plays with resolution issues.

---

## Entity Resolution

**Base path:** `/api/admin/sports/resolution`

### `GET /resolution/game/{gameId}`

Get entity resolution summary.

### `GET /resolution/game/{gameId}/live`

Analyze current PBP for resolution issues.

### `GET /resolution/pipeline-run/{runId}`

Get resolution summary for a pipeline run.

### `GET /resolution/issues`

List games with resolution issues.

---

## Social

**Base path:** `/api/social`

### `GET /posts`

List social posts.

### `GET /posts/game/{gameId}`

Posts for a game.

### `POST /posts`

Create post.

### `POST /posts/bulk`

Bulk create posts.

### `DELETE /posts/{postId}`

Delete post.

### `GET /accounts`

List social accounts.

### `POST /accounts`

Create/update account.

---

## FairBet

**Base path:** `/api/fairbet`

Simple odds comparison tool displaying betting lines from multiple sportsbooks.

### Supported Leagues

- NBA
- NHL
- NCAAB

### `GET /odds`

Get bet-centric odds for cross-book comparison.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `league` | `string` | — | Filter by league code |
| `limit` | `int` | 100 | Max results (1-500) |
| `offset` | `int` | 0 | Pagination offset |

**Response:**
```json
{
  "bets": [
    {
      "game_id": 123,
      "league_code": "NBA",
      "home_team": "Los Angeles Lakers",
      "away_team": "Boston Celtics",
      "game_date": "2025-01-31T19:00:00Z",
      "market_key": "spreads",
      "selection_key": "team:los_angeles_lakers",
      "line_value": -3.5,
      "books": [
        {"book": "DraftKings", "price": -110, "observed_at": "2025-01-31T18:00:00Z"},
        {"book": "FanDuel", "price": -108, "observed_at": "2025-01-31T18:00:00Z"}
      ]
    }
  ],
  "total": 245,
  "books_available": ["DraftKings", "FanDuel", "BetMGM", "Caesars", "PointsBet"]
}
```

**Field Notes:**
- `market_key`: `"h2h"` (moneyline), `"spreads"`, or `"totals"`
- `selection_key`: `{entity_type}:{entity_slug}` (e.g., `"team:los_angeles_lakers"`)
- `line_value`: Spread or total number; `0` for moneyline

---

## Reading Positions

**Base path:** `/api`

### `POST /api/users/{userId}/games/{gameId}/reading-position`

Save reading position.

### `GET /api/users/{userId}/games/{gameId}/resume`

Get reading position.

---

## Response Models

All responses use **camelCase** field names.

### GameSummary

```typescript
interface GameSummary {
  id: number;
  leagueCode: string;
  gameDate: string;           // ISO 8601 UTC
  homeTeam: string;
  awayTeam: string;
  homeScore: number | null;
  awayScore: number | null;
  hasBoxscore: boolean;
  hasPlayerStats: boolean;
  hasOdds: boolean;
  hasSocial: boolean;
  hasPbp: boolean;
  hasStory: boolean;
  playCount: number;
  socialPostCount: number;
  hasRequiredData: boolean;
  scrapeVersion: number | null;
  lastScrapedAt: string | null;
  lastIngestedAt: string | null;
  lastPbpAt: string | null;
  lastSocialAt: string | null;
}
```

### GameListResponse

```typescript
interface GameListResponse {
  games: GameSummary[];
  total: number;
  nextOffset: number | null;
  withBoxscoreCount: number;
  withPlayerStatsCount: number;
  withOddsCount: number;
  withSocialCount: number;
  withPbpCount: number;
  withStoryCount: number;
}
```

### GameStoryResponse

```typescript
interface GameStoryResponse {
  gameId: number;
  story: StoryContent;
  plays: StoryPlay[];
  validationPassed: boolean;
  validationErrors: string[];
}

interface StoryContent {
  moments: StoryMoment[];
}

interface StoryMoment {
  playIds: number[];
  explicitlyNarratedPlayIds: number[];
  period: number;
  startClock: string | null;
  endClock: string | null;
  scoreBefore: number[];      // [away, home]
  scoreAfter: number[];       // [away, home]
  narrative: string;
  cumulativeBoxScore: MomentBoxScore | null;  // Running stats snapshot
}

// Cumulative box score at a moment in time
interface MomentBoxScore {
  home: MomentTeamBoxScore;
  away: MomentTeamBoxScore;
}

interface MomentTeamBoxScore {
  team: string;               // Team name
  score: number;              // Running score at this moment
  players: MomentPlayerStat[];  // Top contributors (up to 5)
  goalie: MomentGoalieStat | null;  // NHL only
}

// Basketball player stats (NBA/NCAAB)
interface MomentPlayerStat {
  name: string;
  pts?: number;    // Points
  reb?: number;    // Rebounds
  ast?: number;    // Assists
  "3pm"?: number;  // Three-pointers made
  // NHL stats (when league is NHL)
  goals?: number;
  assists?: number;
  sog?: number;    // Shots on goal
  plusMinus?: number;
}

// NHL goalie stats
interface MomentGoalieStat {
  name: string;
  saves: number;
  ga: number;       // Goals against
  savePct: number;  // Save percentage (0.0-1.0)
}

interface StoryPlay {
  playId: number;
  playIndex: number;
  period: number;
  clock: string | null;
  playType: string | null;
  description: string | null;
  homeScore: number | null;
  awayScore: number | null;
}
```

### NHL Player Stats

```typescript
interface NHLSkaterStat {
  team: string;
  playerName: string;
  toi: string | null;         // "MM:SS"
  goals: number | null;
  assists: number | null;
  points: number | null;
  shotsOnGoal: number | null;
  plusMinus: number | null;
  penaltyMinutes: number | null;
  hits: number | null;
  blockedShots: number | null;
  rawStats: object;
}

interface NHLGoalieStat {
  team: string;
  playerName: string;
  toi: string | null;
  shotsAgainst: number | null;
  saves: number | null;
  goalsAgainst: number | null;
  savePercentage: number | null;
  rawStats: object;
}
```

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
