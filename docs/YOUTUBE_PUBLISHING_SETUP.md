# YouTube Publishing Gateway Setup

Sprint 1B extends the secure YouTube connection flow into a resumable upload and processing-reconciliation workflow.

Sprint 1C adds YouTube audit-readiness controls so Story Engine can safely keep private uploads available while blocking unlisted and public until an administrator records compliance approval.

Sprint 1D adds a full compliance submission profile, readiness requirement catalogue, evidence manifest, and exportable submission package so an administrator can prepare a manual YouTube API compliance submission without exposing secrets.

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

Submission profile:

- Store only non-secret reviewer-facing metadata.
- Expected fields include:
  - application display name
  - product description
  - organisation or individual developer name
  - support contact
  - privacy-policy URL
  - terms-of-service URL
  - application homepage URL
  - production OAuth redirect URI
  - production frontend URL
  - production API URL
  - data-retention summary
  - user-data deletion summary
  - token revocation summary
  - account-disconnection summary
  - quota-monitoring summary
  - incident-response summary
  - security-contact summary
  - submission case/reference ID
  - intended submission date
  - reviewed-by and review timestamp
  - optional non-secret notes
- Do not store tokens, credentials, client secrets, encryption keys, database URLs, private YouTube URLs, provider video IDs, resumable session URIs, or copied Google responses in the submission profile.

Readiness statuses:

- `pass`: implemented evidence or supplied metadata is present and meets the current technical requirement.
- `fail`: a blocking technical or documentation gap remains.
- `needs_confirmation`: Story Engine cannot truthfully complete or infer the requirement and a human must confirm it.
- `not_applicable`: the requirement does not currently apply to the stored workflow or evidence item.

Blocker severity:

- `blocking`: must be resolved before `audit_approved` can be recorded.
- `advisory`: important for reviewer completeness, but not treated as an approval gate on its own.
- `none`: the requirement is satisfied or informational.

Human confirmations:

- Human confirmations exist for items Story Engine cannot self-certify, such as legal review, policy review, operational review, and submission-package review.
- Completing OAuth or a private upload does not complete any human confirmation automatically.
- Clearing a confirmation is allowed when the underlying evidence is no longer current.

Evidence manifest:

- Story Engine can list the manual evidence an administrator should capture, such as:
  - OAuth consent screen screenshots
  - YouTube Data API enablement
  - redirect URI configuration
  - upload UI and visibility blocking screenshots
  - disconnect/revocation UI
  - privacy, terms, and support pages
  - deletion instructions
  - quota-monitoring evidence
  - incident-response process evidence
- The manifest records whether each item is required, why it matters, acceptable evidence, current state, and whether human action is still required.
- Story Engine does not store screenshots or legal documents in this sprint.

Export formats:

- JSON submission package for structured review.
- Markdown submission package for human-readable review.
- Concise checklist Markdown for manual completion outside Story Engine.

Approval guard:

- Story Engine blocks `audit_approved` until all blocking readiness failures are resolved.
- Required conditions include:
  - explicit administrator confirmation
  - confirmation that only Google can grant approval
  - a non-empty case/reference identifier
  - an approval date
  - non-localhost production URLs
  - privacy-policy URL
  - terms-of-service URL
  - support contact
  - documented deletion and revocation behaviour
  - completed mandatory human confirmations
- If any blocker remains, the backend returns `youtube_compliance_readiness_incomplete`.

Why Story Engine cannot infer approval:

- OAuth success proves only that a channel granted the requested scopes.
- A private upload proves only that the technical upload path worked for the connected project.
- Neither event proves that Google approved the project for unlisted or public distribution.
- Story Engine therefore treats audit approval as an explicit administrative record backed by human review.

Preparing a manual submission:

1. Complete the non-secret submission profile.
2. Review the grouped readiness requirements and resolve blocking failures.
3. Complete every mandatory human confirmation.
4. Export the JSON or Markdown package for internal review.
5. Export the checklist and gather the manual evidence listed in the evidence manifest.
6. Submit the actual compliance materials to Google outside Story Engine.
7. Record `audit_pending` after submission.
8. Record `audit_approved` only after Google explicitly grants approval.

What humans must still verify:

- legal sufficiency of privacy and terms documents
- ownership and accuracy of support contacts
- production domains and redirect URIs
- deletion and revocation instructions
- quota-monitoring and incident-response process quality
- any statements required by Google that Story Engine cannot truthfully generate from code alone

Downgrading approval state:

- Return the project to `private_only` if approval is withdrawn, the Google project changes, or the recorded production/legal evidence becomes stale.
- Use `audit_pending` only when a real submission is in progress.

Keeping production and legal information current:

- Review the submission profile whenever production domains, support contacts, redirect URIs, privacy wording, terms wording, or operational processes change.
- Re-run the readiness evaluation after each change and before recording any status transition.
- Treat localhost or non-HTTPS production URLs as blockers rather than as acceptable production evidence.

Reference rule:

- Uploads using `videos.insert` from unverified API projects created after 28 July 2020 are restricted to private viewing until the project passes a compliance audit.
