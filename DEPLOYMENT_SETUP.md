# Deployment Setup Guide

This guide walks you through setting up CI/CD deployment to your Hetzner server at `sports-data-admin.dock108.ai` (37.27.222.59).

## What Was Changed

The following files have been updated to support automated deployment:

1. **`.github/workflows/backend-ci-cd.yml`** - Updated CI/CD workflow with:
   - Correct GHCR image paths (`ghcr.io/dock108/sports-data-admin-util-{service}:latest`)
   - Proper deployment script that navigates to `/opt/sports-data-api/infra`
   - Migration step before API deployment
   - Health checks after each service restart
   - Support for both `scraper` and `scraper-beat` services

2. **`infra/docker-compose.yml`** - Added image tags to services:
   - `api`: `ghcr.io/dock108/sports-data-admin-util-api:latest`
   - `web`: `ghcr.io/dock108/sports-data-admin-util-web:latest`
   - `scraper`: `ghcr.io/dock108/sports-data-admin-util-scraper:latest`
   - `migrate`: Uses the same API image

3. **`docs/DEPLOYMENT.md`** - Comprehensive deployment documentation including:
   - GitHub secrets configuration
   - Server setup instructions
   - Deployment flow explanation
   - Troubleshooting guide

## Next Steps

### 1. Configure GitHub Secrets

Go to your repository settings: `https://github.com/dock108/sports-data-admin-util/settings/secrets/actions`

Add these secrets:

| Secret Name | Value | Notes |
|-------------|-------|-------|
| `DEPLOY_HOST` | `37.27.222.59` | Your Hetzner server IP |
| `DEPLOY_USER` | `root` | SSH user (or your preferred user) |
| `DEPLOY_SSH_KEY` | Your private SSH key | Generate with `ssh-keygen -t ed25519` |
| `DEPLOY_PATH` | `/opt/sports-data-api` | Project directory on server |
| `GHCR_TOKEN` | GitHub PAT | Create at github.com/settings/tokens |

**To create GHCR_TOKEN:**
1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Select scopes: `write:packages`, `read:packages`, `delete:packages`
4. Generate and copy the token

**To set up SSH key:**
```bash
# On your local machine
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/hetzner_deploy

# Copy public key to server
ssh-copy-id -i ~/.ssh/hetzner_deploy.pub root@37.27.222.59

# Copy private key content for GitHub secret
cat ~/.ssh/hetzner_deploy
# Copy the entire output including BEGIN/END lines
```

### 2. Set Up the Hetzner Server

SSH into your server and run:

```bash
ssh root@37.27.222.59

# Install Docker if not already installed
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Create project directory
mkdir -p /opt/sports-data-api
cd /opt/sports-data-api

# Clone the repository
git clone https://github.com/dock108/sports-data-admin-util.git .

# Create the production .env file
nano infra/.env
```

Paste this production `.env` configuration:

```bash
# Environment
ENVIRONMENT=production

# Postgres
POSTGRES_DB=dock108
POSTGRES_USER=dock108
POSTGRES_PASSWORD=4815162342bogey
POSTGRES_PORT=5432

# Redis
REDIS_PASSWORD=4815162342bogey

# Migrations
RUN_MIGRATIONS=false

# Odds API
ODDS_API_KEY=13ae83e9a816daa34ef76c0b0d12b81f

# X/Twitter authentication
X_AUTH_TOKEN=2be7702d0970e27ccfe885151eefcf9b963a2415
X_CT0=62db509922e44c793794aa2670064f8d9729685660a5a5a718f3f293918db48e1e7c675950c0f720cfc0300c1f40bea1140bd0ccbb5725013c936a77ef8c021077feca292f8fe92be9799c01abb30504

# Database URLs (internal Docker network)
DATABASE_URL=postgresql+asyncpg://dock108:4815162342bogey@postgres:5432/dock108
REDIS_URL=redis://:4815162342bogey@redis:6379/2

# Celery configuration
CELERY_BROKER_URL=redis://:4815162342bogey@redis:6379/2
CELERY_RESULT_BACKEND=redis://:4815162342bogey@redis:6379/2

# CORS Origins
ALLOWED_CORS_ORIGINS=https://sports-data-admin.dock108.ai,https://dock108.ai,https://api.dock108.ai

# Web URLs
NEXT_PUBLIC_SPORTS_API_URL=https://sports-data-admin.dock108.ai
NEXT_PUBLIC_THEORY_ENGINE_URL=https://sports-data-admin.dock108.ai
SPORTS_API_INTERNAL_URL=http://api:8000

# Features
NEXT_PUBLIC_ENABLE_INLINE_X_VIDEO=true
```

