# Account Deletion and Retention Controls

Story Engine includes a local account-deletion flow for the single-account private installation used today.

This document is an operational and product summary, not legal advice.

## What account deletion removes

- connected social-account records
- encrypted OAuth access and refresh tokens
- OAuth state records
- idea-queue items
- pipeline runs
- generated assets and generated-content metadata
- publication jobs and publication targets
- local `PlatformPost` records
- performance snapshots and performance learnings
- prompt logs, generation-cost records, and related operational run metadata

## What is anonymised instead of fully removed

- the local `accounts` row is converted into a deleted-account tombstone so Story Engine can:
  - keep deletion idempotent
  - prevent silent recreation or reactivation of the deleted account
  - preserve only the minimum non-active state needed for security review

## What may be retained temporarily

- deleted-account tombstones may be reviewed for purge after 12 months when they are no longer needed for security review or anti-reactivation safeguards
- expired OAuth state records may be reviewed for cleanup after 12 months

Story Engine does not automatically run destructive retention cleanup in this sprint. It exposes a dry-run retention report so the operator can review what has aged past the default window.

## What remains outside Story Engine

- videos already uploaded to YouTube remain on YouTube
- Story Engine does not delete provider-hosted videos automatically
- users should also revoke Google access manually if they no longer want Story Engine connected

Manual revocation path:

1. Open the Google account permissions page for the connected account.
2. Locate the Story Engine application entry.
3. Remove access from Google if desired.

## Authentication and post-deletion access

- account deletion immediately blocks future protected API access
- if private app access is enabled, the user must re-enter the current app password before deletion
- Story Engine does not support restoring a deleted account
- Story Engine does not support password-reset-based reactivation of a deleted account

## Retention baseline

- default retention ceiling: 12 months after data is no longer needed
- retained records must not contain active OAuth tokens
- retained records should be anonymised where possible
- no undocumented legal-retention claim should be made

## Billing scope

The current local Story Engine repository does not implement a Stripe billing or subscription workflow, so billing cleanup is out of scope for this sprint.

## Operator and review placeholders

- operator: `Mayo Soremekun`
- support/security contact: `mayomide.sore@outlook.com`
- governing law placeholder: `Federal Republic of Nigeria`, pending legal review
- public availability placeholder: Story Engine is intended for public availability to paying customers, pending final commercial and legal review

## Compliance-readiness relationship

The YouTube compliance readiness package can now truthfully state that:

- local account deletion is technically implemented
- local social tokens are removed during deletion
- provider-side Google revocation remains manual
- Story Engine exposes a 12-month dry-run retention report

Legal publication, privacy wording, customer-facing policies, and final retention commitments still require human review before being presented as final external statements.
