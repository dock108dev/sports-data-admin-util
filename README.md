# Sports Data Admin

Central data platform for Scroll Down Sports. It ingests, normalizes, and serves sports data to internal consumers (admin UI and downstream apps).

## Run Locally

### Docker (recommended)

```bash
cd infra
cp .env.example .env

docker compose --profile dev up -d --build
```

**URLs**
- Admin UI: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/healthz

### Local development (manual)

See [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md).

## Deployment Basics

Infrastructure and deployment references live in [docs/INFRA.md](docs/INFRA.md). The `infra/` directory contains Docker and compose assets used for local and deploy environments.

## Documentation

Start with the docs index: [docs/INDEX.md](docs/INDEX.md).

Key guides:
- [Platform Overview](docs/PLATFORM_OVERVIEW.md)
- [API](docs/API.md)
- [Database Integration](docs/DATABASE_INTEGRATION.md)
- [Operator Runbook](docs/OPERATOR_RUNBOOK.md)
- [Scoring & Scrapers](docs/SCORE_LOGIC_AND_SCRAPERS.md)
- [X Integration](docs/X_INTEGRATION.md)

## Contributing

See [AGENTS.md](AGENTS.md) and [docs/CODEX_TASK_RULES.md](docs/CODEX_TASK_RULES.md).
