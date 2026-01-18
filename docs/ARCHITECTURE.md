# System Architecture

## Overview

Sports Data Admin is a data platform that ingests, normalizes, and serves sports data. It consists of three main components:

```
┌─────────────┐      ┌─────────────┐      ┌──────────────┐
│   Scraper   │─────▶│  PostgreSQL │◀─────│   FastAPI    │
│  (Python)   │      │  Database   │      │     API      │
└─────────────┘      └─────────────┘      └──────────────┘
                            │                      │
                            │                      ▼
                            │              ┌──────────────┐
                            └─────────────▶│  Admin Web   │
                                           │   (React)    │
                                           └──────────────┘
```

## Components

### 1. Scraper (`scraper/`)

Python service that collects sports data from external sources:

**Data Sources:**
- **Boxscores & PBP**: Sports Reference (basketball-reference.com, hockey-reference.com)
- **Live PBP**: NBA CDN, NHL Stats API
- **Odds**: The Odds API
- **Social**: X/Twitter (via Playwright)

**Execution:**
- Celery worker processes scrape jobs
- Celery Beat scheduler runs automatic ingestion (13:00-02:00 UTC, every 15 min)
- Manual jobs triggered via Admin UI

**Key Modules:**
- `scrapers/` - Sport-specific scrapers (NBA, NHL, NCAAB)
- `live/` - Live feed clients
- `odds/` - Odds API integration
- `social/` - X/Twitter collector (Playwright-based)
- `persistence/` - Database write operations
- `normalization/` - Team name normalization

### 2. API (`api/`)

FastAPI backend that serves normalized data:

**Endpoints:**
- `/api/admin/sports/*` - Admin operations (games, teams, scraper runs)
- `/api/games/*` - App snapshot endpoints (timeline, social, PBP)
- `/api/reading-positions/*` - User reading position tracking
- `/healthz` - Health check

**Key Services:**
- `services/timeline_generator.py` - Generates timeline artifacts from PBP + social
- `services/moments.py` - Partitions timeline into moments (Lead Ladder-based)
- `services/game_analysis.py` - AI enrichment for moments
- `services/compact_mode.py` - Timeline compression

**Database:**
- PostgreSQL with SQLAlchemy ORM
- Alembic for migrations
- JSONB for flexible stats storage

### 3. Admin Web (`web/`)

React/TypeScript admin interface:

| Feature | Description |
|---------|-------------|
| **Data Browser** | Filter and view games, teams, scrape runs |
| **Ingestion** | Schedule scrape jobs with date ranges and data type toggles |
| **Game Detail** | View boxscores, player stats, odds, social posts, PBP |
| **Timeline Generation** | Generate and regenerate timeline artifacts |
| **Compact Moments** | Review AI-generated game moment summaries |

**Stack:**
- Next.js (App Router)
- TypeScript
- CSS Modules

## Data Flow

### Ingestion Pipeline

```
1. Scraper fetches data from sources
   ├─ Boxscores → sports_team_boxscores, sports_player_boxscores
   ├─ Odds → sports_game_odds
   ├─ PBP → sports_game_plays
   └─ Social → game_social_posts

2. API generates timeline artifacts (post-scrape)
   ├─ PBP events + Social events → merged timeline
   ├─ Lead Ladder partitioning → moments
   ├─ AI enrichment → headlines/summaries
   └─ Persist → sports_game_timeline_artifacts

3. Clients fetch via API
   ├─ Full timeline (for detailed view)
   └─ Compact timeline (compressed for mobile)
```

### Timeline Generation

See [TECHNICAL_FLOW.md](TECHNICAL_FLOW.md) for the complete pipeline.

**Key Concepts:**
- **Narrative Time**: Events ordered by game phase (pregame, q1, q2, halftime, q3, q4, postgame), not wall-clock time
- **Lead Ladder**: Tier-based lead tracking that determines moment boundaries
- **Moments**: Contiguous segments of plays where game control state is stable
- **Compact Mode**: Semantic compression that preserves social posts and key plays

## Database Schema

### Core Tables

| Table | Description |
|-------|-------------|
| `sports_leagues` | League definitions (NBA, NHL, NCAAB, etc.) |
| `sports_teams` | Teams with names, abbreviations, external IDs |
| `sports_games` | Games with scores, dates, status (`scheduled`, `live`, `final`) |
| `sports_game_plays` | Play-by-play events (quarter, clock, description, scores) |
| `game_social_posts` | X/Twitter posts from team accounts |
| `sports_team_boxscores` | Team stats (JSONB) |
| `sports_player_boxscores` | Player stats (JSONB) |
| `sports_game_odds` | Odds from various books (spread, total, moneyline) |

### Timeline Artifacts

| Table | Description |
|-------|-------------|
| `sports_game_timeline_artifacts` | Generated timelines with moments and summaries |
| `compact_mode_thresholds` | Per-sport Lead Ladder thresholds |
| `game_reading_positions` | User reading positions for progressive reveal |

### Audit & Jobs

| Table | Description |
|-------|-------------|
| `sports_scrape_runs` | Scrape job audit log |
| `sports_job_runs` | General job execution log (timeline generation, etc.) |

## Configuration

### Environment Variables

**Required:**
- `DATABASE_URL` - PostgreSQL connection string
- `ENVIRONMENT` - `development`, `staging`, or `production`

**Optional:**
- `OPENAI_API_KEY` - For AI enrichment (moment summaries)
- `ODDS_API_KEY` - For odds ingestion
- `X_AUTH_TOKEN`, `X_CT0` - For X/Twitter scraping
- `CELERY_BROKER_URL` - Redis URL for Celery (defaults to `redis://redis:6379/0`)

### Sport Configuration

Sport-specific settings live in `api/app/config_sports.py`:

```python
SPORTS_CONFIG = {
    "NBA": SportConfig(
        code="NBA",
        display_name="NBA",
        supports_pbp=True,
        supports_social=True,
        supports_timeline=True,
        supports_odds=True,
    ),
    # ... other sports
}
```

## Deployment

### Docker Compose

```bash
cd infra
cp .env.example .env
docker compose --profile dev up -d --build
```

**Profiles:**
- `dev` - All services (API, scraper, web, postgres, redis)
- `prod` - Production services only

**Services:**
- `api` - FastAPI (port 8000)
- `scraper-worker` - Celery worker
- `scraper-beat` - Celery scheduler
- `web` - Next.js (port 3000)
- `postgres` - PostgreSQL (port 5432)
- `redis` - Redis (port 6379)

### Production

See [DEPLOYMENT.md](DEPLOYMENT.md) for production setup, including:
- Server provisioning
- Nginx reverse proxy
- SSL certificates
- Backup procedures
- Rollback procedures

## Key Principles

1. **Stability over speed** - Downstream apps depend on predictable schemas
2. **Fail fast** - No silent fallbacks that hide data quality issues
3. **Traceable changes** - Every transformation is logged and auditable
4. **Deterministic core** - AI only for narration, not for structure or ordering

## See Also

- [TECHNICAL_FLOW.md](TECHNICAL_FLOW.md) - Detailed timeline generation flow
- [MOMENT_SYSTEM_CONTRACT.md](MOMENT_SYSTEM_CONTRACT.md) - Moment system specification
- [API.md](API.md) - API endpoint reference
- [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md) - Local development setup
- [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md) - Production operations
