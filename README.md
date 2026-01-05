# Sports Data Admin

The central sports data administration platform for **Scroll Down Sports**. This system ingests, curates, and publishes sports data consumed by downstream applications.

---

## What Is This?

Sports Data Admin is the **source of truth** for all sports data in the Scroll Down Sports ecosystem. It handles:

- **Data ingestion** from external sources (Sports Reference, The Odds API, X/Twitter)
- **Normalization** into predictable, consistent schemas
- **Curation** via the admin UI for review and quality control
- **Publishing** through a REST API consumed by downstream apps

This is **not a user-facing product**. It is internal infrastructure for data operations.

---

## Who Uses This?

| Role | Purpose |
|------|---------|
| Data Ops | Schedule scrapes, review ingested data, fix issues |
| Developers | Integrate downstream apps via the API |
| AI Agents | Automated data tasks (Codex, Cursor, etc.) |

End users never interact with this platform directly.

---

## Core Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INGEST → REVIEW → PUBLISH                    │
└─────────────────────────────────────────────────────────────────────┘

  External Sources          Admin Platform           Downstream Apps
  ─────────────────         ──────────────           ───────────────
  Sports Reference    ──►   Scraper Workers    ──►   REST API
  The Odds API        ──►   PostgreSQL         ──►   scroll-down-app (iOS)
  X/Twitter           ──►   Admin UI           ──►   scroll-down-sports-ui (Web)
```

1. **Ingest**: Scrapers pull data from external sources on a schedule or on-demand
2. **Review**: Operators use the admin UI to verify data quality, fix gaps, rescrape as needed
3. **Publish**: Clean data is exposed via the REST API for downstream consumption

---

## Downstream Consumers

This platform serves:

| App | Description |
|-----|-------------|
| `scroll-down-app` | iOS mobile app |
| `scroll-down-sports-ui` | Web frontend |

Both consume the same REST API. Schema changes here affect both consumers—**never break schemas silently**.

---

## Repository Structure

```
sports-data-admin/
├── api/              # FastAPI backend (REST API + Alembic migrations)
├── scraper/          # Celery workers (boxscores, odds, social, play-by-play)
├── web/              # Next.js admin UI
├── sql/              # Legacy SQL schemas (now managed by Alembic)
├── infra/            # Docker Compose, Dockerfiles, Nginx config
└── docs/             # Detailed documentation
```

---

## Quick Start

### Docker (Recommended)

```bash
cd infra
cp .env.example .env   # Edit credentials

# Start everything
docker compose --profile dev up -d --build
```

**URLs:**
- Admin UI: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/healthz

### Local Development

See [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) for running services individually.

---

## Data Types

| Type | Source | Description |
|------|--------|-------------|
| Games | Sports Reference | Schedules, scores, status |
| Boxscores | Sports Reference | Team and player statistics |
| Odds | The Odds API | Spreads, totals, moneylines |
| Social | X/Twitter | Team posts (24-hour game window) |
| Play-by-play | Sports Reference | Game event sequences |

---

## Key Principles

1. **Stability over speed** — Downstream apps depend on this. Don't ship broken data.
2. **Predictable schemas** — No silent changes. Document everything.
3. **Zero silent failures** — Log all errors with context. Never swallow exceptions.
4. **Traceable changes** — Every transformation must be explainable.

---

## Documentation

Start with the [Documentation Index](docs/INDEX.md) for detailed guides:

- [Platform Overview](docs/PLATFORM_OVERVIEW.md)
- [Local Development](docs/LOCAL_DEVELOPMENT.md)
- [Infrastructure](docs/INFRA.md)
- [Database Integration](docs/DATABASE_INTEGRATION.md)
- [Operator Runbook](docs/OPERATOR_RUNBOOK.md)
- [Scoring Logic & Scrapers](docs/SCORE_LOGIC_AND_SCRAPERS.md)
- [X Integration](docs/X_INTEGRATION.md)

---

## API Contract

This API implements the `scroll-down-api-spec`. Schema changes require:

1. Update the spec first
2. Update this implementation
3. Document breaking changes in [CHANGELOG.md](docs/CHANGELOG.md)

---

## Contributing

See [AGENTS.md](AGENTS.md) for AI agent guidance and [docs/CODEX_TASK_RULES.md](docs/CODEX_TASK_RULES.md) for task formatting.

**Before making changes:**
- Read relevant files before proposing edits
- Don't add dependencies casually
- Don't modify schemas without migrations
- Don't break consumers silently
