# Platform Overview

Sports Data Admin is the **internal data infrastructure** for Scroll Down Sports. It is not user-facing—it serves downstream apps (iOS, Web) via a REST API.

---

## Features

### Data Collection
- **Boxscores**: Team and player stats from Sports Reference
- **Odds**: Spreads, totals, moneylines from The Odds API
- **Social**: Team X/Twitter posts (24-hour game day window)

### Admin UI
- **Data Browser**: Filter and view games, teams, scrape runs
- **Ingestion**: Schedule scrape jobs with date ranges
- **Game Detail**: View boxscores, player stats, odds, social posts

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/sports/games` | List games with filters |
| GET | `/api/admin/sports/games/{id}` | Game detail with stats |
| GET | `/api/admin/sports/teams` | List teams |
| POST | `/api/admin/sports/scraper/runs` | Create scrape job |
| GET | `/api/admin/sports/scraper/runs` | List scrape runs |
| GET | `/api/social/posts/game/{id}` | Social posts for game |
| GET | `/healthz` | Health check |

### Query Parameters

```
GET /api/admin/sports/games?league=NBA&league=NCAAB&season=2024&missingOdds=true&limit=50
```

| Param | Type | Description |
|-------|------|-------------|
| `league` | string[] | Filter by league code |
| `season` | int | Season year |
| `team` | string | Search team name |
| `startDate` / `endDate` | date | Date range |
| `missingBoxscore` | bool | Games without boxscores |
| `missingPlayerStats` | bool | Games without player stats |
| `missingOdds` | bool | Games without odds |
| `missingSocial` | bool | Games without social posts |

## Database Schema

| Table | Description |
|-------|-------------|
| `sports_leagues` | League definitions (NBA, NFL, etc.) |
| `sports_teams` | Teams with X handles |
| `sports_games` | Games with scores and metadata |
| `sports_team_boxscores` | Team stats (JSONB) |
| `sports_player_boxscores` | Player stats (JSONB) |
| `sports_game_odds` | Odds from various books |
| `game_social_posts` | X/Twitter posts per game |
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
