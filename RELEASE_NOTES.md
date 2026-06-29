# V1 Release Notes

## Summary

This release marks the `v1 local MVP` for AI coding mini-story production.

The app supports planning, generating, reviewing, storing, exporting, and manually posting short-form coding videos through a local-first workflow.

`v1.0.1-runway-verified` adds one verified paid-provider checkpoint on top of the local MVP:

- Runway/R2 regression verified end to end
- Prompt compaction added for the Runway `promptText` size limit
- Exactly one successful Runway job was submitted after the fix
- R2 upload, quality check, Video Review, Asset Library, and Export Pack were all re-verified
- Local `.env` should be returned to safe `mock/r2` mode after paid-provider testing

## V1 Feature Set

- Dashboard for creating and tracking pipeline runs
- Ideas review page for editing idea, script, storyboard, and prompt inputs before paid generation
- Video Review page for asset playback, quality checks, events, and export/manual posting controls
- Idea Queue and manual content calendar for planning future content
- Asset Library for browsing completed/generated videos and their metadata
- Export pack workflow for manual posting on TikTok, Instagram Reels, and YouTube Shorts
- Brand defaults and batch planning controls
- Mock and Runway video provider support behind the same provider abstraction
- Local filesystem and Cloudflare R2 storage support
- Health and readiness endpoints plus an in-app environment/status panel

## Supported Modes

- `mock/local`
- `mock/r2`
- `runway/r2`

## Known Limitations

- This is a manual posting workflow only
- No auto-posting or social API publishing
- No analytics or reporting dashboards
- No login, auth, subscriptions, or multi-user management
- Runway generation remains single-run and review-gated, not bulk-paid generation
- The app is designed as a stable local MVP, not a production SaaS deployment

## Runway Cost Warning

- `VIDEO_PROVIDER=runway` can spend real credits when a run is resumed
- Do not enable Runway mode unless intentional
- Duplicate Resume is guarded to avoid creating a second provider job for the same run
- After any paid-provider regression test, return local `.env` to `VIDEO_PROVIDER=mock` unless you intentionally need Runway mode again

## Safe Startup Commands

```bash
docker-compose up --build
docker-compose down
docker-compose logs backend --tail=250
docker-compose logs celery_worker --tail=250
pytest -q
npm run build
```

## Backup Reminders

- Preserve `.env` separately and treat it as sensitive
- Back up Postgres volume/data before risky migration or cleanup work
- Preserve Cloudflare R2 bucket configuration and public asset URLs
- Do not delete local Postgres volumes unless intentional
