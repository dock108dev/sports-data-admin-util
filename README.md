# Sports Data Admin

Central data platform for Scroll Down Sports. It ingests, normalizes, and serves sports data to internal consumers (admin UI and downstream apps).

## Run Locally

```bash
cd infra
cp .env.example .env

docker compose --profile dev up -d --build
```

Note: `infra/.env` contains secrets and is gitignored.

**URLs**
- Admin UI: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/healthz

For manual setup, see [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md).

## Deployment Basics

Infrastructure details live in [docs/INFRA.md](docs/INFRA.md). Production deploy flow and rollback guidance live in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Documentation

Start with the docs index: [docs/INDEX.md](docs/INDEX.md).

## Contributing

See [AGENTS.md](AGENTS.md) and [docs/CODEX_TASK_RULES.md](docs/CODEX_TASK_RULES.md).
