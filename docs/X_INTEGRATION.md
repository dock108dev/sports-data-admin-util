# X (Twitter) Integration

This document describes the X (formerly Twitter) integration for displaying game timeline posts in Scroll Down Sports.

## Overview

The integration allows embedding official NBA team posts from X as game highlights. Posts are collected from team accounts and displayed in chronological order during game playback, with spoiler content filtered out.

### Architecture

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  scroll-down-       │     │  sports-data-admin  │     │   X (Twitter)       │
│  sports-ui          │────▶│  API + Scraper      │◀────│   Team Accounts     │
│                     │     │                     │     │                     │
│  - Timeline display │     │  - Post storage     │     │  @warriors          │
│  - Embed rendering  │     │  - Spoiler filter   │     │  @Lakers            │
│  - Scraper triggers │     │  - Game windows     │     │  @celtics           │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                     │
                                     ▼
                            ┌─────────────────────┐
                            │  PostgreSQL         │
                            │                     │
                            │  - game_social_posts│
                            │  - sports_teams     │
                            │    (x_handle)       │
                            └─────────────────────┘
```

## Database Schema

### `game_social_posts` Table

Stores social posts linked to games:

```sql
CREATE TABLE game_social_posts (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES sports_games(id),
    team_id INTEGER NOT NULL REFERENCES sports_teams(id),
    tweet_url TEXT NOT NULL UNIQUE,  -- Post URL (column named for backwards compat)
    posted_at TIMESTAMPTZ NOT NULL,
    has_video BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### `sports_teams.x_handle` Column

Each team has an optional X handle:

```sql
ALTER TABLE sports_teams ADD COLUMN x_handle VARCHAR(50);
```

## Running the X Scraper

### Via Admin UI (Frontend Integration)

The X scraper integrates with the existing scraper infrastructure and can be triggered from the admin UI:

```typescript
// Example: Trigger social scraping for NBA games
const response = await fetch('/api/admin/sports/scraper/runs', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    config: {
      leagueCode: 'NBA',
      scraperType: 'social',  // or 'all' for everything
      startDate: '2024-03-01',
      endDate: '2024-03-15',
      includeBoxscores: false,
      includeOdds: false,
      includeSocial: true,
      // Social-specific options:
      socialPreGameHours: 2,
      socialPostGameHours: 1,
    },
    requestedBy: 'admin@example.com',
  }),
});
```

### Scraper Configuration Options

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `includeSocial` | boolean | false | Scrape X posts for games in date range |
| `backfillSocial` | boolean | false | Only scrape games missing posts |
| `socialPreGameHours` | int | 2 | Hours before game to start window |
| `socialPostGameHours` | int | 1 | Hours after game to end window |

### Scraper Types

| Type | Boxscores | Odds | Social |
|------|-----------|------|--------|
| `boxscore` | ✓ | ✗ | ✗ |
| `odds` | ✗ | ✓ | ✗ |
| `boxscore_and_odds` | ✓ | ✓ | ✗ |
| `social` | ✗ | ✗ | ✓ |
| `all` | ✓ | ✓ | ✓ |

### Running Independently

To run social scraping independently:

```bash
# Via Celery (production)
celery -A bets_scraper.celery_app call run_scrape_job \
  --args='[1, {"scraper_type": "social", "league_code": "NBA", "start_date": "2024-03-01", "end_date": "2024-03-15", "include_social": true}]'
```

### Running with Other Scrapers

Set `includeSocial: true` alongside other options:

```json
{
  "config": {
    "leagueCode": "NBA",
    "scraperType": "all",
    "startDate": "2024-03-01",
    "endDate": "2024-03-15",
    "includeBoxscores": true,
    "includeOdds": true,
    "includeSocial": true,
    "socialPostGameHours": 1
  }
}
```

## API Endpoints

### Social Posts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/social/posts` | List posts with filters |
| GET | `/api/social/posts/game/{game_id}` | Get posts for a game timeline |
| POST | `/api/social/posts` | Create a single post |
| POST | `/api/social/posts/bulk` | Bulk create posts |
| DELETE | `/api/social/posts/{post_id}` | Delete a post |

### Team Social Info

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/sports/teams/{team_id}/social` | Get team X handle |
| GET | `/api/admin/sports/games/{game_id}` | Includes team X handles |

### Scraper Runs

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/admin/sports/scraper/runs` | Create new scrape run |
| GET | `/api/admin/sports/scraper/runs` | List scrape runs |
| GET | `/api/admin/sports/scraper/runs/{id}` | Get run status |
| POST | `/api/admin/sports/scraper/runs/{id}/cancel` | Cancel running job |

## Frontend Integration (scroll-down-sports-ui)

### 1. Consuming Posts API

```typescript
// src/adapters/SportsApiAdapter.ts

interface SocialPost {
  id: number;
  game_id: number;
  team_id: string;
  post_url: string;
  posted_at: string;
  has_video: boolean;
}

async function getPostsForGame(gameId: number): Promise<SocialPost[]> {
  const response = await fetch(
    `${API_BASE}/api/social/posts/game/${gameId}`
  );
  const data = await response.json();
  return data.posts;
}
```

### 2. Timeline Component

```tsx
// src/components/GameTimeline.tsx

const GameTimeline = ({ gameId }: { gameId: number }) => {
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPostsForGame(gameId)
      .then(setPosts)
      .finally(() => setLoading(false));
  }, [gameId]);

  if (loading) return <TimelineSkeleton />;
  if (!posts.length) return <NoPostsMessage />;

  return (
    <div className="timeline">
      {posts.map((post) => (
        <TweetEmbed
          key={post.id}
          tweetUrl={post.post_url}
          hasVideo={post.has_video}
        />
      ))}
    </div>
  );
};
```

### 3. Admin Scraper Controls

Add UI controls to trigger social scraping:

```tsx
// src/components/admin/SocialScraperForm.tsx

const SocialScraperForm = () => {
  const [config, setConfig] = useState({
    leagueCode: 'NBA',
    startDate: '',
    endDate: '',
    socialPreGameHours: 2,
    socialPostGameHours: 3,
  });

  const handleSubmit = async () => {
    await fetch('/api/admin/sports/scraper/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        config: {
          ...config,
          scraperType: 'social',
          includeSocial: true,
          includeBoxscores: false,
          includeOdds: false,
        },
      }),
    });
  };

  return (
    <form onSubmit={handleSubmit}>
      <h3>Social Post Scraper</h3>
      <select
        value={config.leagueCode}
        onChange={(e) => setConfig({ ...config, leagueCode: e.target.value })}
      >
        <option value="NBA">NBA</option>
        <option value="NCAAB">NCAAB</option>
      </select>
      <input
        type="date"
        value={config.startDate}
        onChange={(e) => setConfig({ ...config, startDate: e.target.value })}
      />
      <input
        type="date"
        value={config.endDate}
        onChange={(e) => setConfig({ ...config, endDate: e.target.value })}
      />
      <label>
        Pre-game hours:
        <input
          type="number"
          value={config.socialPreGameHours}
          onChange={(e) => setConfig({ ...config, socialPreGameHours: +e.target.value })}
        />
      </label>
      <label>
        Post-game hours:
        <input
          type="number"
          value={config.socialPostGameHours}
          onChange={(e) => setConfig({ ...config, socialPostGameHours: +e.target.value })}
        />
      </label>
      <button type="submit">Start Social Scrape</button>
    </form>
  );
};
```

### 4. Caption masking (spoiler-safe)

Wrap embeds with a masking container so captions stay hidden until user intent:

```css
.tweet-mask {
  position: relative;
}
.tweet-mask__overlay {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 96px; /* adjust to caption height */
  background: linear-gradient(to top, #fff, rgba(255,255,255,0));
  pointer-events: none;
  transition: opacity 160ms ease;
}
.tweet-mask--revealed .tweet-mask__overlay {
  opacity: 0;
}
```

```tsx
<div className={`tweet-mask ${revealed ? "tweet-mask--revealed" : ""}`}>
  <blockquote className="twitter-tweet">
    <a href={post.post_url}></a>
  </blockquote>
  <div className="tweet-mask__overlay" />
</div>
```

Trigger `revealed` with your existing scroll-to-reveal or explicit click logic.

## Spoiler Filtering

Posts containing game results are filtered out to preserve the spoiler-free experience.

### Filtered Patterns

1. **Score patterns**: `112-108`, `W 112-108`, `Final: 112-108`
2. **Final keywords**: `final`, `game over`, `we win`, `victory`
3. **Recap content**: `recap`, `post-game`, `full highlights`

### Usage (API)

```python
from app.utils.spoiler_filter import contains_spoiler, check_for_spoilers

# Quick check
if contains_spoiler("Final score: 112-108"):
    print("This post contains spoilers")

# Detailed check
result = check_for_spoilers("We win! 🎉")
if result.is_spoiler:
    print(f"Spoiler detected: {result.reason}")
```

## Game Window

Posts are collected within a time window around each game:

- **Pre-game**: 2 hours before tip-off (configurable)
- **Post-game**: 3 hours after tip-off (configurable)

### Configuration

Via scraper config:
```json
{
  "socialPreGameHours": 2,
  "socialPostGameHours": 3
}
```

## X API Integration

The scraper supports pluggable collection strategies:

### Mock Collector (Default)
For testing without X API access. Returns empty results.

### X API Collector
Requires `X_BEARER_TOKEN` environment variable.

```bash
# Add to .env
X_BEARER_TOKEN=your_bearer_token_here
```

### Implementing Custom Collector

```python
from bets_scraper.social import XCollectorStrategy, CollectedPost

class CustomXCollector(XCollectorStrategy):
    def collect_posts(
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CollectedPost]:
        # Your implementation here
        posts = []
        # ... fetch from X API or headless browser
        return posts
```

## Running Migrations

Apply the migrations in order:

```bash
# Add x_handle column
psql "$DATABASE_URL" -f sql/002_team_x_handles.sql

# Seed NBA team handles
psql "$DATABASE_URL" -f sql/003_seed_nba_x_handles.sql

# Create game_social_posts table (if not already done)
psql "$DATABASE_URL" -f sql/001_game_social_posts.sql
```

## NBA Team X Handles

All 30 NBA teams have official X handles configured. See `sql/003_seed_nba_x_handles.sql` for the full list.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis for Celery task queue |
| `X_BEARER_TOKEN` | No | X API v2 bearer token |

## Testing

### Verify API

```bash
# Check posts for a game
curl http://localhost:8000/api/social/posts/game/1984

# Check team X handle
curl http://localhost:8000/api/admin/sports/teams/1/social

# Trigger social scrape
curl -X POST http://localhost:8000/api/admin/sports/scraper/runs \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "leagueCode": "NBA",
      "scraperType": "social",
      "startDate": "2024-03-01",
      "endDate": "2024-03-01",
      "includeSocial": true
    }
  }'
```

## Future Improvements

1. **X API Integration**: Implement XApiCollector with actual X API v2 calls
2. **Headless Browser**: Add Playwright-based collector as fallback
3. **AI Spoiler Detection**: Use NLP for better spoiler filtering
4. **Post Prioritization**: Rank posts by engagement/relevance
5. **Multi-league Support**: Add NCAAB, NFL team handles
6. **Real-time Collection**: Collect posts during live games

## Runbook: Backfill 2023 & 2024 NBA posts

1) Ensure the stack is running (`docker-compose up -d api scraper postgres redis`).
2) Make sure `sports_teams.x_handle` is populated (run `sql/003_seed_nba_x_handles.sql` if needed).
3) Trigger social-only scrape runs via API (recommended per-month chunks):

```bash
# Example: March 2024
curl -X POST http://localhost:8000/api/admin/sports/scraper/runs \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "leagueCode": "NBA",
      "scraperType": "social",
      "startDate": "2024-03-01",
      "endDate": "2024-03-31",
      "includeSocial": true,
      "socialPreGameHours": 2,
      "socialPostGameHours": 1
    }
  }'
```

Suggested backfill windows:
- 2023-10-01 to 2023-12-31 (split monthly)
- 2024-01-01 to 2024-06-30 (split monthly)

4) Monitor progress:
```bash
curl http://localhost:8000/api/admin/sports/scraper/runs
```

5) Validate data:
```bash
curl http://localhost:8000/api/social/posts/game/1984
```
