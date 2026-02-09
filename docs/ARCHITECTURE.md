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
│  Sports Ref, NHL API             Celery/uv                  Normalized      │
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
- **Sources:** Sports Reference (NBA boxscores, NCAAB), NBA API (NBA PBP), NHL API (NHL), CBB Stats API (NCAAB boxscores), The Odds API, X/Twitter
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

## Game Flow Generation

The game flow system converts play-by-play data into block-based narratives through an 8-stage pipeline.

### Architecture

A game flow consists of **4-7 narrative blocks**, each containing 2-4 sentences (~65 words). Blocks are designed for 60-90 second total read time.

```
NORMALIZE_PBP → GENERATE_MOMENTS → VALIDATE_MOMENTS → ANALYZE_DRAMA → GROUP_BLOCKS → RENDER_BLOCKS → VALIDATE_BLOCKS → FINALIZE_MOMENTS
```

### Pipeline Stages

| Stage | Purpose |
|-------|---------|
| NORMALIZE_PBP | Fetch and normalize PBP with phase assignments |
| GENERATE_MOMENTS | Segment plays into moment boundaries |
| VALIDATE_MOMENTS | Validate moment structure |
| ANALYZE_DRAMA | Use AI to identify dramatic peak and weight quarters |
| GROUP_BLOCKS | Group moments into 4-7 narrative blocks (drama-weighted) |
| RENDER_BLOCKS | Generate block narratives via OpenAI |
| VALIDATE_BLOCKS | Enforce guardrail invariants |
| FINALIZE_MOMENTS | Persist to database |

### Core Concept: Narrative Block

A narrative block contains:
- `block_index`: Position (0-6)
- `role`: Semantic role (SETUP, MOMENTUM_SHIFT, RESPONSE, DECISION_POINT, RESOLUTION)
- `moment_indices`: Which moments are grouped
- `narrative`: 2-4 sentences (~65 words)
- Score and time context

### Key Properties

- **Consumer-focused:** 4-7 blocks, 60-90 second read time
- **Traceability:** Blocks → Moments → Plays
- **Semantic roles:** Each block has a narrative purpose
- **Guardrails enforced:** Hard limits on block count, social post count, word count
- **Social-independent:** Game flow structure identical with/without social data

See [GAMEFLOW_CONTRACT.md](GAMEFLOW_CONTRACT.md) for the authoritative specification.

See [GAMEFLOW_PIPELINE.md](GAMEFLOW_PIPELINE.md) for implementation details.

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
- `sports_game_odds` - Betting lines (game-centric)
- `fairbet_game_odds_work` - Bet-centric odds for cross-book comparison
- `team_social_posts` - Social media content (mapped to games via `mapping_status`)

See `sql/` for complete schema.

---

## API Endpoints

### App Endpoints (for external apps)
- `GET /api/games` - List games by date range
- `GET /api/games/{id}` - Single game details
- `GET /api/games/{id}/pbp` - Play-by-play by period
- `GET /api/games/{id}/flow` - AI-generated game flow

### Admin Endpoints
- `GET /api/admin/sports/games` - List games with filtering
- `GET /api/admin/sports/games/{id}` - Full game detail
- `GET /api/admin/sports/scraper/runs` - List scraper runs
- `POST /api/admin/sports/scraper/runs` - Create scraper run
- `GET /api/admin/sports/pipeline/run/{id}` - Pipeline run status

### FairBet Endpoints
- `GET /api/fairbet/odds` - Cross-book odds comparison

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
- **Framework:** Next.js 16+
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
