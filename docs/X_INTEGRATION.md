# X (Twitter) Integration

Social posts from official team X accounts, displayed as game highlights.

## Architecture: Team-Centric Two-Phase Collection

Social collection uses a **team-centric** approach rather than game-centric:

### Phase 1: COLLECT
1. For each team with games in the date range, scrape all tweets
2. **Window**: 5:00 AM ET game day to 4:59 AM ET next day (24 hours)
3. **Playwright scraper** visits X search with date filters
4. **Content extraction**: Tweet text, images, video detection
5. **Posts saved** to `team_social_posts` with `mapping_status='unmapped'`

### Phase 2: MAP
1. Query unmapped tweets from `team_social_posts`
2. Match tweets to games based on team and posting time
3. Apply spoiler filtering
4. Copy mapped tweets to `game_social_posts`

### Why Team-Centric?
- Collect once, map to multiple games if needed
- More efficient rate limit usage
- Supports doubleheader scenarios
- Cleaner separation of concerns

## Database Schema

### Phase 1: Raw Collected Tweets

```sql
CREATE TABLE team_social_posts (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES sports_teams(id) ON DELETE CASCADE,
    platform VARCHAR(20) NOT NULL DEFAULT 'x',
    external_post_id VARCHAR(100),
    post_url TEXT NOT NULL,
    posted_at TIMESTAMPTZ NOT NULL,
    tweet_text TEXT,
    has_video BOOLEAN DEFAULT FALSE,
    video_url TEXT,
    image_url TEXT,
    source_handle VARCHAR(100),
    media_type VARCHAR(20),
    mapping_status VARCHAR(20) DEFAULT 'unmapped',  -- 'unmapped', 'mapped', 'no_game'
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(team_id, platform, external_post_id)
);
```

### Phase 2: Mapped Game Posts

```sql
CREATE TABLE game_social_posts (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES sports_games(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES sports_teams(id) ON DELETE CASCADE,
    tweet_url TEXT NOT NULL UNIQUE,
    posted_at TIMESTAMPTZ NOT NULL,
    has_video BOOLEAN DEFAULT FALSE,
    tweet_text TEXT,
    video_url TEXT,
    image_url TEXT,
    source_handle VARCHAR(100),
    media_type VARCHAR(20),  -- 'video', 'image', or 'none'
    reveal_risk BOOLEAN DEFAULT FALSE,
    reveal_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL
);
```

### Team Handles

```sql
-- Team X handles
ALTER TABLE sports_teams ADD COLUMN x_handle VARCHAR(50);
```

### Media Types

| `media_type` | Description | Rendering |
|--------------|-------------|-----------|
| `video` | Post contains video | Use Twitter embed widget |
| `image` | Post contains image | Display `image_url` directly |
| `none` | Text-only post | Display `tweet_text` |

## Running the Scraper

### Via Admin UI

1. Go to http://localhost:3000/admin/sports/ingestion
2. Select date range and league
3. Toggle "Social" on
4. Click "Start Run"

### Via API

```bash
curl -X POST http://localhost:8000/api/admin/sports/scraper/runs \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "league_code": "NBA",
      "start_date": "2024-03-01",
      "end_date": "2024-03-15",
      "boxscores": false,
      "odds": false,
      "social": true,
      "only_missing": true
    }
  }'
```

### Scraper Options

| Field | Description |
|-------|-------------|
| `social: true` | Enable social scraping |
| `only_missing: true` | Skip games that already have posts |
| `updated_before: "2026-01-01T00:00:00Z"` | Only scrape if last update before this date |

## X Authentication

Historical search requires logged-in cookies.

### Getting Cookies (Safari)

1. Log into x.com in Safari
2. Open Develop → Show Web Inspector → Storage → Cookies
3. Copy values for `auth_token` and `ct0`
4. Add to `infra/.env`:

```bash
X_AUTH_TOKEN=your_auth_token_value
X_CT0=your_ct0_value
```

### Cookie Expiration

Cookies expire periodically. If scraping returns empty results:

1. Log into x.com again in your browser
2. Copy fresh cookie values
3. Update `.env` and restart the scraper container

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
| GET | `/api/admin/sports/games/{id}` | Includes `social_posts` array |

### Social Post Response

```json
{
  "id": 123,
  "game_id": 456,
  "team_abbreviation": "LAL",
  "post_url": "https://x.com/Lakers/status/...",
  "posted_at": "2024-03-01T19:30:00Z",
  "tweet_text": "Let's go Lakers! 💜💛",
  "image_url": "https://pbs.twimg.com/...",
  "video_url": null,
  "media_type": "image",
  "source_handle": "Lakers",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

## Downstream Rendering

For downstream apps consuming social posts:

| `media_type` | Recommended Rendering |
|--------------|----------------------|
| `video` | Use Twitter's embed widget (video URLs are protected) |
| `image` | Display `image_url` directly with `<img>` |
| `none` | Display `tweet_text` with link to original post |

See [ARCHITECTURE.md](ARCHITECTURE.md) for a high-level view of how social posts fit into the platform.

## Rate Limiting

The scraper uses polite delays (5-9 seconds between requests) to avoid overwhelming X servers.
