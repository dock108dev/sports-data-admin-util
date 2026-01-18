# Operator Runbook

Production operations guide for sports-data-admin.

## Architecture Overview

```mermaid
flowchart LR
  subgraph Client
    Admin[Admin Browser]
  end

  subgraph Edge
    Nginx[Nginx\nadmin.scrolldownsports.*]
  end

  subgraph App
    Web[Admin UI (Next.js)]
    API[FastAPI API]
    Worker[Celery Worker (Scraper)]
  end

  subgraph Data
    Postgres[(Postgres)]
    Redis[(Redis)]
    Storage[(S3/Storage Box)]
  end

  Admin -->|HTTPS| Nginx --> Web
  Web --> API
  API --> Postgres
  API --> Redis
  Worker --> Postgres
  Worker --> Redis
  Worker --> Storage
```

---

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full deployment flow. Key points:

1. **Deploy trigger:** Merge to `main` or manual workflow dispatch
2. **Change detection:** GitHub Actions detects which services changed
3. **Tests:** Unit tests run before deployment
4. **Build:** Images pushed to GHCR with `latest` and commit-sha tags
5. **Server update:** SSH, pull images, run migrations, restart services

### Quick Manual Deploy

```bash
ssh root@<server-ip>
cd /opt/sports-data-api/infra

echo $GHCR_TOKEN | docker login ghcr.io -u dock108 --password-stdin
docker compose --profile prod pull
docker compose --profile prod run --rm migrate
docker compose --profile prod up -d
docker compose --profile prod ps
```

---

## Health Checks

### API Health

```bash
curl -f http://localhost:8000/healthz
```

Returns `503` if database connectivity fails. Use for deploy verification.

### Container Health

```bash
docker compose ps
docker inspect --format='{{.State.Health.Status}}' sports-api
```

---

## Migrations

Alembic migrations are run explicitly (not on startup).

```bash
# Run pending migrations (recommended)
docker compose --profile prod run --rm migrate

# Check current version
docker exec sports-api alembic current

# Run manually
docker exec sports-api alembic upgrade head
```

---

## Backups & Restore

### Nightly Backups

Use `scripts/backup/pg_dump_backup.sh` with a cron job or systemd timer.

Example cron entry:
```bash
0 2 * * * DATABASE_URL=postgresql+asyncpg://... BACKUP_S3_URI=s3://bucket/sports /workspace/scripts/backup/pg_dump_backup.sh
```

Upload options:
- `BACKUP_S3_URI`: Uses AWS CLI (`aws s3 cp`)
- `BACKUP_RCLONE_REMOTE`: Uses `rclone copy` for Hetzner Storage Box or S3-compatible endpoints

### Restore

```bash
gzip -cd sports_YYYYMMDDTHHMMSSZ.sql.gz | psql "${DATABASE_URL}"

# Container restore (destructive)
CONFIRM_DESTRUCTIVE=true docker exec sports-postgres /scripts/restore.sh /backups/sports_YYYYMMDD.sql.gz
```

Note: Restore uses `DROP DATABASE ... WITH (FORCE)` on Postgres 16+ so you don't need to stop app containers first.

### Destructive Operation Guardrails

- `init_db` (SQLAlchemy `create_all`) is blocked in production/staging
- `/scripts/restore.sh` requires `CONFIRM_DESTRUCTIVE=true`

---

## Admin Access

### Basic Auth Setup

```bash
htpasswd -c /etc/nginx/.htpasswd admin
```

### SSH Tunnel Access

For private access without exposing the UI:
```bash
ssh -L 9000:localhost:80 ops@your-host
```
Then visit `http://localhost:9000`.

---

## CI/CD

### GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `GHCR_TOKEN` | GitHub PAT with `write:packages` |
| `DEPLOY_HOST` | Server IP address |
| `DEPLOY_USER` | SSH user (typically `root`) |
| `DEPLOY_SSH_KEY` | Private SSH key |
| `DEPLOY_PATH` | Project path on server |

### Behavior

- Deploys only changed services
- Restarts with `docker compose up -d <service>`

---

## Environment Variables (Production)

Production secrets live in `infra/.env` on the server (never committed).

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Postgres connection string |
| `REDIS_URL` | Redis connection string |
| `CELERY_BROKER_URL` | Celery broker override |
| `ALLOWED_CORS_ORIGINS` | Comma-separated trusted origins |
| `RATE_LIMIT_REQUESTS` | Rate limit requests per window |
| `RATE_LIMIT_WINDOW_SECONDS` | Rate limit window size |
| `ENVIRONMENT` | Must be `production` |

### Startup Validation (Fail-Fast)

Containers validate required environment at startup and exit if misconfigured.

**API required:**
- `ENVIRONMENT` (must be `development`, `staging`, or `production`)
- `DATABASE_URL`
- `ALLOWED_CORS_ORIGINS` (production only, must not include `localhost`)

**Scraper/worker required:**
- `ENVIRONMENT`
- `DATABASE_URL`
- `REDIS_URL`
- `ODDS_API_KEY` (production only)
- `X_BEARER_TOKEN` **or** `X_AUTH_TOKEN` + `X_CT0` (production only)

**Production-only constraints:**
- `DATABASE_URL` and `REDIS_URL` must not point at `localhost`
- `DATABASE_URL` must not use default `postgres:postgres` credentials

---

## Troubleshooting

### Deployment fails with "permission denied" on SSH

- Verify `DEPLOY_SSH_KEY` contains the complete private key
- Ensure public key is in server's `~/.ssh/authorized_keys`
- Check permissions: `chmod 600 ~/.ssh/authorized_keys`

### Images fail to pull from GHCR

- Verify `GHCR_TOKEN` has correct permissions
- Check if token has expired
- Test: `echo $GHCR_TOKEN | docker login ghcr.io -u dock108 --password-stdin`

### Service health checks fail

- Check logs: `docker compose --profile prod logs <service>`
- Verify `infra/.env` variables
- Check migration logs: `docker compose --profile prod logs migrate`

### Container keeps restarting

- Check environment validation errors in logs
- Verify required env vars are set
- Check database connectivity

---

## Guardrails

- **Do not** edit production files on VM without committing to repo (except `.env`)
- **Migrations:** Run explicitly via `migrate` service, not at startup
- **Debug failures:** Start with GitHub Actions logs, then check container logs

---

## See Also

- [INFRA.md](INFRA.md) - Docker configuration and local development
- [DEPLOYMENT.md](DEPLOYMENT.md) - Full deployment flow
- [EDGE_PROXY.md](EDGE_PROXY.md) - Caddy/Nginx routing
