# X (Twitter) Integration

Social posts from official NBA team accounts, displayed as game highlights.

## How It Works

1. **Game day window**: 5:00 AM ET to 4:59 AM ET next day (24 hours)
2. **Playwright scraper** visits X search with date filters
3. **Spoiler filter** removes posts with scores/results
4. **Posts saved** with game_id, team_id, URL, timestamp

## Database Schema

```sql
-- Team X handles
ALTER TABLE sports_teams ADD COLUMN x_handle VARCHAR(50);

-- Social posts
CREATE TABLE game_social_posts (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES sports_games(id),
    team_id INTEGER NOT NULL REFERENCES sports_teams(id),
    post_url TEXT NOT NULL UNIQUE,
    posted_at TIMESTAMPTZ NOT NULL,
    has_video BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

## Running the Scraper

### Via Admin UI

1. Go to http://localhost:3000/admin/theory-bets/ingestion
2. Select date range and league
3. Check "Include social posts"
4. Click "Schedule Run"

### Via API

```bash
curl -X POST http://localhost:8000/api/admin/sports/scraper/runs \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "leagueCode": "NBA",
      "startDate": "2024-03-01",
      "endDate": "2024-03-15",
      "includeBoxscores": false,
      "includeOdds": false,
      "includeSocial": true
    }
  }'
```

## X Authentication

Historical search requires logged-in cookies:

### Getting Cookies (Safari)

1. Log into x.com in Safari
2. Open Develop → Show Web Inspector → Storage → Cookies
3. Copy values for `auth_token` and `ct0`
4. Add to `infra/.env`:

```bash
X_AUTH_TOKEN=your_auth_token_value
X_CT0=your_ct0_value
```

## Spoiler Filtering

Posts matching these patterns are excluded:

| Pattern | Examples |
|---------|----------|
| Score format | `112-108`, `W 112-108` |
| Final keywords | `final`, `game over`, `victory` |
| Recap content | `recap`, `post-game`, `highlights` |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/social/posts/game/{game_id}` | Posts for a game |
| GET | `/api/social/posts` | All posts with filters |
| GET | `/api/admin/sports/teams/{id}/social` | Team X handle |

## Backfill Example

```bash
# Backfill March 2024 NBA games
curl -X POST http://localhost:8000/api/admin/sports/scraper/runs \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "leagueCode": "NBA",
      "startDate": "2024-03-01",
      "endDate": "2024-03-31",
      "includeSocial": true,
      "backfillSocial": true
    }
  }'
```

Use `backfillSocial: true` to only scrape games without existing posts.

## Migrations

```bash
# Apply in order
psql "$DATABASE_URL" -f sql/001_game_social_posts.sql
psql "$DATABASE_URL" -f sql/002_team_x_handles.sql
psql "$DATABASE_URL" -f sql/003_seed_nba_x_handles.sql
```

## Rate Limiting

The scraper uses polite delays (5-9 seconds between requests) to avoid overwhelming X servers.
