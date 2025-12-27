# sports-data-admin

Standalone sports data platform with scraping, API, and admin UI for NBA, NCAAB, NFL, NHL, MLB, and NCAAF.

## Stack

| Component | Technology | Port |
|-----------|------------|------|
| **API** | FastAPI + SQLAlchemy | 8000 |
| **Scraper** | Celery + Playwright | — |
| **Web UI** | Next.js | 3000 |
| **Database** | PostgreSQL 16 | 5432 |
| **Queue** | Redis | 6379 |

## Quick Start (Docker)

```bash
cd infra
cp .env.example .env   # Edit credentials as needed

# Start everything
docker compose up -d --build

# First run: apply schema
docker exec -i sports-postgres psql -U dock108 -d dock108 < ../sql/000_sports_schema.sql
docker exec -i sports-postgres psql -U dock108 -d dock108 < ../sql/001_game_social_posts.sql
docker exec -i sports-postgres psql -U dock108 -d dock108 < ../sql/002_team_x_handles.sql
docker exec -i sports-postgres psql -U dock108 -d dock108 < ../sql/003_seed_nba_x_handles.sql
```

**URLs:**
- Admin UI: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/healthz

## Quick Start (Local Development)

```bash
# 1. Database schema
psql "$DATABASE_URL" -f sql/000_sports_schema.sql

# 2. API
cd api
pip install -r requirements.txt
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/sports"
export REDIS_URL="redis://localhost:6379/2"
uvicorn main:app --reload --port 8000

# 3. Scraper (new terminal)
cd scraper
uv pip install --system -e .
celery -A bets_scraper.celery_app.app worker --loglevel=info --queues=bets-scraper

# 4. Web UI (new terminal)
cd web
pnpm install
NEXT_PUBLIC_SPORTS_API_URL=http://localhost:8000 pnpm dev
```

## Project Structure

```
sports-data-admin/
├── api/                 # FastAPI service
│   ├── app/
│   │   ├── routers/     # API endpoints
│   │   ├── db_models.py # SQLAlchemy ORM models
│   │   └── db.py        # Database connection
│   └── main.py
├── scraper/             # Celery workers
│   └── bets_scraper/
│       ├── scrapers/    # Sport-specific scrapers
│       ├── social/      # X/Twitter scraper
│       ├── odds/        # Odds API client
│       └── services/    # Run manager
├── web/                 # Next.js admin UI
│   └── src/
│       ├── app/admin/   # Admin pages
│       ├── components/  # React components
│       └── lib/api/     # API client
├── sql/                 # Database schema & migrations
├── infra/               # Docker configuration
└── docs/                # Additional documentation
```

## Features

### Data Collection
- **Boxscores**: Team and player stats from Sports Reference
- **Odds**: Spreads, totals, moneylines from The Odds API
- **Social**: Team X/Twitter posts (24-hour game day window)

### Admin UI
- **Data Browser**: Filter and view games, teams, scrape runs
- **Ingestion**: Schedule scrape jobs with date ranges
- **Game Detail**: View boxscores, player stats, odds, social posts

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection (async: `postgresql+asyncpg://`) |
| `REDIS_URL` | Yes | Redis for Celery queue |
| `ODDS_API_KEY` | No | The Odds API key for live odds |
| `X_AUTH_TOKEN` | No | X auth cookie for social scraping |
| `X_CT0` | No | X csrf cookie for social scraping |
| `NEXT_PUBLIC_SPORTS_API_URL` | Yes (web) | API base URL for frontend |

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

## Docker Commands

```bash
# Start all services
docker compose up -d --build

# View logs
docker compose logs -f api
docker compose logs -f scraper

# Rebuild single service
docker compose up -d --build api

# Stop everything
docker compose down
```

## Additional Documentation

- [Database Integration Guide](docs/DATABASE_INTEGRATION.md) — SQL queries, Python integration, pandas
- [X Integration Details](docs/X_INTEGRATION.md) — Social scraper internals

## License

Private — Dock108
