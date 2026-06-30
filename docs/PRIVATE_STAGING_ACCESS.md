# Private Staging Access

This project now supports a lightweight private access mode for solo-developer staging.

It is intentionally narrow in scope:

- Good for a private MVP behind one shared password
- Good for protecting staging routes and UI access
- Not a replacement for real multi-user authentication

## Environment Variables

Required when private access is enabled:

- `AUTH_ENABLED=true`
- `APP_ACCESS_PASSWORD=strong-private-password`

Recommended for staging:

- `APP_SESSION_SECRET=separate-signing-secret`

Always configure CORS explicitly:

- `CORS_ALLOWED_ORIGINS=https://your-frontend-origin.example.com`

Local development can keep:

- `AUTH_ENABLED=false`

## How It Works

When `AUTH_ENABLED=false`:

- Local development behaves as before
- Existing pipeline, idea queue, asset library, settings, and export flows stay open locally

When `AUTH_ENABLED=true`:

- The frontend shows a simple access screen first
- Successful login stores a signed access token in browser local storage
- Protected backend APIs require a valid bearer token
- Logout clears the local token

Protected APIs include:

- `/api/pipeline-runs`
- `/api/idea-queue`
- `/api/asset-library`
- `/api/settings`

Public/safe endpoints remain:

- `/health`
- `/health/details`
- `/api/access/status`
- `/api/access/login`

## Why This Is Not Full SaaS Auth Yet

This groundwork is intentionally not:

- public signup
- team/user management
- OAuth/social login
- roles/permissions
- billing/subscriptions

Before any public launch, add a real auth and security model.

## CORS Guidance

Local:

- `CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`

Private staging:

- use only the exact frontend origin(s)
- do not leave wildcard origins enabled

## What Not To Commit

Never commit:

- `.env`
- real `APP_ACCESS_PASSWORD`
- real `APP_SESSION_SECRET`
- `RUNWAY_API_KEY`
- R2 access keys or secrets

Keep only safe placeholders in `.env.example`.
