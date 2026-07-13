# YouTube Publishing Gateway Setup

Sprint 1B extends the secure YouTube connection flow into a resumable upload and processing-reconciliation workflow.

Sprint 1C adds YouTube audit-readiness controls so Story Engine can safely keep private uploads available while blocking unlisted and public until an administrator records compliance approval.

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

YouTube compliance statuses:

- `private_only`: safe default for new and existing projects. Private uploads remain available; unlisted/public stay blocked.
- `audit_pending`: use after a compliance submission has been sent but before approval is recorded. Private uploads remain available; unlisted/public stay blocked.
- `audit_approved`: use only after an administrator explicitly records that YouTube API compliance approval has been granted. Unlisted/public become selectable for future jobs.
- `unknown`: available when the administrator cannot safely confirm the project state. Story Engine still blocks unlisted/public.

Why OAuth success is not audit approval:

- A connected channel proves only that the user completed OAuth and granted scopes.
- It does not prove that the Google API project has passed the YouTube compliance audit.
- Story Engine therefore keeps `private_only` as the safe default until an administrator records a different status.

Administrative workflow:

1. Connect the channel through the existing YouTube OAuth flow.
2. Record `audit_pending` after submitting the YouTube compliance materials.
3. Record `audit_approved` only after approval is granted.
4. Return the project to `private_only` if approval is withdrawn or the project configuration changes.

Audit-readiness report:

- Story Engine can generate a structured audit-readiness report in JSON or Markdown.
- The report captures implemented behaviour such as scopes, consent flow, token encryption, visibility blocking, retry/idempotency protections, and publication audit logging.
- The report also highlights what a human still needs to provide, such as privacy-policy URLs, support contacts, and formal compliance submission references.

Reference rule:

- Uploads using `videos.insert` from unverified API projects created after 28 July 2020 are restricted to private viewing until the project passes a compliance audit.
