# Platform Overview

Sports Data Admin is the central data platform for Scroll Down Sports. It ingests, normalizes, and serves sports data to downstream consumer apps.

## Data Collection

| Data Type | Source | Description |
|-----------|--------|-------------|
| **Boxscores** | Sports Reference | Team and player stats |
| **Odds** | The Odds API | Spreads, totals, moneylines |
| **Social** | X/Twitter | Team posts within game day window |
| **Play-by-Play** | Sports Reference | Quarter-by-quarter game events |

## Admin UI Features

| Feature | Description |
|---------|-------------|
| **Data Browser** | Filter and view games, teams, scrape runs |
| **Ingestion** | Schedule scrape jobs with date ranges and data type toggles |
| **Game Detail** | View boxscores, player stats, odds, social posts, PBP |
| **Compact Moments** | Review AI-generated game moment summaries |

## API Endpoints

### Admin Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/sports/games` | List games with filters |
| GET | `/api/admin/sports/games/{id}` | Game detail with all data |
| GET | `/api/admin/sports/games/{id}/moments` | All moments (full timeline coverage) |
| GET | `/api/admin/sports/games/{id}/highlights` | Notable moments only |
| GET | `/api/admin/sports/teams` | List teams |
| POST | `/api/admin/sports/scraper/runs` | Create scrape job |
| GET | `/api/admin/sports/scraper/runs` | List scrape runs |
| GET | `/api/admin/sports/timelines/missing` | Games missing timeline artifacts |
| POST | `/api/admin/sports/timelines/generate/{id}` | Generate timeline for a game |
| POST | `/api/admin/sports/timelines/regenerate-batch` | Regenerate timelines in batch |

### Reading Position Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/reading-positions/{user_id}/{game_id}` | Get saved position |
| PUT | `/api/reading-positions/{user_id}/{game_id}` | Save position |
| DELETE | `/api/reading-positions/{user_id}/{game_id}` | Delete position |
| GET | `/api/reading-positions/{user_id}` | List all positions for user |

### Utility Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/healthz` | Health check |
| GET | `/docs` | OpenAPI documentation |

### Query Parameters (Games List)

```
GET /api/admin/sports/games?league=NBA&season=2024&missingOdds=true&limit=50
```

| Param | Type | Description |
|-------|------|-------------|
| `league` | string[] | Filter by league code (NBA, NFL, etc.) |
| `season` | int | Season year |
| `team` | string | Search team name |
| `startDate` / `endDate` | date | Date range filter |
| `missingBoxscore` | bool | Games without boxscores |
| `missingPlayerStats` | bool | Games without player stats |
| `missingOdds` | bool | Games without odds |
| `missingSocial` | bool | Games without social posts |

## Database Schema

| Table | Description |
|-------|-------------|
| `sports_leagues` | League definitions (NBA, NFL, NCAAB, etc.) |
| `sports_teams` | Teams with names, abbreviations, X handles |
| `sports_games` | Games with scores, dates, status |
| `sports_team_boxscores` | Team stats (JSONB) |
| `sports_player_boxscores` | Player stats (JSONB) |
| `sports_game_odds` | Odds from various books |
| `sports_game_plays` | Play-by-play events |
| `game_social_posts` | X/Twitter posts per game |
| `game_reading_positions` | User reading positions |
| `compact_mode_thresholds` | Per-sport threshold configs |
| `sports_scrape_runs` | Scrape job audit log |

## Social Scraping

Posts are collected from official team X accounts within a 24-hour window:

- **Start**: 5:00 AM ET on game day
- **End**: 4:59 AM ET the next day

Spoiler content (scores, "final", "we win") is filtered out automatically.

### X Authentication

To scrape historical posts, add cookies from a logged-in X session:

```bash
# Get from browser dev tools → Application → Cookies → x.com
X_AUTH_TOKEN=your_auth_token_here
X_CT0=your_ct0_token_here
```

## Moments & Highlights

The platform partitions each game timeline into contiguous, non-overlapping **moments**:

| Moment Type | Description |
|-------------|-------------|
| NEUTRAL | Normal play, no significant pattern |
| RUN | Scoring run (8+ consecutive points by one team) |
| LEAD_BATTLE | Multiple lead changes in a short stretch |
| CLOSING_STRETCH | Final 2 minutes of close game |

**Highlights** are moments where `is_notable=True`. Each moment includes:
- Play IDs (start, end, all plays in range)
- Teams and players involved
- Player stats within the moment (pts, ast, blk, stl)
- Score before/after
- Game clock range

Moments are generated post-scrape and stored in `sports_game_timeline_artifacts`.
