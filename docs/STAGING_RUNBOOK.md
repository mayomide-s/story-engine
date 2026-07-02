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

## R2 Asset Inventory

Remember:

- database backups do not back up R2 binary assets
- generated MP4s and thumbnails live in R2
- do not delete R2 objects manually unless DB references are handled too
- the weekly inventory check is read-only and does not back up R2 binary objects or delete unused files

Systemd automation on the VPS:

- timer: `story-engine-r2-inventory.timer`
- service: `story-engine-r2-inventory.service`
- schedule: weekly on Sunday at `04:15` UTC/server time

Check the timer:

```bash
systemctl list-timers --all | grep story-engine
```

Run the inventory manually:

```bash
systemctl start story-engine-r2-inventory.service
```

View recent service logs:

```bash
journalctl -u story-engine-r2-inventory.service -n 80 --no-pager
```

Run the inventory check:

```bash
./scripts/vps-r2-asset-inventory.sh
```

What it reports:

- R2 bucket name
- object count and total size for `videos/`
- object count and total size for `thumbnails/`
- DB asset record counts for `video_mp4` and `thumbnail`
- missing R2 objects referenced by DB
- at most the first 20 missing keys

Healthy result:

- non-zero counts for `videos/` and `thumbnails/` once staging has generated assets
- `Missing R2 objects referenced by DB: 0`

If missing keys are reported:

- do not delete more objects
- inspect the listed keys
- compare DB records, R2 inventory, and recent logs before making changes

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

## Security Baseline

Baseline staging VPS expectations:

- UFW firewall enabled
- allowed public ports:
  - `22/tcp` for SSH
  - `80/tcp` for HTTP
  - `443/tcp` for HTTPS
- Fail2ban enabled for SSH
- SSH password login disabled
- SSH key login required

Expected effective SSH settings:

- `PasswordAuthentication no`
- `KbdInteractiveAuthentication no`
- `PermitRootLogin without-password`
- `PubkeyAuthentication yes`

Useful checks:

```bash
ufw status numbered
fail2ban-client status
fail2ban-client status sshd
ss -tulpn | grep -E ':(22|80|443|8000|8001|5174|5432|6379)\b'
sshd -T | grep -Ei 'passwordauthentication|kbdinteractiveauthentication|permitrootlogin|pubkeyauthentication'
```

Healthy staging expectations:

- only `22`, `80`, and `443` should be publicly exposed
- backend, frontend container bind ports, Postgres, and Redis should stay private to localhost or Docker-internal networking
- SSH should reject password-based login attempts
- Fail2ban should show the `sshd` jail active

## Staging Release Checklist

Run the VPS-only read-only checklist from `/opt/story-engine`:

```bash
./scripts/vps-staging-release-check.sh
```

Run it before:

- staging deploys
- schema or infrastructure changes
- any controlled paid Runway test
- rollback verification
- troubleshooting after VPS security or Docker changes

Checklist result meanings:

- `PASS`: the check matched the expected staging baseline
- `WARN`: non-critical drift or missing context was detected and should be reviewed
- `FAIL`: a critical safety or readiness check failed

Important:

- this checklist is read-only
- it does not deploy, rebuild, back up data, restore data, modify `.env`, or enable Runway
- it is intended to catch unsafe staging state before changes are made

## Demo Readiness

Run the demo check from `/opt/story-engine`:

```bash
bash scripts/vps-demo-readiness-check.sh
```

Run it:

- before showing the app live
- before recording a demo
- before sharing staging with someone else

What it checks:

- the staging release checklist passes first
- the app is still in safe `mock/r2` mode
- the golden demo Runway video object exists in R2
- the golden demo thumbnail object exists in R2
- the R2 inventory still reports zero DB-referenced missing objects

Important:

- this check is read-only
- it does not deploy, rebuild, enable Runway, or change `.env`
- Runway should remain disabled unless you intentionally open a paid test window

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

Use the guarded paid-test window instead of editing `.env` by hand when possible.

## Controlled Runway Paid Test

Warning:

- Runway generation costs real money
- this only opens a temporary provider window
- it does not generate a video automatically

Open a default 30-minute window:

```bash
CONFIRM_RUNWAY_COST=YES bash scripts/vps-runway-paid-test-window.sh
```

Open a shorter 15-minute window:

```bash
CONFIRM_RUNWAY_COST=YES bash scripts/vps-runway-paid-test-window.sh 15
```

Manual rollback:

```bash
bash scripts/vps-safe-mock-mode.sh
```

Post-test safety check:

```bash
bash scripts/vps-staging-release-check.sh
```

What the paid-test window script does:

- runs the staging release checklist first
- verifies staging is still in safe `mock/r2` mode before switching
- verifies Runway and R2 config exists without printing secrets
- backs up `.env`
- changes only `VIDEO_PROVIDER=runway`
- restarts `backend` and `celery_worker`
- verifies `/health/details` shows `runway/r2` readiness
- schedules an automatic rollback to mock mode when `systemd-run` is available

If you still need to switch manually:

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
