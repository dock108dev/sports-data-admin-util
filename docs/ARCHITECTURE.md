# Architecture Overview

## System Purpose

Sports Data Admin is the **centralized sports data hub for all Dock108 apps**.

**Primary Functions:**
- Automated ingestion from multiple sports data sources
- Normalization and storage in unified PostgreSQL database
- REST API serving data to all Dock108 sports products
- Narrative story generation (Scroll Down Sports feature)
- Admin UI for data management and monitoring

**Scope:** Multi-sport (NBA, NHL, NCAAB), multi-consumer (all Dock108 apps)

## High-Level Architecture

```mermaid
graph TD
    A[External Sources<br/>ESPN, Hockey Reference, etc.] --> B[Multi-Sport Scraper]
    B --> C[PostgreSQL Hub<br/>Normalized Data]
    C --> D[REST API<br/>All Dock108 Apps]
    C --> E[Story Generator<br/>Scroll Down Sports]
    D --> F[Dock108 Products]
    E --> G[Scroll Down Sports]
    C --> H[Admin UI<br/>Management & Monitoring]
```

## Components

### 1. Data Scraper (`scraper/`)
**Purpose:** Automated ingestion from external sources

- **Sports:** NBA, NHL, NCAAB
- **Sources:** ESPN, Hockey Reference, Sports Reference
- **Data Types:** Play-by-play, box scores, odds, social media
- **Scheduling:** Celery task queue
- **Output:** Normalized data to PostgreSQL

### 2. REST API (`api/`)
**Purpose:** Serve data to all Dock108 apps

- **Framework:** FastAPI
- **Database:** PostgreSQL (async SQLAlchemy)
- **Endpoints:** Games, plays, box scores, odds, social, teams
- **Story API:** Chapters-first narrative generation (Scroll Down feature)
- **Admin Endpoints:** Scraper management, data browser

### 3. Admin UI (`web/`)
**Purpose:** Data management and monitoring

- **Framework:** React + TypeScript + Next.js
- **Features:**
  - Data browser (games, plays, stats)
  - Story Generator interface (Scroll Down feature)
  - Scraper run management
  - Data quality monitoring

### 4. Database (PostgreSQL)
**Purpose:** Single source of truth

- **Schema:** Normalized across sports
- **Tables:** games, plays, box scores, odds, social posts, teams
- **Migrations:** Alembic (see `sql/`)
- **Access:** Async SQLAlchemy ORM

---

## Story Generation Pipeline

The core product feature: converting play-by-play into narrative stories.

### Pipeline Flow

```mermaid
graph LR
    A[Play-by-Play] --> B[ChapterizerV1]
    B --> C[Chapters]
    C --> D[StoryState Builder]
    D --> E[AI Generator]
    E --> F[GameStory]
```

### Stage Details

#### 1. ChapterizerV1
**Input:** Normalized play-by-play events  
**Output:** Chapters with reason codes  
**Logic:** Structural boundary detection (NBA v1 rules)  
**Deterministic:** Yes  
**AI:** No  

**Boundaries:**
- Hard: Period start/end, overtime, game end
- Scene Reset: Timeouts, reviews, challenges
- Momentum: Crunch time start (minimal v1)

See [NBA_V1_BOUNDARY_RULES.md](NBA_V1_BOUNDARY_RULES.md)

#### 2. StoryState Builder
**Input:** Ordered chapters  
**Output:** StoryState (running context)  
**Logic:** Deterministic stat accumulation  
**Derived From:** Prior chapters only  
**AI:** No  

**Tracks:**
- Player stats (top 6 by points)
- Team scores
- Momentum hints
- Theme tags

See [AI_CONTEXT_POLICY.md](AI_CONTEXT_POLICY.md)

#### 3. AI Story Generator
**Input:** Current chapter + StoryState  
**Output:** Chapter summaries + titles  
**Logic:** Sequential generation (no future knowledge)  
**AI:** Yes (OpenAI)  

**Modes:**
- Chapter Summary: 1-3 sentences per chapter
- Chapter Title: 3-8 words per chapter
- Compact Story: Full game recap (4-12 min read)

See [AI_SIGNALS_NBA_V1.md](AI_SIGNALS_NBA_V1.md)

#### 4. GameStory Output
**Format:** JSON  
**Contains:** Chapters, summaries, compact story  
**Consumed By:** Admin UI, consumer apps  

---

## Data Models

### Play
```python
@dataclass
class Play:
    index: int              # Position in timeline (0-based)
    event_type: str         # "pbp", "social", etc.
    raw_data: dict          # Complete event data
```

**Properties:**
- Atomic unit of game action
- Immutable
- Chronological

