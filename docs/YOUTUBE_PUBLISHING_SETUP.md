# YouTube Publishing Gateway Setup

Sprint 1A adds the secure connection and publication-domain foundation for YouTube publishing.

Required environment variables:

- `SOCIAL_TOKEN_ENCRYPTION_KEY`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REDIRECT_URI`
- `GOOGLE_OAUTH_FRONTEND_SUCCESS_URL`
- `GOOGLE_OAUTH_FRONTEND_ERROR_URL`

Recommended Google configuration:

1. Create a Google Cloud project for Story Engine staging.
2. Enable the YouTube Data API for that project.
3. Configure an OAuth consent screen.
4. Create a Web application OAuth client.
5. Register the exact backend callback URL in `GOOGLE_OAUTH_REDIRECT_URI`.
6. Add the corresponding frontend success/error URLs for post-callback redirection.

Current Sprint 1A scope:

- builds the Google authorization URL
- requests `youtube.upload` plus `youtube.readonly`
- uses `channels.list(mine=true)` after OAuth to resolve the actual YouTube channel identity
- stores encrypted tokens after callback
- creates draft publication jobs and frozen asset snapshots
- does not upload videos yet
- does not call YouTube from tests
