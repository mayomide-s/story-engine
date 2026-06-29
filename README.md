# AI Coding Story Engine MVP

This repository is the v1 stability checkpoint for the first end-to-end milestone:

`topic -> idea/script/storyboard -> review pause -> Runway generation -> Celery polling -> MP4 download -> thumbnail -> R2 upload -> quality check -> approved video -> manual posting package -> completed run`

## Stack

- Frontend: React + Vite
- Backend: FastAPI + SQLAlchemy + Alembic
- Queue: Celery + Redis
- Database: PostgreSQL
- Storage: local filesystem or Cloudflare R2
- Video providers: `mock` and `runway`

## Configuration

Copy `.env.example` to `.env` and fill in only the values you need.

Important variables:

- `DATABASE_URL`
- `REDIS_URL`
- `VIDEO_PROVIDER`
- `STORAGE_PROVIDER`
- `RUNWAY_API_KEY`
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME`
- `R2_PUBLIC_BASE_URL`

## Modes

### Local mock mode

- Set `VIDEO_PROVIDER=mock`
- Set `STORAGE_PROVIDER=local`
- Start with `docker-compose up --build`

This is the cheapest and safest mode for normal development.

### Mock + R2 mode

- Set `VIDEO_PROVIDER=mock`
- Set `STORAGE_PROVIDER=r2`
- Fill in the R2 variables
- Start with `docker-compose up --build`

Use this when you want real R2 uploads without spending Runway credits.

### Runway + R2 mode

- Set `VIDEO_PROVIDER=runway`
- Set `STORAGE_PROVIDER=r2`
- Fill in `RUNWAY_API_KEY` and all R2 variables
- Start with `docker-compose up --build`

This is the real paid path.

## Credit Warning

Do not run `VIDEO_PROVIDER=runway` unless intentional.

Resuming a run in Runway mode can spend credits. The UI now shows a warning before Resume when `VIDEO_PROVIDER=runway`, and duplicate Resume should not submit a second Runway job for the same run.

## Runbook

### Start the stack

```bash
docker-compose up --build
```

The backend seeds `CodeToons AI` automatically on startup if missing.

### Create a run

From the UI:

- Open Dashboard
- Enter a topic such as `CORS`
- Click `Create Run`

From the API:

```bash
curl -X POST http://localhost:8000/api/pipeline-runs ^
  -H "Content-Type: application/json" ^
  -d "{\"topic\":\"CORS\",\"auto_mode\":false}"
```

The run will stop at storyboard review in `awaiting_review`.

### Resume a run

From the UI:

- Open Dashboard
- Select an `awaiting_review` run
- Click `Resume`

From the API:

```bash
curl -X POST http://localhost:8000/api/pipeline-runs/RUN_ID/resume ^
  -H "Content-Type: application/json" ^
  -d "{\"review_notes\":\"Approved from dashboard\"}"
```

### Re-run quality check without spending Runway credits

Use this when the assets already exist and you only want to re-run quality/manual package logic.

From the UI:

- Open `Video Review`
- Select a rejected or `needs_review` run with existing assets
- Click `Re-run Quality Check`

From the API:

```bash
curl -X POST http://localhost:8000/api/pipeline-runs/RUN_ID/recheck ^
  -H "Content-Type: application/json" ^
  -d "{\"review_notes\":\"Rechecked after quality logic change\"}"
```

This does not submit a new Runway job.

### Inspect logs

```bash
docker-compose logs backend --tail=250
docker-compose logs celery_worker --tail=250
docker-compose logs celery_beat --tail=250
```

## Known Safe Commands

```bash
docker-compose up --build
docker-compose down
docker-compose logs backend --tail=250
docker-compose logs celery_worker --tail=250
pytest -q
npm run build
```

## Cleanup

There is no archive/delete UI in this checkpoint. Use cleanup commands intentionally instead of building a management layer yet.

Examples:

```bash
docker-compose down
docker volume ls
docker ps -a
```

For application-level cleanup, use SQL or a DB client carefully against local development data only.

## API Endpoints

- `POST /api/pipeline-runs`
- `GET /api/pipeline-runs`
- `GET /api/pipeline-runs/{id}`
- `POST /api/pipeline-runs/{id}/resume`
- `POST /api/pipeline-runs/{id}/recheck`
- `POST /api/pipeline-runs/{id}/cancel`
- `PATCH /api/pipeline-runs/{id}/idea`
- `PATCH /api/pipeline-runs/{id}/script`
- `PATCH /api/pipeline-runs/{id}/storyboard`

## Notes

- `POST /api/pipeline-runs` defaults to `auto_mode=false`.
- Prompt logs redact secrets, API keys, access tokens, signed URLs, and provider credentials before persistence.
- `VIDEO_PROVIDER=mock` is still the default and recommended default for development.
