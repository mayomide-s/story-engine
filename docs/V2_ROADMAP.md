# V2 Roadmap

## Purpose

This document plans the next phase after `v1.0.1` without changing the current app behavior.

The goal of `v2` should be to make the product more reliable, easier to review, safer to deploy privately, and better informed by real usage before expanding into heavier automation.

## What V1 Already Does

The current `v1` local MVP already covers:

- idea queue
- batch planning controls
- brand defaults
- prompt preview and editable review flow
- Runway video generation
- Cloudflare R2 asset storage
- automated quality check and recheck
- asset library
- export/manual posting pack
- deployment and staging planning docs

Operationally, `v1` also already proves:

- mock and Runway provider support
- local Docker workflow
- Celery polling flow
- R2 upload path
- release tagging and GitHub backup
- deployment-preflight and VPS staging documentation

## V2 Planning Principles

Keep `v2` realistic for a solo developer:

- prefer quality and control over breadth
- avoid irreversible automation too early
- deploy privately before chasing broader product scope
- do not build analytics-heavy systems before real posting data exists
- do not add direct auto-posting before auth/security exists

## V2 Track 1: Content Quality Improvements

### User Value

High.

Better scripts, prompts, critique, and editing produce more useful videos and reduce wasted Runway credits.

### Implementation Complexity

Moderate.

Most of the required primitives already exist:

- prompt preview
- editable review inputs
- critique step
- style presets

### Cost / Risk

Moderate.

The main risk is spending too much time tuning prompts before enough real usage data exists.

### Before or After Deployment

Mostly before or alongside private staging deployment.

This improves the core output quality without requiring broader platform work.

## V2 Track 2: Private Staging Deployment

### User Value

High.

A private staging deployment makes the system easier to test from more than one machine and is the next practical step before any broader release.

### Implementation Complexity

Moderate.

The repo already has:

- deployment preflight docs
- deployment target decision docs
- VPS staging deployment package

### Cost / Risk

Moderate.

Costs include:

- VPS
- domain/subdomain
- R2 usage
- optional Runway staging tests

### Before or After Deployment

This is the deployment track itself and should happen early in `v2`.

## V2 Track 3: Authentication And Security

### User Value

Very high.

Without access control, the app should remain private. Auth is a prerequisite for any broader rollout, multi-user access, or sensitive provider-key operations.

### Implementation Complexity

Moderate to high.

This likely touches:

- backend auth/session model
- frontend route protection
- account ownership rules
- secret handling and deployment settings

### Cost / Risk

High if rushed.

Security work done halfway creates a false sense of safety.

### Before or After Deployment

After private staging is working, but before any wider or public release.

## V2 Track 4: Better Editing And Review Workflow

### User Value

High.

Better review UX reduces bad generations, improves operator confidence, and helps the manual workflow scale without adding unsafe automation.

### Implementation Complexity

Moderate.

This can build on existing:

- Ideas page
- prompt preview
- review notes
- critique guidance
- recheck flow

### Cost / Risk

Low to moderate.

Mostly product/design effort, with low infra risk.

### Before or After Deployment

Can happen before or after private staging deployment.

It is especially useful once staging exists and the workflow is exercised more often.

## V2 Track 5: Controlled Publishing Preparation

### User Value

Moderate to high.

This helps the app move from “manual export only” toward a safer future publishing model without crossing into full automation too early.

### Implementation Complexity

Moderate.

Examples might include:

- richer publish readiness states
- approval checkpoints
- better per-platform packaging
- publishing audit fields

### Cost / Risk

Moderate.

The main risk is drifting into direct posting too early.

### Before or After Deployment

After private staging, and preferably after auth/security groundwork begins.

## V2 Track 6: Analytics And Manual Performance Tracking

### User Value

Potentially high later, but limited immediately.

Without real posting volume and stable publish workflows, analytics can become speculative overhead.

### Implementation Complexity

Moderate to high depending on scope.

### Cost / Risk

Moderate.

The risk is building dashboards before trustworthy data pipelines exist.

### Before or After Deployment

After deployment and after some real manual posting history exists.

This should not be an early `v2` priority.

## Track Priority Summary

### Best early `v2` candidates

- private staging deployment
- content quality improvements
- better editing and review workflow

### Important but not first

- authentication and security
- controlled publishing preparation

### Should wait

- analytics/manual performance tracking beyond lightweight notes or manual fields

## Recommended Next 3 Milestones After V1.0.1

## Milestone 1: Private Staging Bring-Up

Primary goal:

- deploy a private staging environment on a single VPS using the existing Docker strategy

Success criteria:

- staging works in `mock/r2`
- health checks pass
- one controlled `runway/r2` regression succeeds
- `.env` and secrets stay out of git
- staging remains private

Why this first:

- it validates the operational model without changing the product itself

## Milestone 2: Review Workflow And Output Quality Pass

Primary goal:

- make the human-in-the-loop workflow faster and safer before more automation

Focus areas:

- better script/prompt edit UX
- clearer critique guidance
- stronger review states and notes
- fewer wasted Runway submissions

Why this second:

- once staging exists, quality and review pain points become easier to observe

## Milestone 3: Auth/Security Foundation For Non-Public Access

Primary goal:

- add the minimum access control needed before any wider use

Focus areas:

- login/access control
- protected routes
- environment and provider-key safety review
- deployment hardening follow-up

Why this third:

- it should happen before any public launch or direct automation
- but it is easier to design after the private staging and review workflow are clearer

## What V2 Should Explicitly Avoid

- direct auto-posting before auth/security
- public launch before access control
- bulk paid Runway generation
- analytics bloat before real posting data exists
- large infrastructure jumps before private staging is stable

## Recommended V2 Direction

The most realistic `v2` path for a solo developer is:

1. private staging deployment
2. review and content quality improvements
3. auth/security groundwork

This keeps the roadmap aligned with the app’s current strengths:

- strong manual workflow
- controlled paid generation
- clear review steps
- deployment readiness without overcommitting to automation too early
