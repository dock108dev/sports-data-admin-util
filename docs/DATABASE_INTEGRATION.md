# Database Integration Guide

How to connect to and query the sports database from external services.

## Connection

```python
# Async (FastAPI, asyncio)
DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/sports"

# Sync (scripts, pandas, Celery)
DATABASE_URL = "postgresql+psycopg://user:pass@host:5432/sports"
```

## Schema Overview

| Table | Description |
|-------|-------------|
| `sports_leagues` | League definitions (NBA, NFL, NCAAB, etc.) |
| `sports_teams` | Teams with names, abbreviations, X handles |
| `sports_games` | Games with scores, dates, status |
| `sports_team_boxscores` | Team stats as JSONB |
| `sports_player_boxscores` | Player stats as JSONB |
| `sports_game_odds` | Spreads, totals, moneylines |
| `game_social_posts` | X/Twitter posts per game |

## Python Examples

### Direct SQL

```python
from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://user:pass@host:5432/sports")

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT g.game_date, ht.name as home, at.name as away, g.home_score, g.away_score
        FROM sports_games g
        JOIN sports_teams ht ON g.home_team_id = ht.id
        JOIN sports_teams at ON g.away_team_id = at.id
        JOIN sports_leagues l ON g.league_id = l.id
        WHERE l.code = 'NBA' AND g.season = 2024
        ORDER BY g.game_date DESC
        LIMIT 10
    """))
    for row in result:
        print(row)
```

### Pandas

```python
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine("postgresql+psycopg://user:pass@host:5432/sports")

df = pd.read_sql("""
    SELECT g.game_date, l.code as league, g.home_score, g.away_score,
           tb.raw_stats_json->>'pts' as home_pts
    FROM sports_games g
    JOIN sports_leagues l ON g.league_id = l.id
    LEFT JOIN sports_team_boxscores tb ON tb.game_id = g.id AND tb.is_home = true
    WHERE l.code = 'NBA' AND g.status = 'completed'
""", engine)

# Expand JSONB stats
stats_df = df['home_pts'].apply(pd.Series)
```

### ORM Models

```python
import sys
sys.path.insert(0, "/path/to/sports-data-admin/api")

from app.db_models import SportsGame, SportsTeam, SportsLeague
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

engine = create_engine("postgresql+psycopg://user:pass@host:5432/sports")
Session = sessionmaker(bind=engine)

with Session() as session:
    games = session.execute(
        select(SportsGame)
        .join(SportsLeague)
        .where(SportsLeague.code == "NCAAB")
        .limit(20)
    ).scalars().all()
```

## Common Queries

### Games with Complete Data

```sql
SELECT g.*, l.code as league
FROM sports_games g
JOIN sports_leagues l ON g.league_id = l.id
WHERE EXISTS (SELECT 1 FROM sports_team_boxscores WHERE game_id = g.id)
  AND EXISTS (SELECT 1 FROM sports_game_odds WHERE game_id = g.id)
  AND g.status = 'completed';
```

### Team Stats

```sql
SELECT t.name, tb.is_home,
       tb.raw_stats_json->>'pts' as points,
       tb.raw_stats_json->>'fg_pct' as fg_pct,
       tb.raw_stats_json->>'trb' as rebounds
FROM sports_team_boxscores tb
JOIN sports_teams t ON tb.team_id = t.id
JOIN sports_games g ON tb.game_id = g.id
WHERE g.id = 1234;
```

### Closing Lines

```sql
SELECT g.game_date, ht.name as home, at.name as away,
       MAX(CASE WHEN o.market_type = 'spread' AND o.side = 'home' THEN o.line END) as spread,
       MAX(CASE WHEN o.market_type = 'total' AND o.side = 'over' THEN o.line END) as total
FROM sports_games g
JOIN sports_teams ht ON g.home_team_id = ht.id
JOIN sports_teams at ON g.away_team_id = at.id
JOIN sports_game_odds o ON o.game_id = g.id
WHERE o.is_closing_line = true AND g.season = 2024
GROUP BY g.id, g.game_date, ht.name, at.name;
```

### Data Coverage

```sql
SELECT l.code, g.season, COUNT(*) as games,
       COUNT(DISTINCT tb.game_id) as with_boxscores,
       COUNT(DISTINCT o.game_id) as with_odds,
       COUNT(DISTINCT sp.game_id) as with_social
FROM sports_games g
JOIN sports_leagues l ON g.league_id = l.id
LEFT JOIN sports_team_boxscores tb ON tb.game_id = g.id
LEFT JOIN sports_game_odds o ON o.game_id = g.id
LEFT JOIN game_social_posts sp ON sp.game_id = g.id
GROUP BY l.code, g.season
ORDER BY l.code, g.season DESC;
```

## REST API

For frontend/external service integration, use the REST API:

```typescript
const API_BASE = "http://localhost:8000";

// List games
const games = await fetch(`${API_BASE}/api/admin/sports/games?league=NBA&season=2024`);

// Game detail
const detail = await fetch(`${API_BASE}/api/admin/sports/games/1234`);

// Social posts
const posts = await fetch(`${API_BASE}/api/social/posts/game/1234`);
```

## Dependencies

```txt
# Sync access
sqlalchemy>=2.0.0
psycopg[binary]>=3.2.0

# Async access
sqlalchemy>=2.0.0
asyncpg>=0.29.0

# Analytics
pandas>=2.0.0
```

## Read-Only User

```sql
CREATE USER sports_readonly WITH PASSWORD 'password';
GRANT CONNECT ON DATABASE sports TO sports_readonly;
GRANT USAGE ON SCHEMA public TO sports_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sports_readonly;
```
