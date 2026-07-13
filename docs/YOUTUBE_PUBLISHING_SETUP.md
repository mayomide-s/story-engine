# YouTube Publishing Gateway Setup

Sprint 1B extends the secure YouTube connection flow into a resumable upload and processing-reconciliation workflow.

Required environment variables:

- `SOCIAL_TOKEN_ENCRYPTION_KEY`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REDIRECT_URI`
- `GOOGLE_OAUTH_FRONTEND_SUCCESS_URL`
- `GOOGLE_OAUTH_FRONTEND_ERROR_URL`
- `YOUTUBE_DEFAULT_CATEGORY_ID`
- `YOUTUBE_UPLOAD_CHUNK_SIZE_BYTES`
- `YOUTUBE_TOKEN_REFRESH_LEEWAY_SECONDS`
- `YOUTUBE_CLAIM_TIMEOUT_SECONDS`
- `YOUTUBE_MAX_RETRY_ATTEMPTS`
- `YOUTUBE_POLL_INTERVAL_SECONDS`
- `YOUTUBE_MAX_POLL_ATTEMPTS`

Recommended Google configuration:

1. Create a Google Cloud project for Story Engine staging.
2. Enable the YouTube Data API for that project.
3. Configure an OAuth consent screen.
4. Create a Web application OAuth client.
5. Register the exact backend callback URL in `GOOGLE_OAUTH_REDIRECT_URI`.
6. Add the corresponding frontend success/error URLs for post-callback redirection.

Current Sprint 1B scope:

- builds the Google authorization URL
- requests `youtube.upload` plus `youtube.readonly`
- uses `channels.list(mine=true)` after OAuth to resolve the actual YouTube channel identity
- stores encrypted tokens after callback
- creates draft publication jobs and frozen asset snapshots
- uploads the frozen selected MP4 through YouTube resumable upload
- persists the YouTube video ID before processing reconciliation
- polls `videos.list` until the upload is confirmed private, unlisted, public, failed, or uncertain
- creates exactly one `PlatformPost` only for confirmed unlisted/public uploads
- keeps resumable session URIs encrypted at rest
- requires Redis-backed Celery workers for asynchronous execution
- does not call YouTube from tests

Operational notes:

- New or unverified Google projects may force uploads to remain private.
- Story Engine treats those results as `uploaded_private` and does not create a `PlatformPost`.
- Retry and reconciliation never create a second upload after a provider video ID has been persisted.
- The worker queue must be running anywhere you expect uploads or polling to progress.
