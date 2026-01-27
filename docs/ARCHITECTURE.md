# Architecture Overview

## System Purpose

Sports Data Admin is the **centralized sports data hub for all Dock108 apps**.

**Primary Functions:**
- Automated ingestion from multiple sports data sources
- Normalization and storage in unified PostgreSQL database
- REST API serving data to all Dock108 sports products
- Timeline generation combining PBP and social events
- Admin UI for data management and monitoring

**Scope:** Multi-sport (NBA, NHL, NCAAB), multi-consumer (all Dock108 apps)

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INGESTION                                          │
│                                                                             │
│  [External Sources]  ──scrape──▶  [Scraper]  ──persist──▶  [PostgreSQL]    │
│  ESPN, Hockey Ref                Celery/uv                  Normalized      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SERVING                                            │
│                                                                             │
│  [PostgreSQL]  ──▶  [REST API]  ──▶  [Dock108 Apps]                        │
│                     FastAPI          All products                           │
│                                                                             │
│  [PostgreSQL]  ──▶  [Admin UI]  ──▶  [Operators]                           │
│                     Next.js          Data management                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Data Scraper (`scraper/`)
**Purpose:** Automated ingestion from external sources

- **Sports:** NBA, NHL, NCAAB
- **Sources:** ESPN, Hockey Reference, Sports Reference
- **Data Types:** Play-by-play, box scores, odds, social media
- **Scheduling:** Celery task queue with Redis
- **Output:** Normalized data to PostgreSQL

### 2. REST API (`api/`)
**Purpose:** Serve data to all Dock108 apps

- **Framework:** FastAPI
- **Database:** PostgreSQL (async SQLAlchemy)
- **Endpoints:** Games, plays, box scores, odds, social, teams
- **Admin Endpoints:** Scraper management, data browser

### 3. Admin UI (`web/`)
**Purpose:** Data management and monitoring

- **Framework:** React + TypeScript + Next.js
- **Features:**
  - Data browser (games, plays, stats)
  - Scraper run management
  - Data quality monitoring

### 4. Database (PostgreSQL)
**Purpose:** Single source of truth

- **Schema:** Normalized across sports
- **Tables:** games, plays, box scores, odds, social posts, teams
- **Migrations:** Alembic (see `sql/`)
- **Access:** Async SQLAlchemy ORM

---

## Story Generation

The story system converts play-by-play data into condensed moment-based narratives through a multi-stage pipeline.

### Architecture

A story is an ordered list of **condensed moments**. Each moment is a small set of PBP plays with at least one explicitly narrated play.

```
NORMALIZE_PBP → GENERATE_MOMENTS → VALIDATE_MOMENTS → RENDER_NARRATIVES → FINALIZE_MOMENTS
```

### Pipeline Stages

| Stage | Purpose |
|-------|---------|
| NORMALIZE_PBP | Fetch and normalize PBP with phase assignments |
| GENERATE_MOMENTS | Segment plays into moment boundaries |
| VALIDATE_MOMENTS | Validate against story contract |
| RENDER_NARRATIVES | Generate narrative text via OpenAI |
| FINALIZE_MOMENTS | Persist to database |

### Core Concept: Condensed Moment

A condensed moment contains:
- `play_ids`: The backing plays
- `explicitly_narrated_play_ids`: Plays directly described in narrative
- `narrative`: Text describing the plays
- Time and score context

### Key Properties

- **Traceability:** Every narrative sentence maps to specific plays
- **No abstraction:** No headers, sections, or thematic groupings
- **Ordered:** Moments follow game chronology
- **Mechanical segmentation:** Moment boundaries are deterministic, not AI-driven
- **OpenAI is prose-only:** It renders narratives, not structure

See [story_contract.md](story_contract.md) for the authoritative specification.

See [STORY_PIPELINE.md](STORY_PIPELINE.md) for implementation details.

**Code:** `api/app/services/pipeline/`

---

## Timeline System

The timeline system combines PBP events with social media posts into a unified game timeline.

### Components

- `timeline_generator.py` - Main assembly logic
- `timeline_phases.py` - Game phase detection
- `timeline_validation.py` - Validation rules
- `timeline_events.py` - Event normalization
- `social_events.py` - Social post processing

See [TIMELINE_ASSEMBLY.md](TIMELINE_ASSEMBLY.md) for details.

---

## Database Schema

### Core Tables
- `sports_games` - Game metadata
- `sports_game_plays` - Play-by-play events
- `sports_team_boxscores` - Team stats
- `sports_player_boxscores` - Player stats
- `sports_game_odds` - Betting lines
- `game_social_posts` - Social media content

See `sql/` for complete schema.

---

## API Endpoints

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
- **Task Queue:** Celery + Redis

### Frontend
- **Framework:** Next.js 14+
- **Language:** TypeScript
- **Styling:** CSS Modules
- **API Client:** Fetch API

### Scraper
- **Language:** Python 3.11+
- **Package Manager:** uv
- **HTTP:** httpx
- **Parsing:** BeautifulSoup, lxml

---

## Key Principles

1. **Stability over speed** — Downstream apps depend on this
2. **Predictable schemas** — No silent changes
3. **Zero silent failures** — Log everything
4. **Traceable changes** — Every transformation explainable
5. **Single source of truth** — Normalized data across sports

See [CLAUDE.md](../CLAUDE.md) for coding standards.
