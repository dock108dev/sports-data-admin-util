# X (Twitter) Integration

Social posts from official team X accounts, displayed as game highlights in downstream apps.

---

## Overview

The social scraper collects posts from official team accounts during a 24-hour game-day window. Posts are filtered to exclude spoilers (scores, results) and stored with rich metadata for flexible rendering downstream.

---

## How It Works

1. **Game day window**: 5:00 AM ET on game day → 4:59 AM ET next day (24 hours)
2. **Playwright scraper** visits X search with date filters and team handle
3. **Media extraction**: Tweet text, images, and video URLs are captured
4. **Spoiler filter** removes posts containing scores or result keywords
5. **Posts saved** with game_id, team_id, URL, timestamp, and media metadata

---

## Database Schema

```sql
CREATE TABLE game_social_posts (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES sports_games(id),
    team_id INTEGER NOT NULL REFERENCES sports_teams(id),
    post_url TEXT NOT NULL UNIQUE,
    posted_at TIMESTAMPTZ NOT NULL,
    
    -- Media fields
    tweet_text TEXT,
    image_url TEXT,
    video_url TEXT,
    source_handle VARCHAR(100),
    media_type VARCHAR(20),  -- 'video', 'image', 'text'
    has_video BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Team X handles
ALTER TABLE sports_teams ADD COLUMN x_handle VARCHAR(50);
```

### Media Type Values

| Value | Description |
|-------|-------------|
| `video` | Post contains video content |
| `image` | Post contains image(s) |
| `text` | Text-only post |

---

## Running the Scraper

### Via Admin UI

1. Go to http://localhost:3000/admin/theory-bets/ingestion
2. Select date range and league
3. Enable the "Social" toggle
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
      "social": true,
      "boxscores": false,
      "odds": false,
      "pbp": false
    }
  }'
```

### Rescrape Stale Data

Use the `updatedBefore` filter to rescrape posts older than a specific date:

```bash
curl -X POST http://localhost:8000/api/admin/sports/scraper/runs \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "leagueCode": "NBA",
      "startDate": "2024-03-01",
      "endDate": "2024-03-31",
      "social": true,
      "updatedBefore": "2026-01-01"
    }
  }'
```

---

## X Authentication

Historical search requires logged-in cookies from a browser session.

### Getting Cookies (Safari)

1. Log into x.com in Safari
2. Open Develop → Show Web Inspector → Storage → Cookies
3. Copy values for `auth_token` and `ct0`
4. Add to `infra/.env`:

```bash
X_AUTH_TOKEN=your_auth_token_value
X_CT0=your_ct0_value
```

### Getting Cookies (Chrome)

1. Log into x.com
2. Open DevTools → Application → Cookies → x.com
3. Copy `auth_token` and `ct0` values
4. Add to `infra/.env`

---

## Spoiler Filtering

Posts matching these patterns are excluded:

| Pattern | Examples |
|---------|----------|
| Score format | `112-108`, `W 112-108`, `L 99-101` |
| Final keywords | `final`, `game over`, `victory`, `defeat` |
| Recap content | `recap`, `post-game`, `highlights`, `we win` |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/social/posts/game/{game_id}` | Posts for a specific game |
| GET | `/api/social/posts` | All posts with filters |
| GET | `/api/admin/sports/teams/{id}/social` | Team X handle info |

### Response Shape

```json
{
  "id": 123,
  "game_id": 456,
  "team_id": 789,
  "post_url": "https://x.com/Lakers/status/1234567890",
  "posted_at": "2024-03-15T19:30:00Z",
  "tweet_text": "Let's go Lakers! 💜💛",
  "image_url": "https://pbs.twimg.com/media/...",
  "video_url": null,
  "source_handle": "Lakers",
  "media_type": "image",
  "has_video": false,
  "created_at": "2024-03-15T20:00:00Z",
  "updated_at": "2024-03-15T20:00:00Z"
}
```

---

## Downstream Rendering

Downstream apps should render posts based on `media_type`:

| media_type | Recommended Rendering |
|------------|----------------------|
| `video` | Twitter embed widget (for native playback) |
| `image` | Custom card with `image_url` + `tweet_text` |
| `text` | Custom card with `tweet_text` only |

All post types should include a "View on X →" link to `post_url`.

---

## Rate Limiting

The scraper uses polite delays (5-9 seconds between requests) to avoid overwhelming X servers. Scraping large date ranges may take significant time.

---

## Migrations

Social post schema is managed by Alembic. Run migrations via:

```bash
cd api
alembic upgrade head
```

For fresh databases, the schema is created automatically on first migration run.
