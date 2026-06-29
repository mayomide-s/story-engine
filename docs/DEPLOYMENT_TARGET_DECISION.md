# Deployment Target Decision

## Current Architecture

The current app is built around these moving parts:

- React/Vite frontend
- FastAPI backend
- PostgreSQL
- Redis
- Celery worker
- Cloudflare R2 for assets
- Runway as the paid video provider

This matters because deployment choices need to support:

- one web frontend
- one API service
- one durable relational database
- one Redis broker/backend
- at least one background worker process
- external secret storage for R2 and Runway

## Decision Goal

Choose the simplest safe deployment path for the next milestone without changing the current product shape.

Constraints:

- no auto-posting
- no analytics
- no login/subscriptions
- no batch paid generation
- no public launch before auth/security hardening

## Option 1: Single VPS With Docker Compose

### Complexity

Low.

This is operationally closest to the current local setup because the app already runs end to end in Docker Compose.

### Cost Risk

Low to moderate.

Typical costs are predictable:

- one VPS
- one domain
- optional managed backups
- R2 usage
- Runway credits

### Operational Burden

Moderate.

You own:

- OS patching
- Docker updates
- reverse proxy / TLS
- volume backups
- restart/recovery procedures

But the mental model stays simple because the stack lives in one place.

### Secret Management

Reasonable.

Secrets can live in:

- server environment variables
- a `.env` file on the server outside git
- a secret manager layered on top later

### Database Persistence

Straightforward.

You can use:

- Docker volume on the VPS
- or better, an external managed Postgres later

### Redis/Celery Support

Good.

Redis and Celery worker fit naturally in the same Compose deployment.

### Suitability For Solo Developer / Local MVP

Very high.

This is the closest match to the current repo, the easiest to reason about, and the least likely to create surprise platform behavior while the app is still a manual MVP.

## Option 2: Managed App Platform With Separate Services

Examples include:

- Render
- Railway
- Fly.io
- DigitalOcean App Platform

### Complexity

Moderate.

You usually split the app into:

- frontend service
- backend service
- worker service
- managed Postgres
- managed Redis

### Cost Risk

Moderate.

Costs can creep up through:

- separate service instances
- managed DB/Redis pricing
- egress and storage assumptions

### Operational Burden

Lower than a VPS for host maintenance, but higher in platform-specific setup.

You trade OS ops for:

- platform env management
- service linking
- worker process configuration
- platform logs and restart policies

### Secret Management

Usually strong.

Most platforms provide built-in secret injection.

### Database Persistence

Usually good if using managed Postgres.

### Redis/Celery Support

Usually possible, but the worker path must be configured intentionally.

This is a key risk area: some platforms make background workers easy, some make them awkward.

### Suitability For Solo Developer / Local MVP

Good, but only if the chosen platform handles:

- always-on worker services
- Redis cleanly
- service-to-service networking clearly

This is a viable second step after a VPS-like staging proof.

## Option 3: Managed Kubernetes / Container Platform

Examples include:

- Kubernetes on a cloud provider
- ECS/Fargate style container orchestration
- Nomad or other multi-service schedulers

### Complexity

High.

You add:

- manifests or Helm
- service discovery
- ingress
- secret objects
- rollout configuration
- worker scaling configuration

### Cost Risk

Moderate to high.

The cost is not just infrastructure. It is also engineering/operator time.

### Operational Burden

High for a solo developer at this stage.

### Secret Management

Strong in theory, but more configuration-heavy.

### Database Persistence

Usually offloaded to managed services anyway.

### Redis/Celery Support

Technically very good, but operationally overpowered for this app right now.

### Suitability For Solo Developer / Local MVP

Low.

This adds more platform complexity than the current product needs.

## Option 4: Split Frontend Hosting Plus Backend/Worker Stack

Typical shape:

- static frontend on Vercel/Netlify/Cloudflare Pages
- backend + Celery + Redis + Postgres on a VPS or managed services

### Complexity

Moderate.

This separates static delivery from API/worker concerns.

### Cost Risk

Moderate.

Frontend hosting may be cheap or free at low volume, but the backend stack still carries the real app cost.

### Operational Burden

Moderate.

You must coordinate:

- frontend public URL
- backend API URL
- CORS policy
- deployment timing between frontend and backend

### Secret Management

Good if the frontend has no secrets and backend secrets stay in the API/worker environment only.

### Database Persistence

Depends on where backend runs.

### Redis/Celery Support

Still depends on the backend side. Static frontend hosting does not solve worker complexity.

### Suitability For Solo Developer / Local MVP

Good once the API/worker stack is already understood.

This can be a nice incremental improvement after the first staging deployment proves stable.

## Practical Comparison

### Simplest to operate right now

- Single VPS with Docker Compose

### Best balance of convenience and managed infrastructure later

- Managed app platform with separate services

### Best for internet-scale ops, but worst fit for this stage

- Managed Kubernetes / container orchestration

### Best hybrid once backend deployment is stable

- Split frontend hosting plus backend/worker stack

## Recommended Primary Path

Recommended next deployment path:

- Start with a single VPS using Docker Compose

Why:

- it matches the existing runtime model closely
- it keeps Celery + Redis + backend wiring simple
- it reduces unknown platform behavior while Runway and R2 remain the operationally sensitive parts
- it is the easiest path for a solo developer shipping a manual internal MVP

Recommended later evolution:

- once the VPS deployment is stable, consider moving to split frontend hosting plus a managed backend/worker stack or a managed app platform

## Staged Deployment Plan

### Stage 1: Staging in mock mode

- deploy using `VIDEO_PROVIDER=mock`
- use `STORAGE_PROVIDER=r2`
- validate health checks, R2 uploads, queue/worker flow, manual posting package generation, and review UI

### Stage 2: Staging in Runway mode

- switch only the staging environment to `VIDEO_PROVIDER=runway`
- keep `STORAGE_PROVIDER=r2`
- run one controlled paid-provider regression at a time
- verify provider submission, polling, upload, quality check, and resume safety

### Stage 3: Production manual-posting mode

- keep manual workflow only
- no auto-posting
- no public mass launch
- use Runway carefully with explicit operational controls

## What Must Not Happen

- no secrets in git
- no live Runway calls in CI
- no auto-posting
- no public launch before auth/security is added
- no assumption that a static frontend host replaces backend/worker requirements

## Decision Summary

For the next milestone, the simplest safe path is:

- single VPS with Docker Compose for backend, worker, Redis, and Postgres
- Cloudflare R2 for assets
- Runway only in controlled staging/production environments

This keeps the deployment model close to the verified local MVP while minimizing operational surprise.
