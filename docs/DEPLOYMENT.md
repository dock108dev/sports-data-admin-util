# Deployment

## Overview

Production runs on a Hetzner VM using Docker Compose. Cloudflare fronts inbound traffic to the VM. Deployments are orchestrated through GitHub Actions, which build and publish container images and then update services on the server.

## Server Setup (One-Time)

Before the first deployment, prepare the Hetzner server:

```bash
# SSH into the server
ssh root@37.27.222.59

# Install Docker and Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Create project directory
mkdir -p /opt/sports-data-api
cd /opt/sports-data-api

# Clone the repository (or copy files)
git clone https://github.com/dock108/sports-data-admin-util.git .

# Create the production .env file
nano infra/.env
# (Paste the production environment configuration)

# Login to GitHub Container Registry
echo $GHCR_TOKEN | docker login ghcr.io -u dock108 --password-stdin

# Pull initial images
cd infra
docker compose -f docker-compose.yml --profile prod pull

# Run initial migrations
docker compose -f docker-compose.yml --profile prod run --rm migrate

# Start all services
docker compose -f docker-compose.yml --profile prod up -d
```

## Deploy Flow (Step-by-Step)

1. **Trigger**: A deploy runs on merge to `main` or a manual GitHub Actions workflow dispatch from `main`.
2. **Change detection**: GitHub Actions detects which parts of the codebase changed (api, web, scraper, infra).
3. **Tests**: Runs unit tests for API and scraper changes.
4. **CI/CD build**: GitHub Actions builds the API, web, and scraper images and pushes them to GHCR with `latest` and commit-sha tags.
5. **Server update**: The deploy job connects to the Hetzner VM over SSH, navigates to `/opt/sports-data-api/infra`, logs into GHCR, pulls updated images, runs migrations if needed, and restarts only the changed services.
6. **Health checks**: After each service restart, the workflow verifies the service is healthy before proceeding.

## GitHub Secrets Configuration

The CI/CD pipeline requires the following secrets to be configured in the GitHub repository settings (Settings → Secrets and variables → Actions):

| Secret | Description | Example |
|--------|-------------|---------|
| `DEPLOY_HOST` | IP address or hostname of the Hetzner server | `37.27.222.59` |
| `DEPLOY_USER` | SSH user for deployment (typically `root`) | `root` |
| `DEPLOY_SSH_KEY` | Private SSH key for authentication | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `DEPLOY_PATH` | Absolute path to project directory on server | `/opt/sports-data-api` |
| `GHCR_TOKEN` | GitHub Personal Access Token with `write:packages` permission | `ghp_...` |

**Setting up GHCR_TOKEN:**
1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token with `write:packages`, `read:packages`, and `delete:packages` scopes
3. Add the token as a repository secret named `GHCR_TOKEN`

**Setting up SSH key:**
1. Generate a dedicated SSH key pair: `ssh-keygen -t ed25519 -C "github-actions-deploy"`
2. Add the public key to the server's `~/.ssh/authorized_keys`
3. Add the private key as the `DEPLOY_SSH_KEY` secret (include the entire key including headers)

## Environment Variables

Production secrets live only on the server in a `.env` file located at `infra/.env` within the project directory. The compose file loads this via environment variable substitution. Use `infra/.env.example` as the template (do not commit `infra/.env`).

Required variable categories include:

- **Database/Redis**: Postgres credentials, Redis password, and service connection URLs (`DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`).
- **App/runtime config**: `ENVIRONMENT=production`, `ALLOWED_CORS_ORIGINS`, and related runtime toggles.
- **External APIs**: Odds API and X/Twitter scraping credentials for the worker.
- **Frontend URLs**: `NEXT_PUBLIC_SPORTS_API_URL` (and related internal API URLs if applicable).

Do not check secrets into git. Keep production values only in the server `.env`.

## Rollback Strategy

Rollbacks are performed by pinning a service to a previous GHCR image tag (typically the commit-sha tag created by CI/CD), then restarting the service:

1. Update the service image tag in the server’s compose config to the desired SHA (or image digest).
2. Run `docker compose pull <service>` to fetch the older image.
3. Run `docker compose up -d <service>` to restart with the pinned version.

Note: database migrations are not rolled back automatically. If a deploy includes a schema change, you must manually revert the migration before running the older application image.

## Operational Notes & Guardrails

- **Do not** edit production secrets or compose files on the VM without committing the change to the repo (except for the server-only `.env`).
- **Migrations**: run explicitly using the `migrate` service before or after app restarts; do not rely on startup migrations in production.
- **Deploy failures**: start with GitHub Actions logs and then check container logs on the VM (`docker compose logs <service>`).

## Troubleshooting

### Deployment fails with "permission denied" on SSH

- Verify the `DEPLOY_SSH_KEY` secret contains the complete private key including headers
- Ensure the corresponding public key is in `/root/.ssh/authorized_keys` on the server
- Check SSH key permissions on the server: `chmod 600 ~/.ssh/authorized_keys`

### Images fail to pull from GHCR

- Verify `GHCR_TOKEN` has `read:packages` and `write:packages` permissions
- Check if the token has expired (PATs expire after a set period)
- Ensure the repository visibility allows package access
- Manually test: `echo $GHCR_TOKEN | docker login ghcr.io -u dock108 --password-stdin`

### Service health checks fail after deployment

- Check service logs: `docker compose -f docker-compose.yml --profile prod logs <service>`
- Verify environment variables in `infra/.env` are correct (compare against `infra/.env.example`)
- Check database connectivity: `docker compose -f docker-compose.yml --profile prod exec api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"`
- Ensure migrations ran successfully: `docker compose -f docker-compose.yml --profile prod logs migrate`

### Manual deployment from server

If GitHub Actions is unavailable, you can deploy manually:

```bash
ssh root@37.27.222.59
cd /opt/sports-data-api/infra

# Login to GHCR
echo $GHCR_TOKEN | docker login ghcr.io -u dock108 --password-stdin

# Pull latest images
docker compose -f docker-compose.yml --profile prod pull

# Run migrations
docker compose -f docker-compose.yml --profile prod run --rm migrate

# Restart services
docker compose -f docker-compose.yml --profile prod up -d

# Check status
docker compose -f docker-compose.yml --profile prod ps
docker compose -f docker-compose.yml --profile prod logs --tail=50
```

## Assumptions

This deployment model assumes a single Hetzner VM running Docker Compose with Cloudflare in front and GitHub Actions performing SSH-based deploys. It should be revisited if production moves to multi-host orchestration, a different image registry, or a non-SSH deployment mechanism.
