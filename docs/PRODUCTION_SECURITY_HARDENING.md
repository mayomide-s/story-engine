# Production Security Hardening

This document describes the production-oriented security controls added for Story Engine before a Cloudflare-fronted deployment.

## Session Model

- Browser authentication now uses a server-managed opaque session stored in PostgreSQL.
- The browser receives the raw session token only through the `SESSION_COOKIE_NAME` HTTP-only cookie.
- Story Engine stores only a cryptographic hash of the session token in the database.
- The raw session token is never returned in JSON and must not be stored in `localStorage` or `sessionStorage`.
- Session records store:
  - account ownership
  - expiry
  - last-used timestamp
  - revocation timestamp and reason
  - a small metadata payload for non-secret session context

## Cookie Configuration

Relevant variables:

- `SESSION_COOKIE_NAME`
- `SESSION_COOKIE_DOMAIN`
- `SESSION_COOKIE_MAX_AGE_SECONDS`
- `SESSION_COOKIE_SAMESITE`
- `SESSION_COOKIE_SECURE`

Production expectations:

- `HttpOnly`
- `Secure`
- `SameSite=Lax`
- host-only cookie scope unless a broader domain is intentionally required

Local development may omit the secure-cookie flag automatically when `ENVIRONMENT` is development-like. Production must keep secure cookies enabled.

## CSRF Protection

- Authenticated state-changing API routes require an `X-CSRF-Token` header by default.
- The CSRF token is tied to the current server-side session.
- Missing or invalid CSRF tokens are rejected with a `403` and code `csrf_validation_failed`.
- Unknown browser origins are rejected before a valid authenticated mutation is processed.
- Logout uses an idempotent variant so an already-expired session can still clear the cookie safely.

## Session Expiry And Revocation

Sessions are rejected when:

- the account is deleted
- the account is in a non-active state
- the session expires
- the session is explicitly revoked
- the primary access password changes and the session fingerprint no longer matches

Revocation reasons currently include:

- `logout`
- `logout_all`
- `account_deleted`
- `account_disabled`
- `password_changed`
- `security_forced_logout`
- `expired`

Account deletion revokes every active Story Engine session for the account before completing the tombstone flow.

## Trusted Hosts

Relevant variables:

- `ALLOWED_HOSTS`
- `TRUST_PROXY_HEADERS`
- `TRUSTED_PROXY_CIDRS`

Production should explicitly allow only the approved public hosts:

- `storyengine.soremekun.org`
- `api.storyengine.soremekun.org`

Do not use wildcard host allowances in production.

## Proxy And Cloudflare Assumptions

Story Engine is designed to sit behind Cloudflare and an origin reverse proxy later.

Operational assumptions:

- HTTPS terminates before requests reach the application origin
- direct-origin access is restricted by firewall rules
- forwarded headers are trusted only when `TRUST_PROXY_HEADERS=true`
- trusted proxies must be listed in `TRUSTED_PROXY_CIDRS`
- authenticated API traffic should bypass edge caching
- public legal pages may be cached separately at the edge if desired

Recommended origin protections for a later deployment:

- allow inbound traffic only from the reverse proxy or Cloudflare-proxied path
- forward a request ID header from the edge or reverse proxy
- log only sanitized request metadata

## CORS

Relevant variable:

- `CORS_ALLOWED_ORIGINS`

Production should set this to the exact frontend origin:

- `https://storyengine.soremekun.org`

Credentialed CORS with wildcard origins is rejected by configuration validation.

## Rate Limits

Story Engine now supports configurable application-layer limits for sensitive operations.

Relevant variables:

- `LOGIN_RATE_LIMIT_ATTEMPTS`
- `LOGIN_RATE_LIMIT_WINDOW_SECONDS`
- `SENSITIVE_RATE_LIMIT_ATTEMPTS`
- `SENSITIVE_RATE_LIMIT_WINDOW_SECONDS`
- `PUBLICATION_RATE_LIMIT_ATTEMPTS`
- `PUBLICATION_RATE_LIMIT_WINDOW_SECONDS`
- `COMPLIANCE_WRITE_RATE_LIMIT_ATTEMPTS`
- `COMPLIANCE_WRITE_RATE_LIMIT_WINDOW_SECONDS`

Covered operations include:

- login
- account deletion validation
- account deletion execution
- YouTube authorization initiation
- publication job creation
- publication target retry
- YouTube compliance write endpoints

Production should keep additional Cloudflare edge rate limits for the same high-risk paths. Application limits remain necessary even when Cloudflare sits in front of the origin.

## Production Startup And Migrations

The API startup path no longer assumes migrations should always run.

Relevant variable:

- `RUN_MIGRATIONS_ON_STARTUP`

Behaviour:

- development-like environments default to running migrations on startup
- production-like environments default to skipping automatic migrations
- the application can validate that the database is already at the Alembic head through `REQUIRE_SCHEMA_UP_TO_DATE`

Explicit commands:

- migration step: `sh backend/migrate.sh`
- API step: `sh backend/start-api.sh`
- compatibility wrapper: `sh backend/start.sh`

Recommended production order:

1. run migrations once
2. start API processes
3. start Celery worker processes

Do not rely on multiple API replicas racing to run Alembic.

## Worker Startup

The worker still uses the existing Celery command surface:

```bash
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

Keep API and worker processes separate in production.

## R2 Requirements

Production R2 mode requires:

- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME`
- `R2_PUBLIC_BASE_URL`

Outside local development, `R2_PUBLIC_BASE_URL` must be an absolute HTTPS URL.

R2 credentials stay server-side only and must never be exposed to the frontend.

## Security Headers

The backend now sets baseline response headers, including:

- `Strict-Transport-Security` on HTTPS requests
- `Content-Security-Policy`
- `X-Content-Type-Options`
- `X-Frame-Options`
- `Referrer-Policy`
- `Permissions-Policy`
- `X-Request-ID`

Reverse proxy hardening can add stricter edge controls later, but the application now supplies a safer baseline by default.

## Local Development Differences

- local development can keep non-secure cookies
- localhost hosts remain allowed
- rate limiting uses a safe in-process fallback during tests and local development
- production proxy and origin assumptions are not automatically enabled in local mode