Continue with server setup:

```bash
# Login to GHCR (use your GHCR_TOKEN)
echo YOUR_GHCR_TOKEN | docker login ghcr.io -u dock108 --password-stdin

# Pull initial images
cd infra
docker compose -f docker-compose.yml --profile prod pull

# Start database and redis first
docker compose -f docker-compose.yml --profile prod up -d postgres redis

# Wait for them to be healthy
sleep 10

# Run migrations
docker compose -f docker-compose.yml --profile prod run --rm migrate

# Start all services
docker compose -f docker-compose.yml --profile prod up -d

# Check status
docker compose -f docker-compose.yml --profile prod ps
```

### 3. Test the Deployment

Once the server is set up and GitHub secrets are configured:

1. Go to your repository's Actions tab
2. Click on "Backend CI/CD" workflow
3. Click "Run workflow" → "Run workflow" (manual trigger)
4. Watch the workflow execute

The workflow will:
- Detect changes
- Run tests
- Build and push Docker images to GHCR
- SSH into your server
- Pull updated images
- Run migrations (if API changed)
- Restart services
- Verify health checks

### 4. Verify Deployment

After deployment completes, check your services:

```bash
ssh root@37.27.222.59
cd /opt/sports-data-api/infra

# Check all services are running
docker compose -f docker-compose.yml --profile prod ps

# Check logs
docker compose -f docker-compose.yml --profile prod logs --tail=50 api
docker compose -f docker-compose.yml --profile prod logs --tail=50 web
docker compose -f docker-compose.yml --profile prod logs --tail=50 scraper

# Test API health
curl http://localhost:8000/healthz

# Test Web
curl http://localhost:3000
```

## Deployment Flow

```
Push to main
    ↓
Detect changes (api/web/scraper/infra)
    ↓
Run tests (if api/scraper changed)
    ↓
Build & push images to GHCR
    ↓
SSH to Hetzner server
    ↓
Login to GHCR
    ↓
Pull updated images
    ↓
Run migrations (if api/infra changed)
    ↓
Restart changed services
    ↓
Verify health checks
    ↓
Done!
```

## Troubleshooting

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for detailed troubleshooting steps.

Common issues:
- **SSH permission denied**: Check `DEPLOY_SSH_KEY` secret and server authorized_keys
- **Image pull fails**: Verify `GHCR_TOKEN` has correct permissions
- **Health check fails**: Check service logs and environment variables

## Manual Deployment

If you need to deploy manually without GitHub Actions:

```bash
ssh root@37.27.222.59
cd /opt/sports-data-api/infra

# Pull latest code
git pull origin main

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
```

## Next Steps After Setup

1. Set up nginx reverse proxy (see `infra/nginx/admin.conf`)
2. Configure SSL certificates with Let's Encrypt
3. Set up Cloudflare DNS to point to your server
4. Configure firewall rules
5. Set up monitoring and alerting

For more details, see:
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) - Complete deployment documentation
- [`docs/OPERATOR_RUNBOOK.md`](docs/OPERATOR_RUNBOOK.md) - Operations guide
- [`docs/INFRA.md`](docs/INFRA.md) - Infrastructure details
