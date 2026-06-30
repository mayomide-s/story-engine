# VPS Staging Deployment

## Goal

This guide prepares a private single-VPS staging deployment for the current `v2.1` app without changing product behavior.

Recommended staging sequence:

- first: `VIDEO_PROVIDER=mock`, `STORAGE_PROVIDER=r2`
- second: `VIDEO_PROVIDER=runway`, `STORAGE_PROVIDER=r2`

## Recommended VPS Requirements

For a small private staging environment, a practical baseline is:

- 4 vCPU
- 8 GB RAM
- 80 to 160 GB SSD
- Ubuntu 22.04 LTS or Debian 12

Why:

- backend + frontend + Postgres + Redis + Celery worker all run together
- Runway polling and ffmpeg thumbnail/video inspection need some headroom
- Postgres volume growth and Docker image layers need disk margin

## Required Software On The Server

Install:

- `git`
- Docker Engine
- Docker Compose plugin
- optional: `nginx` or another reverse proxy
- optional: `ufw` or similar firewall

Useful verification commands:

```bash
git --version
docker --version
docker compose version
```

## Clone Repo

Example:

```bash
git clone https://github.com/mayomide-s/story-engine.git
cd story-engine
git fetch --tags
```

To pin staging to a known release:

```bash
git checkout v1.0.1-runway-verified
```

## Create `.env` From `.env.example`

On the server:

```bash
cp .env.example .env
```

Then fill in the required values for staging mode.

## Required Secrets

Always required:

- `DATABASE_URL`
- `REDIS_URL`
- `VIDEO_PROVIDER`
- `STORAGE_PROVIDER`
- `VITE_API_BASE_URL`

Required for R2:

- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME`
- `R2_PUBLIC_BASE_URL`

Required for Runway staging:

- `RUNWAY_API_KEY`

Required for private staging access:

- `AUTH_ENABLED=true`
- `APP_ACCESS_PASSWORD`
- optional `APP_SESSION_SECRET`
- `CORS_ALLOWED_ORIGINS`

Never commit `.env`.

## Docker Compose Startup

For a first staging boot:

```bash
docker-compose up --build -d
```

Inspect container state:

```bash
docker-compose ps
```

## Local Rehearsal Before VPS

You can rehearse a staging-like setup locally without touching the main dev stack by using:

- `docker-compose.staging.local.yml`
- alternate local ports: frontend `5174`, backend `8001`, Postgres `5433`, Redis `6380`

Example:

```bash
docker-compose -p sociopost_staginglocal -f docker-compose.staging.local.yml up --build -d
docker-compose -p sociopost_staginglocal -f docker-compose.staging.local.yml down
```

Recommended local rehearsal mode:

- `AUTH_ENABLED=true`
- `VIDEO_PROVIDER=mock`
- `STORAGE_PROVIDER=r2`

## Migration Flow

The backend startup script already runs Alembic on boot after DB readiness checks.

For explicit migration inspection:

```bash
docker-compose exec backend alembic current
docker-compose exec backend alembic upgrade head
docker-compose exec backend alembic history --verbose
```

Do not:

- delete Postgres volumes casually
- hand-edit `alembic_version` casually

## Health Checks

Basic health:

- `GET /health`

Detailed readiness:

- `GET /health/details`

Example:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/details
```

## Worker / Celery Checks

Confirm:

- `celery_worker` container is running
- worker logs show `app.workers.jobs.resume_pipeline_task`
- Redis is reachable

Useful commands:

```bash
docker-compose logs celery_worker --tail=250
docker-compose logs redis --tail=250
docker-compose ps
```

## Log Inspection Commands

```bash
docker-compose logs backend --tail=250
docker-compose logs celery_worker --tail=250
docker-compose logs postgres --tail=250
docker-compose logs redis --tail=250
docker-compose logs frontend --tail=250
```

## Domain / Subdomain Setup

Recommended pattern:

- staging frontend: `staging.example.com`
- staging API: `api-staging.example.com`

Or use one host with reverse proxy routing:

- `staging.example.com` -> frontend
- `staging.example.com/api/*` -> backend

Keep staging private or minimally exposed until auth/security work exists.

## HTTPS / Reverse Proxy Approach

Recommended simple path:

- Nginx or Caddy in front of frontend/backend
- TLS termination at the reverse proxy
- upstream forwarding to Docker services

If you use separate API and frontend subdomains, ensure:

- frontend `VITE_API_BASE_URL` points to the public API URL
- backend CORS is reviewed for the frontend origin

## Frontend `VITE_API_BASE_URL`

Set this to the public API base used by the browser.

Example:

- `https://api-staging.example.com/api`

## Backend CORS Allowed Origins

Set this explicitly for staging.

Recommended:

- only the frontend staging origin
- no wildcard origins

Example:

- `CORS_ALLOWED_ORIGINS=https://staging.example.com`

## R2 Public URL

Ensure:

- `R2_PUBLIC_BASE_URL` points to the public R2/custom domain URL that serves uploaded assets

Example:

- `https://cdn-staging.example.com`

## Postgres Volume Persistence

Postgres must use persistent storage.

At minimum:

- persistent Docker volume

Better later:

- managed external Postgres

## Redis / Celery Reliability Expectations

Redis is required for:

- Celery broker
- task result backend

Acceptable staging posture:

- Redis data loss during restart may be acceptable
- but expect in-flight task state to require manual inspection if Redis is interrupted

Celery worker must stay running for:

- Runway polling
- asset processing
- quality check continuation

## Staging Deployment Checklist

### Stage 1: mock/R2

- set `VIDEO_PROVIDER=mock`
- set `STORAGE_PROVIDER=r2`
- start stack
- confirm health endpoints
- create one mock run
- confirm asset upload to R2
- confirm Video Review, Asset Library, and Export Pack work

### Stage 2: runway/R2

- switch to `VIDEO_PROVIDER=runway`
- keep `STORAGE_PROVIDER=r2`
- restart stack
- run one paid Runway test only
- confirm exactly one provider job is submitted
- confirm quality check and asset registration complete

### After paid staging test

- return staging to `mock/r2` if you want a cheaper steady-state validation environment

## Backup Commands

Example Postgres logical backup:

```bash
docker-compose exec postgres pg_dump -U postgres sociopost > staging-backup.sql
```

Example container/volume inspection:

```bash
docker volume ls
docker-compose ps
```

## Server Backup Checklist

- Postgres backup captured
- `.env` backed up outside git
- R2 bucket configuration preserved
- release tag/commit recorded for rollback

## Rollback Using Git Tags

Known release checkpoints:

- `v1.0-local-mvp`
- `v1.0.1-runway-verified`
- `v2.0-review-quality`
- `v2.1-private-access`

Example rollback:

```bash
git fetch --tags
git checkout v1.0.1-runway-verified
docker-compose down
docker-compose up --build -d
```

## Generic Reverse Proxy Example

If useful, pair this guide with:

- `docs/examples/nginx-staging.example.conf`
