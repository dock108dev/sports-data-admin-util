# Deployment Setup (One-Time)

This doc covers the **one-time** setup steps for deploying to a Hetzner VM. For the ongoing deploy flow, rollback strategy, and troubleshooting, see:

- `docs/DEPLOYMENT.md`
- `docs/OPERATOR_RUNBOOK.md`

## Server prerequisites

- A Hetzner VM reachable over SSH
- Docker installed
- A DNS record pointing at the VM (Cloudflare is commonly used in front)

## Repo on server

```bash
mkdir -p /opt/sports-data-api
cd /opt/sports-data-api
git clone https://github.com/dock108/sports-data-admin-util.git .
```

## Production environment file

Create `infra/.env` **on the server** (do not commit it):

```bash
cd /opt/sports-data-api
nano infra/.env
```

Start from `infra/.env.example` and fill in production values:

- `ENVIRONMENT=production`
- `ALLOWED_CORS_ORIGINS` (comma-separated)
- `ODDS_API_KEY` (required in production for the scraper)
- `X_AUTH_TOKEN` and `X_CT0` (required in production for historical social scraping)

## Caddy / routing

If you use Caddy at the edge, ensure `/api/*` is routed to the FastAPI container without stripping the `/api` prefix.

See `docs/EDGE_PROXY.md`.

## First boot

From `infra/` on the server:

```bash
cd /opt/sports-data-api/infra
docker compose --profile prod pull
docker compose --profile prod up -d postgres redis
docker compose --profile prod run --rm migrate
docker compose --profile prod up -d
```

