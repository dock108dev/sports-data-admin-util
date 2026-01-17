# Sports Data Admin API — Complete Endpoint Reference

> FastAPI service for sports data administration. Backend infrastructure for Scroll Down Sports: API, data scraper, admin UI.

**Base URL:** `/api` (varies by environment)  
**Version:** 1.0.0

---

## Table of Contents

1. [Health Check](#health-check)
2. [Games — Admin](#games--admin)
3. [Games — Compact Mode](#games--compact-mode)
4. [Games — Snapshots (App Consumption)](#games--snapshots-app-consumption)
5. [Timeline Generation (Admin)](#timeline-generation-admin)
6. [Teams](#teams)
7. [Scraper Runs](#scraper-runs)
8. [Job Runs](#job-runs)
9. [Diagnostics](#diagnostics)
10. [Social](#social)
11. [Reading Positions](#reading-positions)
12. [Environment Variables](#environment-variables)
13. [Response Models](#response-models)

---

## Health Check

### `GET /healthz`

Liveness + database readiness check.

**Response:**
```json
{
  "status": "ok",
  "app": "ok",
  "db": "ok"
}
```

**Status Codes:**
- `200` — All dependencies healthy
- `503` — Database unavailable (returns `"error": "database unavailable"`)

---

## Games — Admin

Base path: `/api/admin/sports`

### `GET /games`

List games with filtering and pagination.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `league` | `string[]` | `null` | Filter by league codes (e.g., `NBA`, `NHL`) |
| `season` | `int` | `null` | Filter by season year |
| `team` | `string` | `null` | Filter by team name/abbreviation |
| `startDate` | `date` | `null` | Filter games on or after this date |
| `endDate` | `date` | `null` | Filter games on or before this date |
| `missingBoxscore` | `bool` | `false` | Only games without boxscores |
| `missingPlayerStats` | `bool` | `false` | Only games without player stats |
| `missingOdds` | `bool` | `false` | Only games without odds data |
| `missingSocial` | `bool` | `false` | Only games without social posts |
| `missingAny` | `bool` | `false` | Games missing any data type |
| `limit` | `int` | `50` | Max results (1-200) |
| `offset` | `int` | `0` | Pagination offset |

**Response:** `GameListResponse`
```json
{
  "games": [GameSummary],
  "total": 1234,
  "next_offset": 50,
  "with_boxscore_count": 1000,
  "with_player_stats_count": 950,
  "with_odds_count": 800,
  "with_social_count": 600,
  "with_pbp_count": 500,
  "with_highlights_count": 450
}
```

---

### `GET /games/{game_id}`

Get detailed game data including stats, odds, social posts, and plays.

**Path Parameters:**
- `game_id` (int, required): Game ID

**Response:** `GameDetailResponse`
```json
{
  "game": GameMeta,
  "team_stats": [TeamStat],
  "player_stats": [PlayerStat],
  "odds": [OddsEntry],
  "social_posts": [SocialPostEntry],
  "plays": [PlayEntry],
  "highlights": [HighlightEntry],
  "derived_metrics": {},
  "raw_payloads": {}
}
```

**Status Codes:**
- `404` — Game not found

---

### `GET /games/{game_id}/preview-score`

Get pre-game excitement and quality scores with preview tags.

**Path Parameters:**
- `game_id` (int, required): Game ID

**Response:** `GamePreviewScoreResponse`
```json
{
  "game_id": "123",
  "excitement_score": 75,
  "quality_score": 82,
  "tags": ["rivalry", "playoff-implications"],
  "nugget": "First meeting since the playoff clash last May."
}
```

**Status Codes:**
- `404` — Game not found
- `422` — Game missing team data
- `503` — Preview score unavailable (ratings/standings fetch failed)

---

### `POST /games/{game_id}/rescrape`

Trigger a rescrape job for a specific game (boxscores only).

**Path Parameters:**
- `game_id` (int, required): Game ID

**Response:** `JobResponse`
```json
{
  "run_id": 456,
  "job_id": "celery-task-id",
  "message": "Job enqueued"
}
```

---

### `POST /games/{game_id}/resync-odds`

Trigger a resync of odds data for a specific game.

**Path Parameters:**
- `game_id` (int, required): Game ID

**Response:** `JobResponse`

---

### `POST /games/{game_id}/timeline/generate`

Generate and store a finalized timeline artifact for a game.

**Path Parameters:**
- `game_id` (int, required): Game ID

**Response:** `TimelineArtifactResponse`
```json
{
  "game_id": 123,
  "sport": "NBA",
  "timeline_version": "v1",
  "generated_at": "2026-01-16T04:30:00Z",
  "timeline": [...],
  "summary": {...},
  "game_analysis": {...}
}
```

**Status Codes:**
- `404` — Game not found
- `422` — Timeline generation failed (missing data)

---

### `GET /games/{game_id}/highlights`

Get grounded highlights for a game.

**Path Parameters:**
- `game_id` (int, required): Game ID

**Response:** `HighlightsResponse`
```json
{
  "game_id": 12345,
  "generated_at": "2026-01-16T19:42:00Z",
  "highlights": [
    {
      "highlight_id": "hl_a1b2c3d4",
      "type": "SCORING_RUN",
      "title": "Denver opens the game on an 8–0 run",
      "description": "Denver set the tone early, forcing a quick timeout.",
      "start_play_id": "21",
      "end_play_id": "34",
      "key_play_ids": ["23", "29"],
      "involved_teams": ["DEN", "BOS"],
      "involved_players": ["N. Jokic"],
      "score_change": "12–9 → 18–9",
      "game_clock_range": "Q1 9:12–7:48",
      "game_phase": "early",
      "importance_score": 0.72
    }
  ],
  "total_count": 5
}
```

**Highlight Types:**
| Type | Description |
|------|-------------|
| `SCORING_RUN` | Team goes on a scoring streak (≥8 unanswered points) |
| `LEAD_CHANGE` | Lead swings from one team to another |
| `MOMENTUM_SHIFT` | Significant margin change or quarter-end swing |
| `GAME_DECIDING_STRETCH` | Final stretch that determined the outcome |
| `COMEBACK` | Team erases significant deficit |
| `STAR_TAKEOVER` | Star player dominates a stretch |

**Design Notes:**
- `start_play_id`, `end_play_id`, `key_play_ids` are join keys to `/timeline`
- `key_play_ids` lets the UI jump directly to pivotal moments
- `type` is enum-stable for filtering
- Ordering is by `importance_score` (editorial), not strictly chronological

**Highlights Concept:**

Highlights represent high-signal narrative moments extracted from the game timeline. Each highlight is:
- Grounded in real play-by-play events
- Traceable to specific play IDs
- Enriched with contextual information (score, timing, players)

Highlights are NOT a replacement for the full timeline. They are curated entry points into the most important moments of the game. Consumers may:
- Display highlights as a summary feed
- Link highlights to the timeline using `play_id` references
- Use highlight types to group or filter moments

---

## Games — Compact Mode

Base path: `/api/admin/sports`

Compact mode provides summarized game moments for efficient timeline display.

### `GET /games/{game_id}/compact`

Get all moments for a game in compact format.

**Response:** `CompactMomentsResponse`
```json
{
  "moments": [
    {
      "playIndex": 1,
      "quarter": 1,
      "gameClock": "12:00",
      "momentType": "tip",
      "hint": "Tipoff"
    }
  ],
  "momentTypes": ["tip", "shot", "foul"],
  "scoreChips": [
    {"playIndex": 10, "label": "Q1 End", "homeScore": 28, "awayScore": 24}
  ]
}
```

---

### `GET /games/{game_id}/compact/{moment_id}/pbp`

Get play-by-play entries for a specific moment range.

**Path Parameters:**
- `game_id` (int): Game ID
- `moment_id` (int): Play index of the moment

**Response:** `CompactPbpResponse`
```json
{
  "plays": [PlayEntry]
}
```

---

### `GET /games/{game_id}/compact/{moment_id}/posts`

Get social posts near a specific moment.

**Response:** `CompactPostsResponse`
```json
{
  "posts": [
    {
      "id": 99,
      "post_url": "https://x.com/...",
      "posted_at": "2026-01-15T02:30:00Z",
      "has_video": true,
      "team_abbreviation": "GSW",
      "tweet_text": "What a play!",
      "video_url": "...",
      "containsScore": false
    }
  ]
}
```

---

### `GET /games/{game_id}/compact/{moment_id}/summary`

Get AI-generated summary for a moment.

**Response:** `CompactMomentSummaryResponse`
```json
{
  "summary": "Curry hits a deep three to extend the lead..."
}
```

---

## Games — Snapshots (App Consumption)

Base path: `/api`

These endpoints are designed for mobile/web app consumption.

### `GET /api/games`

List games by time window for app display.

List games by time window for app display.

**Example requests:**
```bash
# Current day's games
curl "https://sports-data-admin.dock108.ai/api/games?range=current"

# Filter by league
curl "https://sports-data-admin.dock108.ai/api/games?range=current&league=NBA"
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `range` | `string` | `current` | Time window: `last2` (48h ago), `current` (today), `next24` |
| `league` | `string` | `null` | Filter by league code |
| `assume_now` | `datetime` | `null` | Override current time (dev only) |

**Response:** `GameSnapshotResponse`
```json
{
  "range": "current",
  "games": [
    {
      "id": 123,
      "league": "NBA",
      "status": "live",
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

**Notes:**
- Games with unresolved conflicts are excluded
- Games missing team mappings are excluded

---

### `GET /api/games/{game_id}/pbp`

Fetch play-by-play grouped by period.

**Response:** `PbpResponse`
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

---

### `GET /api/games/{game_id}/social`

Fetch social posts ordered by posted time.

**Response:** `SocialResponse`
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

**Reveal Levels:** `pre` (safe), `post` (contains spoilers)

---

### `GET /api/games/{game_id}/timeline`

Fetch the stored finalized timeline artifact for a game.

**Response:** `TimelineArtifactResponse`
```json
{
  "game_id": 123,
  "sport": "NBA",
  "timeline_version": "v1",
  "generated_at": "2026-01-15T04:30:00Z",
  "timeline": [
    {
      "event_type": "pbp",
      "play_index": 1,
      "quarter": 1,
      "game_clock": "12:00",
      "description": "Tipoff",
      "synthetic_timestamp": "2026-01-15T02:00:00Z",
      "timeline_block": "q1"
    },
    {
      "event_type": "tweet",
      "post_url": "https://x.com/warriors/status/123",
      "tweet_text": "Game day.",
      "synthetic_timestamp": "2026-01-15T02:10:00Z"
    }
  ],
  "game_analysis": {
    "segments": [
      {
        "segment_id": "segment_1",
        "start_timestamp": "2026-01-15T02:00:00Z",
        "end_timestamp": "2026-01-15T02:10:00Z",
        "segment_type": "opening",
        "teams_involved": [1],
        "score_start": {"home": 2, "away": 0},
        "score_end": {"home": 12, "away": 8},
        "score_delta": {"home": 10, "away": 8},
        "key_event_ids": [0, 1, 2]
      }
    ],
    "highlights": [
      {
        "highlight_type": "scoring_run",
        "start_timestamp": "2026-01-15T02:00:00Z",
        "end_timestamp": "2026-01-15T02:04:00Z",
        "teams_involved": [1],
        "score_context": {
          "points": 8,
          "start_score": {"home": 2, "away": 0},
          "end_score": {"home": 10, "away": 0},
          "team_id": 1
        },
        "related_segment_id": "segment_1"
      }
    ]
  },
  "summary": {
    "teams": {
      "home": {"id": 1, "name": "Warriors"},
      "away": {"id": 2, "name": "Lakers"}
    },
    "final_score": {"home": 110, "away": 103},
    "flow": "competitive"
  }
}
```

---

### `GET /api/games/{game_id}/timeline/diagnostic`

Get diagnostic information about timeline generation for a game.

**Path Parameters:**
- `game_id` (int, required): Game ID

**Response:**
```json
{
  "game_id": 123,
  "has_artifact": true,
  "artifact_version": "v1",
  "generated_at": "2026-01-15T04:30:00Z",
  "pbp_count": 250,
  "social_count": 15,
  "timeline_event_count": 265,
  "segment_count": 8,
  "highlight_count": 5
}
```

---

### `GET /api/games/{game_id}/timeline/compact`

Get a compact version of the timeline optimized for app consumption.

**Path Parameters:**
- `game_id` (int, required): Game ID

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `compression` | `string` | `STANDARD` | Compression level: `HIGHLIGHTS`, `STANDARD`, `DETAILED` |

**Response:** `CompactTimelineResponse`
```json
{
  "game_id": 123,
  "compression_level": "STANDARD",
  "events": [
    {
      "event_type": "pbp",
      "play_index": 1,
      "quarter": 1,
      "game_clock": "12:00",
      "description": "Tipoff",
      "is_highlight": false
    }
  ],
  "event_count": 50,
  "original_count": 265
}
```

---

### `GET /api/games/{game_id}/recap`

Generate a recap for a game at a reveal level.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `reveal` | `string` | `pre` | Reveal level: `pre`, `post` |

**Response:** `RecapResponse`
```json
{
  "game_id": 123,
  "reveal": "pre",
  "available": true,
  "summary": "The game featured momentum swings and key stretches.",
  "reason": null
}
```

---

## Timeline Generation (Admin)

Base path: `/api/admin/sports`

Endpoints for managing timeline artifact generation and regeneration.

### `POST /timelines/generate/{game_id}`

Generate timeline artifact for a specific game.

**Path Parameters:**
- `game_id` (int, required): Game ID

**Request Body:**
```json
{
  "timeline_version": "v1"
}
```

**Response:** `TimelineGenerationResponse`
```json
{
  "game_id": 123,
  "timeline_version": "v1",
  "success": true,
  "message": "Timeline generated successfully"
}
```

**Status Codes:**
- `400` — Game not completed or missing PBP data
- `404` — Game not found
- `500` — Timeline generation failed

---

### `GET /timelines/missing`

List games that have play-by-play data but are missing timeline artifacts.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `league_code` | `string` | `NBA` | League code to filter by |
| `days_back` | `int` | `7` | Days back to check (1-90) |

**Response:** `MissingTimelinesResponse`
```json
{
  "games": [
    {
      "game_id": 123,
      "game_date": "2026-01-15",
      "league": "NBA",
      "home_team": "Warriors",
      "away_team": "Lakers",
      "status": "final",
      "has_pbp": true
    }
  ],
  "total_count": 5
}
```

---

### `POST /timelines/generate-batch`

Synchronously generate timelines for multiple games.

**Request Body:**
```json
{
  "league_code": "NBA",
  "days_back": 7,
  "max_games": 10
}
```

**Response:** `SyncBatchGenerationResponse`
```json
{
  "games_processed": 10,
  "games_successful": 8,
  "games_failed": 2,
  "failed_game_ids": [456, 789],
  "message": "Batch generation complete"
}
```

---

### `GET /timelines/existing`

List games that have timeline artifacts, with staleness detection.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `league_code` | `string` | `NBA` | League code to filter by |
| `days_back` | `int` | `7` | Days back to check (1-90) |
| `only_stale` | `bool` | `false` | Only show stale timelines |

**Response:** `ExistingTimelinesResponse`
```json
{
  "games": [
    {
      "game_id": 123,
      "game_date": "2026-01-15",
      "league": "NBA",
      "home_team": "Warriors",
      "away_team": "Lakers",
      "status": "final",
      "has_pbp": true,
      "generated_at": "2026-01-15T04:30:00Z",
      "last_social_at": "2026-01-15T06:00:00Z",
      "is_stale": true
    }
  ],
  "total_count": 20,
  "stale_count": 3
}
```

**Staleness Detection:**

A timeline is considered "stale" when `last_social_at > generated_at`, indicating that new social posts have been added since the timeline was generated.

---

### `POST /timelines/regenerate-batch`

Regenerate timeline artifacts for games that already have them.

**Request Body:**
```json
{
  "league_code": "NBA",
  "days_back": 7,
  "max_games": null,
  "only_stale": true
}
```

**Response:** `SyncBatchGenerationResponse`
```json
{
  "games_processed": 5,
  "games_successful": 5,
  "games_failed": 0,
  "failed_game_ids": [],
  "message": "Regeneration complete"
}
```

---

## Teams

Base path: `/api/admin/sports`

### `GET /teams`

List teams with optional filters.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `league` | `string` | `null` | Filter by league code |
| `search` | `string` | `null` | Search by name/abbreviation |
| `limit` | `int` | `100` | Max results (up to 500) |
| `offset` | `int` | `0` | Pagination offset |

**Response:** `TeamListResponse`
```json
{
  "teams": [
    {
      "id": 1,
      "name": "Golden State Warriors",
      "shortName": "Warriors",
      "abbreviation": "GSW",
      "leagueCode": "NBA",
      "gamesCount": 82
    }
  ],
  "total": 30
}
```

---

### `GET /teams/{team_id}`

Get team detail with recent games.

**Response:** `TeamDetail`
```json
{
  "id": 1,
  "name": "Golden State Warriors",
  "shortName": "Warriors",
  "abbreviation": "GSW",
  "leagueCode": "NBA",
  "location": "San Francisco",
  "externalRef": "...",
  "xHandle": "warriors",
  "xProfileUrl": "https://x.com/warriors",
  "recentGames": [
    {
      "id": 123,
      "gameDate": "2026-01-15",
      "opponent": "Los Angeles Lakers",
      "isHome": true,
      "score": "112-108",
      "result": "W"
    }
  ]
}
```

---

### `GET /teams/{team_id}/social`

Get team's social media info.

**Response:** `TeamSocialInfo`
```json
{
  "teamId": 1,
  "abbreviation": "GSW",
  "xHandle": "warriors",
  "xProfileUrl": "https://x.com/warriors"
}
```

---

## Scraper Runs

Base path: `/api/admin/sports`

### `POST /scraper/runs`

Create and enqueue a new scrape job.

**Request Body:** `ScrapeRunCreateRequest`
```json
{
  "config": {
    "leagueCode": "NBA",
    "season": 2026,
    "seasonType": "regular",
    "startDate": "2026-01-01",
    "endDate": "2026-01-15",
    "boxscores": true,
    "odds": true,
    "social": false,
    "pbp": false,
    "teamStats": false,
    "playerStats": false,
    "onlyMissing": false,
    "updatedBefore": null,
    "books": ["fanduel", "draftkings"]
  },
  "requestedBy": "admin@example.com"
}
```

**Response:** `ScrapeRunResponse`

---

### `GET /scraper/runs`

List scrape runs with optional filters.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `league` | `string` | `null` | Filter by league code |
| `status` | `string` | `null` | Filter by status |
| `limit` | `int` | `50` | Max results (up to 200) |

**Response:** `ScrapeRunResponse[]`

---

### `GET /scraper/runs/{run_id}`

Get details of a specific scrape run.

---

### `POST /scraper/runs/{run_id}/cancel`

Cancel a pending or running scrape job.

**Status Codes:**
- `400` — Only pending/running jobs can be canceled
- `404` — Run not found

---

## Job Runs

Base path: `/api/admin/sports`

### `GET /jobs`

List job run history.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | `int` | `50` | Max results (1-200) |
| `phase` | `string` | `null` | Filter by phase (e.g., `snapshot`) |

**Response:** `JobRunResponse[]`
```json
[
  {
    "id": 1,
    "phase": "snapshot",
    "leagues": ["NBA", "NHL"],
    "status": "success",
    "started_at": "2026-01-15T02:00:00Z",
    "finished_at": "2026-01-15T02:00:05Z",
    "duration_seconds": 5.2,
    "error_summary": null,
    "created_at": "2026-01-15T02:00:00Z"
  }
]
```

---

## Diagnostics

Base path: `/api/admin/sports/diagnostics`

### `GET /missing-pbp`

List games with missing play-by-play data.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | `int` | `100` | Max results (1-500) |
| `league` | `string` | `null` | Filter by league code |

**Response:** `MissingPbpEntry[]`
```json
[
  {
    "game_id": 123,
    "league_code": "NBA",
    "status": "pending",
    "reason": "source_unavailable",
    "detected_at": "2026-01-15T02:00:00Z",
    "updated_at": "2026-01-15T02:00:00Z"
  }
]
```

---

### `GET /conflicts`

List unresolved game conflicts.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | `int` | `100` | Max results (1-500) |
| `league` | `string` | `null` | Filter by league code |

**Response:** `GameConflictEntry[]`
```json
[
  {
    "league_code": "NBA",
    "game_id": 123,
    "conflict_game_id": 124,
    "external_id": "ext-123",
    "source": "sports-reference",
    "conflict_fields": {"home_score": [108, 110]},
    "created_at": "2026-01-15T02:00:00Z",
    "resolved_at": null
  }
]
```

---

## Social

Base path: `/api/social`

### `GET /posts`

List social posts with filters.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `game_id` | `int` | `null` | Filter by game |
| `team_id` | `string` | `null` | Filter by team abbreviation |
| `start_date` | `datetime` | `null` | Filter by posted_at >= |
| `end_date` | `datetime` | `null` | Filter by posted_at <= |
| `limit` | `int` | `100` | Max results (1-500) |
| `offset` | `int` | `0` | Pagination offset |

**Response:** `SocialPostListResponse`

---

### `GET /posts/game/{game_id}`

Get all social posts for a specific game.

**Response:** `SocialPostListResponse`

---

### `POST /posts`

Create a new social post.

**Request Body:** `SocialPostCreateRequest`
```json
{
  "gameId": 123,
  "teamAbbreviation": "GSW",
  "postUrl": "https://x.com/...",
  "postedAt": "2026-01-15T02:30:00Z",
  "hasVideo": true,
  "videoUrl": "...",
  "imageUrl": null,
  "tweetText": "What a play!",
  "sourceHandle": "warriors",
  "mediaType": "video"
}
```

**Status Codes:**
- `201` — Created
- `404` — Game or team not found
- `409` — Post URL already exists

---

### `POST /posts/bulk`

Bulk create social posts (skips duplicates).

**Request Body:** `SocialPostBulkCreateRequest`
```json
{
  "posts": [SocialPostCreateRequest, ...]
}
```

---

### `DELETE /posts/{post_id}`

Delete a social post.

**Status Codes:**
- `204` — Deleted
- `404` — Post not found

---

### `GET /accounts`

List social account registry entries.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `league` | `string` | `null` | Filter by league code |
| `team_id` | `int` | `null` | Filter by team ID |
| `platform` | `string` | `null` | Filter by platform (e.g., `x`) |
| `limit` | `int` | `100` | Max results |
| `offset` | `int` | `0` | Pagination offset |

**Response:** `SocialAccountListResponse`

---

### `POST /accounts`

Create or update a social account registry entry.

**Request Body:** `SocialAccountUpsertRequest`
```json
{
  "teamId": 1,
  "platform": "x",
  "handle": "warriors",
  "isActive": true
}
```

---

## Reading Positions

Base path: `/api`

Track user reading positions for game timelines.

### `POST /api/users/{user_id}/games/{game_id}/reading-position`

Create or update a user's last-read position.

**Path Parameters:**
- `user_id` (string): User identifier
- `game_id` (int): Game ID

**Request Body:** `ReadingPositionRequest`
```json
{
  "moment": 42,
  "timestamp": 1705289400.0,
  "scrollHint": "Q3-5:30"
}
```

**Response:** `ReadingPositionResponse`

---

### `GET /api/users/{user_id}/games/{game_id}/resume`

Get the last-read position for a user/game pair.

**Response:** `ReadingPositionResponse`
```json
{
  "userId": "user-123",
  "gameId": 456,
  "moment": 42,
  "timestamp": 1705289400.0,
  "scrollHint": "Q3-5:30"
}
```

**Status Codes:**
- `404` — Reading position not found

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string (asyncpg driver) |
| `REDIS_URL` | Yes | Redis URL for Celery broker |

---

## Response Models

### GameSummary
```typescript
{
  id: number;
  league_code: string;
  game_date: datetime;
  home_team: string;
  away_team: string;
  home_score: number | null;
  away_score: number | null;
  has_boxscore: boolean;
  has_player_stats: boolean;
  has_odds: boolean;
  has_social: boolean;
  has_pbp: boolean;
  has_highlights: boolean;
  play_count: number;
  social_post_count: number;
  highlight_count: number;
  has_required_data: boolean;
  scrape_version: number | null;
  last_scraped_at: datetime | null;
  last_ingested_at: datetime | null;
  last_pbp_at: datetime | null;
  last_social_at: datetime | null;
}
```

### GameMeta
```typescript
{
  id: number;
  league_code: string;
  season: number;
  season_type: string | null;
  game_date: datetime;
  home_team: string;
  away_team: string;
  home_score: number | null;
  away_score: number | null;
  status: string;
  scrape_version: number | null;
  last_scraped_at: datetime | null;
  last_ingested_at: datetime | null;
  last_pbp_at: datetime | null;
  last_social_at: datetime | null;
  has_boxscore: boolean;
  has_player_stats: boolean;
  has_odds: boolean;
  has_social: boolean;
  has_pbp: boolean;
  has_highlights: boolean;
  play_count: number;
  social_post_count: number;
  highlight_count: number;
  home_team_x_handle: string | null;
  away_team_x_handle: string | null;
}
```

### TeamSnapshot
```typescript
{
  id: number;
  name: string;
  abbreviation: string | null;
}
```

### PlayEntry
```typescript
{
  play_index: number;
  quarter: number | null;
  game_clock: string | null;
  play_type: string | null;
  team_abbreviation: string | null;
  player_name: string | null;
  description: string | null;
  home_score: number | null;
  away_score: number | null;
}
```

### OddsEntry
```typescript
{
  book: string;
  market_type: string;
  side: string | null;
  line: number | null;
  price: number | null;
  is_closing_line: boolean;
  observed_at: datetime | null;
}
```

### ScrapeRunConfig
```typescript
{
  leagueCode: string;
  season: number | null;
  seasonType: string; // "regular" | "playoff"
  startDate: date | null;
  endDate: date | null;
  boxscores: boolean;
  odds: boolean;
  social: boolean;
  pbp: boolean;
  teamStats: boolean;
  playerStats: boolean;
  onlyMissing: boolean;
  updatedBefore: date | null;
  books: string[] | null;
}
```

### HighlightEntry (Grounded)
```typescript
{
  highlight_id: string;
  type: string; // "SCORING_RUN" | "LEAD_CHANGE" | "MOMENTUM_SHIFT" | "GAME_DECIDING_STRETCH" | "COMEBACK" | "STAR_TAKEOVER"
  title: string;
  description: string;
  start_play_id: string;
  end_play_id: string;
  key_play_ids: string[];
  involved_teams: string[];
  involved_players: PlayerContribution[];
  score_change: string; // "92–96 → 98–96"
  game_clock_range: string; // "Q4 7:42–5:58"
  game_phase: string; // "early" | "mid" | "late" | "closing"
  importance_score: number; // 0-1
}
```

### PlayerContribution
```typescript
{
  name: string; // Player name
  stats: { pts?: number; stl?: number; blk?: number; ast?: number };
  summary: string | null; // "6 pts, 1 stl"
}
```

---

## Consumers

This API serves:
- `scroll-down-app` (iOS)
- `scroll-down-sports-ui` (Web)

## Contract

This API implements `scroll-down-api-spec`. Schema changes require:
1. Update spec first
2. Then update implementation
3. Document breaking changes
