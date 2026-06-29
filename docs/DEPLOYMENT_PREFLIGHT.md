# Deployment Preflight

## Purpose

This document prepares the current `v1` app for deployment planning without actually deploying it.

Current recommendation:

- Production mode: `VIDEO_PROVIDER=runway`, `STORAGE_PROVIDER=r2`
- Safe testing mode: `VIDEO_PROVIDER=mock`, `STORAGE_PROVIDER=r2`

## Required Services

Minimum required services:

- `frontend`
- `backend`
- `postgres`
- `redis`
- `celery_worker`

Optional but currently present in local compose:

- `celery_beat`

## Required Storage And Providers

- Cloudflare R2 for durable asset storage
- Runway API key for real paid video generation

## Required Environment Variables

Always required:

- `DATABASE_URL`
- `REDIS_URL`
- `VIDEO_PROVIDER`
- `STORAGE_PROVIDER`
- `VITE_API_BASE_URL`

Required for `STORAGE_PROVIDER=r2`:

- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME`
- `R2_PUBLIC_BASE_URL`

Required for `VIDEO_PROVIDER=runway`:

- `RUNWAY_API_KEY`

## Recommended Modes

Recommended production mode:

- `VIDEO_PROVIDER=runway`
- `STORAGE_PROVIDER=r2`

Safe testing mode:

- `VIDEO_PROVIDER=mock`
- `STORAGE_PROVIDER=r2`

## Migration Steps

Before a deployment cutover:

```bash
docker-compose exec backend alembic current
docker-compose exec backend alembic upgrade head
```

If using another runtime target, the equivalent requirement is:

- database reachable
- Alembic installed
- `alembic upgrade head` completed before traffic

Do not:

- delete the Postgres volume to solve migration confusion
- hand-edit `alembic_version` casually
- rewrite already-applied migrations in ways that break existing databases

## Health Check URLs

Basic liveness:

- `GET /health`

Detailed readiness:

- `GET /health/details`

Current detailed checks cover:

- database
- redis
- storage
- video provider
- configuration

## Worker And Celery Readiness

At minimum confirm:

- `celery_worker` process is running
- worker registers `app.workers.jobs.resume_pipeline_task`
- Redis is reachable
- backend and worker share the same `DATABASE_URL`, `REDIS_URL`, provider mode, and storage mode

Useful checks:

```bash
docker-compose logs celery_worker --tail=250
docker-compose logs backend --tail=250
docker-compose ps
```

## Production-Readiness Notes

### CORS and frontend/backend URL

The backend currently allows all origins.

Before a real internet-facing deployment, review whether CORS should remain permissive or be restricted to the deployed frontend origin.

### Public API base URL

Frontend builds need the correct public backend URL through:

- `VITE_API_BASE_URL`

Example:

- `https://api.example.com/api`

### R2 public URL

The app expects stable public asset URLs through:

- `R2_PUBLIC_BASE_URL`

Example:

- `https://cdn.example.com`

### Database persistence

Postgres must use persistent storage in any deployment.

Requirements:

- durable volume or managed database
- regular backups
- restore path tested separately

### Redis persistence or acceptable loss

Redis is used for Celery broker/backend.

Decide explicitly whether:

- Redis data loss is acceptable during restart, or
- Redis persistence is required for the deployment target

For this app, short-lived broker loss may be acceptable only if the operational team understands that in-flight work may need manual review.

### Celery worker process

A deployment is incomplete if `celery_worker` is not running.

Runway generation depends on:

- background polling
- upload follow-through
- post-generation quality and packaging steps

### Log inspection

Minimum useful logs:

```bash
docker-compose logs backend --tail=250
docker-compose logs celery_worker --tail=250
docker-compose logs postgres --tail=250
docker-compose logs redis --tail=250
```

## Backup Requirements

Back up:

- Postgres data
- `.env` stored outside git
- R2 bucket configuration and asset retention assumptions
- release tags used for rollback

## Secret-Handling Rules

- Never commit `.env`
- Never commit provider API keys
- Never commit R2 credentials
- Use `.env.example` placeholders only
- Keep production secrets in the deployment platform secret store or environment manager

## Rollback Plan Using Git Tags

Known release checkpoints:

- `v1.0-local-mvp`
- `v1.0.1-runway-verified`

Rollback example:

```bash
git fetch --tags
git checkout v1.0.1-runway-verified
```

Then:

- rebuild containers/images
- re-run migrations review if needed
- restart backend and worker with the intended environment

## Preflight Checklist

- `.env` values reviewed for target mode
- Postgres persistence confirmed
- Redis behavior understood
- R2 bucket and public base URL verified
- Runway key present for production mode
- Alembic migration plan confirmed
- backend `/health` returns ok
- backend `/health/details` returns ready checks without secrets
- `celery_worker` running and logging cleanly
