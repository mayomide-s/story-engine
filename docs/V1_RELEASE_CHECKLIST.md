# V1 Release Checklist

## Docker Startup Checklist

- Confirm `.env` is set for the intended mode
- Run `docker-compose down`
- Run `docker-compose up --build`
- Confirm `backend`, `frontend`, `postgres`, `redis`, `celery_worker`, and `celery_beat` are running
- Confirm Postgres reports healthy

## Health Check Checklist

- Confirm `GET /health` returns `{"status":"ok"}`
- Confirm `GET /health/details` returns safe readiness details
- Confirm health details include DB, Redis, storage, provider, and configuration checks
- Confirm no secrets appear in health output

## Mock Run Checklist

- Use `VIDEO_PROVIDER=mock`
- Create a run from Dashboard
- Confirm the run pauses at `awaiting_review`
- Resume the run
- Confirm mock video generation completes
- Confirm Video Review plays the generated video
- Confirm Asset Library shows the completed asset

## Runway Run Checklist

- Use `VIDEO_PROVIDER=runway`
- Confirm Runway warning is visible before Resume
- Confirm the run pauses before paid generation
- Resume intentionally
- Confirm Celery polling completes safely
- Confirm video, thumbnail, and final URLs are registered
- Confirm no duplicate provider job is created for the same run

## Export Pack Checklist

- Open a completed asset or completed run
- Confirm export pack shows video URL, thumbnail URL, caption, hashtags, prompt, and quality data
- Confirm platform-specific posting sections render
- Confirm copy buttons work
- Confirm manual posting status and URLs persist after refresh

## Backup Checklist

- Preserve `.env`
- Confirm Postgres backup plan or `pg_dump` path is documented
- Confirm R2 bucket/configuration is documented
- Avoid deleting Docker volumes without intent
