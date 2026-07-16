# Managed Production Deployment

This guide prepares Story Engine for the approved managed-services production shape without deploying it.

## Approved Architecture

- Region: `lon1`
- Droplet: `story-engine-prod-01`
- Managed PostgreSQL: `story-engine-prod-pg`
- Managed Valkey: `story-engine-prod-valkey`
- Cloudflare Free initially for DNS and HTTPS proxying
- Cloudflare R2 bucket: `story-engine-prod-assets`

Approved public hosts:

- frontend: `https://storyengine.soremekun.org`
- API: `https://api.storyengine.soremekun.org`
- assets: `https://assets.storyengine.soremekun.org`
- OAuth callback: `https://api.storyengine.soremekun.org/api/social-connections/youtube/callback`

## Existing Deployment Gap

The repository already had:

- a local development stack with Postgres and Redis containers
- a VPS-oriented stack that still started local `postgres` and `redis`
- separate API startup and migration commands
- Cloudflare/R2-aware runtime settings

The missing production piece was a dedicated Compose stack for a Droplet that only runs:

- reverse proxy
- frontend
- backend API
- Celery worker

while connecting to externally managed PostgreSQL, Valkey, and R2.

## Managed Production Compose

Use:

- `docker-compose.managed.prod.yml`

The managed production stack intentionally excludes:

- local PostgreSQL containers
- local Redis or Valkey containers
- `celery_beat`
- development-only port exposure

Only the reverse proxy publishes:

- `80`
- `443`

The frontend and backend stay Docker-internal.

## Environment Template

Use:

- `.env.production.example`

Copy it to a local secret file such as:

- `.env.production`

Do not commit the real file.

Important verified runtime values:

- `VITE_API_BASE_URL=https://api.storyengine.soremekun.org/api`
  because the frontend client appends endpoint paths directly to the configured API base.
- `CORS_ALLOWED_ORIGINS=https://storyengine.soremekun.org`
- `ALLOWED_HOSTS=storyengine.soremekun.org,api.storyengine.soremekun.org`
- `RUN_MIGRATIONS_ON_STARTUP=false`
- `REQUIRE_SCHEMA_UP_TO_DATE=true`
- `R2_PUBLIC_BASE_URL=https://assets.storyengine.soremekun.org`

## What Must Not Be Copied From Local Development

Do not copy these into production:

- active YouTube OAuth tokens
- app session rows
- pilot publication records
- development encryption keys
- development passwords
- local database dumps
- development `.env` files

## Reverse Proxy

Template file:

- `deploy/nginx/managed-prod.conf.template`

It is prepared for:

- `storyengine.soremekun.org`
- `api.storyengine.soremekun.org`

Routes:

- frontend host serves `/`, `/privacy`, `/terms`, `/data-deletion`, `/app`, and built frontend assets
- API host proxies `/api/*`, `/health`, and `/health/details`

The frontend container already provides SPA history fallback, so direct loads of:

- `/`
- `/privacy`
- `/terms`
- `/data-deletion`
- `/app`

continue to work through the reverse proxy.

TLS notes:

- Cloudflare will later proxy the public hosts
- origin TLS certificate and key paths are placeholders only
- Cloudflare SSL mode is expected to be `Full (strict)` later
- do not add real certificates to the repository

## Migration Flow

The normal production stack must not auto-run migrations.

Use the one-off ops profile services instead:

Configuration validation:

```bash
./scripts/managed-prod-config-check.sh .env.production
```

Current revision:

```bash
./scripts/managed-prod-migrate.sh .env.production current
```

Upgrade once:

```bash
./scripts/managed-prod-migrate.sh .env.production upgrade
```

This avoids API-replica migration races.

Rollback for schema mistakes should rely on:

- managed database restore
- point-in-time recovery when available

Do not improvise destructive downgrades against a live production database.

## Build And Runtime Commands

Build images:

```bash
./scripts/managed-prod-build.sh .env.production
```

Start the stack:

```bash
docker compose --env-file .env.production -f docker-compose.managed.prod.yml up -d reverse_proxy frontend backend celery_worker
```

View logs:

```bash
docker compose --env-file .env.production -f docker-compose.managed.prod.yml logs --tail=250
docker compose --env-file .env.production -f docker-compose.managed.prod.yml logs -f backend celery_worker reverse_proxy frontend
```

Stop the stack:

```bash
docker compose --env-file .env.production -f docker-compose.managed.prod.yml down
```

Restart API only:

```bash
docker compose --env-file .env.production -f docker-compose.managed.prod.yml up -d --no-deps backend
```

Restart worker only:

```bash
docker compose --env-file .env.production -f docker-compose.managed.prod.yml up -d --no-deps celery_worker
```

Health checks:

```bash
./scripts/managed-prod-health-check.sh https://api.storyengine.soremekun.org
```

## Health Expectations

Reverse proxy:

- internal `/nginx-health`

Frontend:

- static root responds through the internal Nginx container

Backend:

- `GET /health`
- `GET /health/details`

Worker:

- process alive
- expected Celery tasks loaded in the application module set

These checks must not trigger provider uploads or expensive external work.

## Production Validation Rules

Production-like startup now fails closed when:

- `DATABASE_URL` is missing or still points to SQLite
- `REDIS_URL` is missing or still uses insecure non-TLS Redis
- `SESSION_COOKIE_SECURE` is not enabled
- wildcard CORS is configured
- approved hosts are missing
- `R2_PUBLIC_BASE_URL` is not HTTPS when `STORAGE_PROVIDER=r2`
- trusted proxy CIDRs are missing while proxy-header trust is enabled
- OAuth redirect URLs use HTTP outside local development

Mock video providers are still allowed intentionally for review-only production rehearsals. The managed production Compose template defaults to `runway`, but the backend does not forbid deliberate `mock/r2` review mode.

## R2 Safeguards

- R2 credentials remain backend-only
- the frontend never receives R2 credentials
- durable public asset URLs must use `https://assets.storyengine.soremekun.org`
- the Droplet working-media volume is temporary and not canonical storage
- failed uploads must be recoverable through existing backend logic and logs
- deletion failures should be surfaced in logs without exposing secrets

## Backup And Configuration References

Before a real deployment:

1. back up the managed database through the provider workflow
2. back up `.env.production` outside git
3. capture the rendered Compose config:

```bash
docker compose --env-file .env.production -f docker-compose.managed.prod.yml config > managed-prod-rendered.yml
```

4. record:
   - deployed git SHA
   - built image tags or digests
   - managed database cluster name
   - managed Valkey cluster name
   - R2 bucket name

Do not commit rendered configs that contain real secrets.

## Rollback To Prior Images

Recommended rollback posture:

1. keep the previous backend/frontend image tags or digests
2. restore the previous `.env.production` only if configuration changed
3. restore the database from managed backup only if schema/data rollback is genuinely required
4. restart the affected service or the full stack with the prior images

Do not rely on ad hoc destructive database downgrades for emergency rollback.

## DNS And HTTPS Order

When real deployment time comes later:

1. provision the Droplet, managed PostgreSQL, managed Valkey, and R2
2. verify internal health before public traffic
3. configure origin TLS material for the reverse proxy
4. point Cloudflare DNS records
5. verify HTTPS through Cloudflare
6. only then update Google OAuth production settings

Google OAuth production changes must happen only after HTTPS is working on:

- `https://storyengine.soremekun.org`
- `https://api.storyengine.soremekun.org`
- `https://api.storyengine.soremekun.org/api/social-connections/youtube/callback`