### Chapter
```python
@dataclass
class Chapter:
    chapter_id: str         # "ch_001"
    play_start_idx: int     # First play (inclusive)
    play_end_idx: int       # Last play (inclusive)
    plays: list[Play]       # Raw plays in chapter
    reason_codes: list[str] # Why boundary exists
    period: int | None      # Quarter/period
    time_range: TimeRange | None  # Clock range
```

**Properties:**
- Contiguous play range
- Deterministic boundaries
- No inherent narrative text

### StoryState
```python
@dataclass
class StoryState:
    chapter_index_last_processed: int
    players: dict[str, PlayerStoryState]
    teams: dict[str, TeamStoryState]
    momentum_hint: MomentumHint
    theme_tags: list[str]
    constraints: dict  # no_future_knowledge: true
```

**Properties:**
- Derived from prior chapters only
- Incremental updates
- Bounded lists (top 6 players, max 8 themes)

### GameStory
```python
@dataclass
class GameStory:
    game_id: int
    sport: str
    chapters: list[Chapter]
    compact_story: str | None
    reading_time_estimate_minutes: float | None
    metadata: dict
```

**Properties:**
- Authoritative output
- Consumed by apps
- Forward-compatible schema

---

## AI Responsibility Boundaries

### What AI Does
- ✅ Generate chapter summaries (1-3 sentences)
- ✅ Generate chapter titles (3-8 words)
- ✅ Generate compact story (full game recap)
- ✅ Use callbacks to prior chapters
- ✅ Interpret plays with sportscaster voice

### What AI Does NOT Do
- ❌ Define chapter boundaries
- ❌ Decide structure
- ❌ Infer stats beyond provided signals
- ❌ See future chapters during sequential generation
- ❌ Compute importance scores
- ❌ Make strategic decisions

**Principle:** AI is a narrative renderer, not a decision engine.

---

## Database Schema

### Core Tables
- `sports_games` - Game metadata
- `sports_game_plays` - Play-by-play events
- `sports_team_boxscores` - Team stats
- `sports_player_boxscores` - Player stats
- `sports_game_odds` - Betting lines
- `game_social_posts` - Social media content

### Story Tables (Future)
- `game_stories` - Generated stories (planned)
- `chapter_summaries` - Chapter summaries (planned)

See `sql/` for complete schema.

---

## API Endpoints

### Story Generation
- `GET /api/admin/sports/games/{id}/story` - Fetch game story
- `GET /api/admin/sports/games/{id}/story-state` - Fetch story state
- `POST /api/admin/sports/games/{id}/story/regenerate-*` - Regenerate components

### Game Data
- `GET /api/admin/sports/games` - List games
- `GET /api/admin/sports/games/{id}` - Game details
- `GET /api/admin/sports/games/{id}/plays` - Play-by-play

### Scraper
- `GET /api/admin/sports/scrape-runs` - List scraper runs
- `POST /api/admin/sports/scrape-runs` - Start scraper

See [API.md](API.md) for complete reference.

---

## Tech Stack Details

### Backend
- **Framework:** FastAPI
- **Database:** PostgreSQL 15+
- **ORM:** SQLAlchemy (async)
- **Migrations:** Alembic
- **AI:** OpenAI API
- **Task Queue:** Celery + Redis

### Frontend
- **Framework:** Next.js 14
- **Language:** TypeScript
- **Styling:** CSS Modules
- **API Client:** Fetch API

### Scraper
- **Language:** Python 3.11+
- **Package Manager:** uv
- **HTTP:** httpx
- **Parsing:** BeautifulSoup, lxml

---

## Development Workflow

### Local Development
```bash
# Backend
cd api
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd web
npm install
npm run dev

# Scraper
cd scraper
uv sync
uv run python -m bets_scraper
```

### Running Tests
```bash
# Backend
cd api
pytest

# Frontend
cd web
npm test
```

### Database Migrations
```bash
cd api
alembic upgrade head
```

---

## Deployment

**Environments:**
- Development (local)
- Staging (staging.scrolldownsports.com)
- Production (api.scrolldownsports.com)

**Infrastructure:**
- Docker containers
- Caddy reverse proxy
- PostgreSQL managed database
- Redis for Celery

See [DEPLOYMENT.md](DEPLOYMENT.md) and [INFRA.md](INFRA.md).

---

## Key Principles

1. **Stability over speed** — Downstream apps depend on this
2. **Predictable schemas** — No silent changes
3. **Zero silent failures** — Log everything
4. **Traceable changes** — Every transformation explainable
5. **Structure before narrative** — Chapters are deterministic
6. **No future knowledge** — AI sees only prior chapters

See [AGENTS.md](../AGENTS.md) for coding standards.
