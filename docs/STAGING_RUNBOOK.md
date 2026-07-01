# Staging Runbook

## Purpose

This runbook documents the current private staging operations flow for Story Engine / CodeToons AI.

Use it for:

- safe deploys
- safe mock mode verification
- one-off Runway tests
- rollback
- health checks
- HTTPS/domain checks

This document does not include secrets.

## Current Staging Targets

- Public URL: `https://story.soremekun.org`
- VPS IP: `144.126.234.61`
- App path on VPS: `/opt/story-engine`
- Main branch: `master`

## Current Stack

- Host Nginx terminates HTTPS
- Host Nginx proxies:
  - `/api/` to backend
  - `/health` to backend
  - `/health/details` to backend
  - `/` to frontend
- Frontend runs as a static production build served by an Nginx container
- Backend runs in Docker on `127.0.0.1:8001 -> container 8000`
- Frontend runs in Docker on `127.0.0.1:5174 -> container 80`
- Postgres and Redis run as internal Docker services
- `STORAGE_PROVIDER=r2`
- `VIDEO_PROVIDER` should normally stay `mock`
- Runway is available but must only be enabled intentionally

## Key Compose Files

- `docker-compose.vps.prod.yml`
- `docker-compose.vps.env.yml`

Notes:

- `docker-compose.vps.prod.yml` is the committed base VPS stack
- `docker-compose.vps.env.yml` may be VPS-local and untracked
- do not delete VPS-local compose overrides casually

## Important `.env` Values To Check

Verify these values before deploys or provider changes:

- `VIDEO_PROVIDER`
- `STORAGE_PROVIDER`
- `VITE_API_BASE_URL=/api`
- `AUTH_ENABLED`
- `R2_PUBLIC_BASE_URL`

Recommended steady-state staging values:

- `VIDEO_PROVIDER=mock`
- `STORAGE_PROVIDER=r2`
- `VITE_API_BASE_URL=/api`
- `AUTH_ENABLED=true`

## Safe Deploy Command

Run from `/opt/story-engine`:

```bash
git fetch origin
git checkout master
git reset --hard origin/master
docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml up -d --build backend celery_worker frontend
```

Warnings:

- do not run `git clean -fd` on the VPS
- untracked VPS compose/env files may be important
- create a database backup before deployments that involve migrations or schema risk

## Database Backups

Backups are stored outside the repo at:

```bash
/root/story-engine-backups/db
```

Create a manual backup:

```bash
./scripts/vps-db-backup.sh
```

List backups:

```bash
ls -lh /root/story-engine-backups/db
```

The backup script:

- runs from `/opt/story-engine`
- creates the backup directory if missing
- writes a timestamped Postgres dump
- gzips the dump
- keeps the newest 14 backups
- deletes older backups automatically

Restore the latest backup:

```bash
./scripts/vps-db-restore-latest.sh
```

Warning:

- restore overwrites the staging database
- the restore script requires typing `RESTORE` exactly
- take a fresh backup before restoring if there is any doubt

## Health Checks

Public health checks:

```bash
curl -i https://story.soremekun.org/health
curl -i https://story.soremekun.org/health/details
```

Expected:

- `/health` returns `200`
- `/health/details` returns safe readiness details without secrets

Useful local checks on the VPS:

```bash
curl -i http://127.0.0.1:8001/health
curl -i http://127.0.0.1:8001/health/details
curl -I http://127.0.0.1:5174/
```

## How To Confirm Safe Mock Mode

Check `.env`:

```bash
grep -E '^(VIDEO_PROVIDER|STORAGE_PROVIDER|VITE_API_BASE_URL|AUTH_ENABLED)=' .env
```

Expected safe staging state:

```bash
VIDEO_PROVIDER=mock
STORAGE_PROVIDER=r2
VITE_API_BASE_URL=/api
AUTH_ENABLED=true
```

Then restart the app-facing services:

```bash
docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml up -d --build backend celery_worker frontend
```

## How To Switch To Runway For Exactly One Controlled Test

1. Edit `.env`
2. Set:

```bash
VIDEO_PROVIDER=runway
STORAGE_PROVIDER=r2
VITE_API_BASE_URL=/api
```

3. Restart only the app-facing services:

```bash
docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml up -d --build backend celery_worker frontend
```

4. Confirm readiness:

```bash
curl -i https://story.soremekun.org/health
curl -i https://story.soremekun.org/health/details
```

5. Run exactly one reviewed resume in the UI
6. Confirm only one provider job is created
7. Watch backend and worker logs during the test

## How To Immediately Switch Back To Mock

Edit `.env` back to:

```bash
VIDEO_PROVIDER=mock
STORAGE_PROVIDER=r2
VITE_API_BASE_URL=/api
```

Then restart:

```bash
docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml up -d --build backend celery_worker frontend
```

## Log Commands

Backend:

```bash
docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml logs backend --tail=250
```

Frontend:

```bash
docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml logs frontend --tail=250
```

Worker:

```bash
docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml logs celery_worker --tail=250
```

Follow mode:

```bash
docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml logs -f backend celery_worker frontend
```

## How To Confirm Frontend Is Static Nginx, Not Vite Dev Server

Check container port response headers:

```bash
curl -I http://127.0.0.1:5174/
```

Expected:

- `Server: nginx`
- no Vite blocked-host page

Optional content check:

```bash
curl http://127.0.0.1:5174/ | head
```

If you see Vite host-block text, the wrong frontend container/runtime is active.

## Rollback To Known Tags

Available rollback tags:

- `v2.4.0-runway-visual-prompts`
- `v2.4.1-provider-aware-review`
- `v2.4.2-runway-resume-safety`
- `v2.4.3-https-staging-domain`
- `v2.4.4-static-frontend`

Example rollback:

```bash
git fetch --tags
git checkout v2.4.4-static-frontend
docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml up -d --build backend celery_worker frontend
```

To return to current `master` later:

```bash
git checkout master
git reset --hard origin/master
docker compose --env-file .env -f docker-compose.vps.prod.yml -f docker-compose.vps.env.yml up -d --build backend celery_worker frontend
```

Rollback reminder:

- code rollback and database rollback are separate actions
- if a deployment includes migrations, make a DB backup before deploy
- restoring a DB backup can overwrite newer staging data

## HTTPS / Certbot Check

Dry-run renewal:

```bash
sudo certbot renew --dry-run
```

Also verify host Nginx reloads cleanly after any cert or config work.

## Domain And Routing Checks

Confirm these public routes work:

```bash
curl -I https://story.soremekun.org/
curl -I https://story.soremekun.org/health
curl -I https://story.soremekun.org/health/details
```

Confirm raw-IP fallback can still reach the frontend if needed:

```bash
curl -I http://144.126.234.61:5174/
```

## Operational Safety Warnings

- Never paste secrets into logs, screenshots, tickets, or chat.
- Never commit `.env`.
- Do not run `git clean -fd` on the VPS.
- Do not enable Runway casually.
- Switch back to `VIDEO_PROVIDER=mock` after any paid-provider test unless you intentionally want staging left in Runway mode.
