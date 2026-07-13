from __future__ import annotations

import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import YouTubeProjectCompliance
from app.providers.youtube.oauth import YOUTUBE_OAUTH_SCOPES


YOUTUBE_COMPLIANCE_PLATFORM = "youtube"
YOUTUBE_COMPLIANCE_AUDIT_REQUIRED_CODE = "youtube_compliance_audit_required"
YouTubeComplianceStatus = Literal["unknown", "private_only", "audit_pending", "audit_approved"]
AuditReportSectionStatus = Literal[
    "implemented_verified",
    "inferred_from_configuration",
    "requires_human_confirmation",
    "not_implemented",
]


class YouTubeComplianceConflictError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _normalize_optional_text(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if len(trimmed) > max_length:
        raise ValueError(f"Value must be {max_length} characters or fewer.")
    return trimmed


def _compliance_explanation(status: YouTubeComplianceStatus) -> str:
    if status == "audit_approved":
        return "YouTube audit approval is recorded. Private, unlisted, and public can be selected for future uploads."
    if status == "audit_pending":
        return "YouTube audit review is recorded as pending. Private uploads remain available while unlisted and public stay blocked."
    if status == "unknown":
        return "YouTube audit status is unknown. Story Engine safely treats unlisted and public uploads as unavailable until approval is recorded."
    return "This YouTube API project is recorded as private-only. Google restricts uploads from unverified projects to private viewing until compliance approval is recorded."


def _scope_justifications() -> list[dict[str, str]]:
    return [
        {
            "scope": "https://www.googleapis.com/auth/youtube.upload",
            "required_for": "Create resumable YouTube uploads for explicitly approved Story Engine publication jobs.",
        },
        {
            "scope": "https://www.googleapis.com/auth/youtube.readonly",
            "required_for": "Resolve the connected channel identity and read post-upload processing and visibility state safely.",
        },
    ]


def _git_sha() -> str | None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    value = result.stdout.strip()
    return value or None


def _build_report_sections(current_status: str) -> list[dict[str, object]]:
    settings = get_settings()
    return [
        {
            "key": "application-purpose",
            "title": "Application purpose",
            "status": "implemented_verified",
            "summary": "Story Engine prepares reviewed short-form videos and only publishes a selected final asset after explicit user approval.",
            "bullets": [
                "Publishing starts from a completed pipeline run with a selected final MP4 asset.",
                "The user reviews metadata and explicitly approves the upload before execution.",
            ],
        },
        {
            "key": "connected-youtube-functionality",
            "title": "Connected YouTube functionality",
            "status": "implemented_verified",
            "summary": "The current integration supports secure connection, draft creation, approval, resumable upload execution, and post-upload status tracking.",
            "bullets": [
                "Private uploads remain supported.",
                "PlatformPost rows are created only for confirmed unlisted or public outcomes.",
                "Unlisted and public requests are locally blocked unless audit approval is recorded.",
            ],
        },
        {
            "key": "oauth-consent",
            "title": "User consent flow",
            "status": "implemented_verified",
            "summary": "The browser is redirected to Google's OAuth consent flow and the backend exchanges the callback code without exposing tokens to the browser.",
            "bullets": [
                "Only youtube.upload and youtube.readonly are requested.",
                "OAuth state is persisted and consumed exactly once.",
                "The callback redirects back to the frontend with safe non-secret status parameters only.",
            ],
        },
        {
            "key": "visibility-controls",
            "title": "Visibility controls and compliance blocking",
            "status": "implemented_verified",
            "summary": "Private remains available, while unlisted and public require an audit-approved compliance status before a job can be created.",
            "bullets": [
                f"Current compliance status: {current_status}.",
                "Blocked unlisted/public requests fail before publication jobs, targets, task dispatch, or provider calls are created.",
                "OAuth success is not treated as audit approval.",
            ],
        },
        {
            "key": "token-storage",
            "title": "Token encryption and storage",
            "status": "implemented_verified",
            "summary": "Access and refresh tokens are encrypted at rest and are not returned by the social-connection API.",
            "bullets": [
                "Encryption uses the configured SOCIAL_TOKEN_ENCRYPTION_KEY.",
                "Disconnect clears stored encrypted tokens.",
                "Token values are redacted from safe errors and excluded from audit reports.",
            ],
        },
        {
            "key": "token-refresh",
            "title": "Token refresh behaviour",
            "status": "implemented_verified",
            "summary": "The backend refreshes tokens before upload or polling when they are close to expiry.",
            "bullets": [
                "Revoked or invalid credentials are surfaced as safe reconnect-required failures.",
                "Refresh happens server-side only.",
            ],
        },
        {
            "key": "retry-idempotency",
            "title": "Retry, idempotency, and duplicate-upload protections",
            "status": "implemented_verified",
            "summary": "Story Engine persists frozen asset attribution, resumable upload state, and provider identifiers so retries do not blindly create duplicate uploads.",
            "bullets": [
                "Each publication target stores a stable idempotency key.",
                "Existing provider submission IDs are reused for reconcile/poll flows instead of a second upload.",
                "Encrypted resumable session URIs are stored at rest.",
            ],
        },
        {
            "key": "quota-conscious",
            "title": "Quota-conscious behaviour",
            "status": "implemented_verified",
            "summary": "The upload flow uses resumable uploads and bounded polling to avoid unnecessary repeat requests.",
            "bullets": [
                f"Default YouTube poll interval: {settings.youtube_poll_interval_seconds} seconds.",
                f"Maximum poll attempts: {settings.youtube_max_poll_attempts}.",
                f"Maximum upload retry attempts: {settings.youtube_max_retry_attempts}.",
            ],
        },
        {
            "key": "audit-logging",
            "title": "Audit logging",
            "status": "implemented_verified",
            "summary": "Pipeline events record publication job lifecycle transitions and compliance updates without storing secrets.",
            "bullets": [
                "Publication events include job and target identifiers plus safe status metadata.",
                "Compliance updates record status transitions and non-secret reference fields only.",
            ],
        },
        {
            "key": "content-flags",
            "title": "Made for kids, synthetic media, and notify-subscribers handling",
            "status": "implemented_verified",
            "summary": "The YouTube payload persists made-for-kids and synthetic-media choices, and resumable initialization keeps notifySubscribers false.",
            "bullets": [
                "Made-for-kids is user-selected in the draft.",
                "Contains synthetic media is user-selected in the draft.",
                "notifySubscribers is fixed to false in the current upload implementation.",
            ],
        },
        {
            "key": "retention-deletion",
            "title": "Data retention and deletion behaviour",
            "status": "implemented_verified",
            "summary": "The application retains publication jobs and targets for auditability, while disconnect removes stored tokens from social connections.",
            "bullets": [
                "Publication records persist unless removed by future product features.",
                "There is no provider-side deletion automation in the current implementation.",
            ],
        },
        {
            "key": "human-completion",
            "title": "Human confirmation still required",
            "status": "requires_human_confirmation",
            "summary": "Google compliance submission materials still require project, policy, support, and organizational details that Story Engine does not fabricate.",
            "bullets": [
                "Privacy policy URL and owner details.",
                "Terms of service and support contact information.",
                "Compliance submission case details and any audit correspondence.",
            ],
        },
        {
            "key": "not-implemented",
            "title": "Not implemented",
            "status": "not_implemented",
            "summary": "Story Engine does not automate compliance-form submission, YouTube Studio actions, or post-publication visibility changes.",
            "bullets": [
                "No YouTube Studio browser automation.",
                "No automatic public/unlisted visibility changes after upload.",
                "No production deployment or public-domain readiness assertions are generated here.",
            ],
        },
    ]


def _render_report_markdown(report: dict[str, object]) -> str:
    lines = [
        "# YouTube Audit Readiness Report",
        "",
        f"- Application: {report['application_name']}",
        f"- Platform: {report['platform']}",
        f"- Current compliance status: {report['current_compliance_status']}",
        f"- Generated at: {report['generated_at']}",
    ]
    if report.get("application_version"):
        lines.append(f"- Application version: {report['application_version']}")
    lines.extend(["", "## OAuth scopes", ""])
    for item in report["scope_justifications"]:
        lines.append(f"- `{item['scope']}`: {item['required_for']}")
    lines.extend(["", "## Sections", ""])
    for section in report["sections"]:
        lines.append(f"### {section['title']}")
        lines.append(f"- Status: `{section['status']}`")
        lines.append(f"- Summary: {section['summary']}")
        for bullet in section["bullets"]:
            lines.append(f"  - {bullet}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _find_youtube_project_compliance(db: Session) -> YouTubeProjectCompliance | None:
    return (
        db.query(YouTubeProjectCompliance)
        .filter(YouTubeProjectCompliance.platform == YOUTUBE_COMPLIANCE_PLATFORM)
        .first()
    )


def get_youtube_project_compliance(db: Session) -> YouTubeProjectCompliance:
    record = _find_youtube_project_compliance(db)
    if record is None:
        record = YouTubeProjectCompliance(
            platform=YOUTUBE_COMPLIANCE_PLATFORM,
            compliance_status="private_only",
            status_updated_at=_utcnow(),
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(record)
        db.flush()
    return record


def serialize_youtube_project_compliance(record: YouTubeProjectCompliance | None) -> dict[str, object]:
    status = record.compliance_status if record is not None else "private_only"
    return {
        "platform": YOUTUBE_COMPLIANCE_PLATFORM,
        "compliance_status": status,
        "status_updated_at": record.status_updated_at if record is not None else _utcnow(),
        "submission_date": record.submission_date if record is not None else None,
        "approval_date": record.approval_date if record is not None else None,
        "case_reference": record.case_reference if record is not None else None,
        "admin_note": record.admin_note if record is not None else None,
        "can_publish_private": True,
        "can_publish_unlisted": status == "audit_approved",
        "can_publish_public": status == "audit_approved",
        "status_explanation": _compliance_explanation(status),
        "created_at": record.created_at if record is not None else None,
        "updated_at": record.updated_at if record is not None else None,
    }


def get_youtube_project_compliance_response(db: Session) -> dict[str, object]:
    return serialize_youtube_project_compliance(_find_youtube_project_compliance(db))


def update_youtube_project_compliance(
    db: Session,
    *,
    compliance_status: YouTubeComplianceStatus,
    submission_date: date | None,
    approval_date: date | None,
    case_reference: str | None,
    admin_note: str | None,
    confirm_audit_approved: bool,
) -> dict[str, object]:
    if compliance_status == "audit_approved" and not confirm_audit_approved:
        raise ValueError("Explicit confirmation is required before recording audit approval.")

    record = get_youtube_project_compliance(db)
    record.compliance_status = compliance_status
    record.status_updated_at = _utcnow()
    record.submission_date = submission_date
    record.approval_date = approval_date
    record.case_reference = _normalize_optional_text(case_reference, max_length=255)
    record.admin_note = _normalize_optional_text(admin_note, max_length=2000)
    record.updated_at = _utcnow()
    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize_youtube_project_compliance(record)


def ensure_youtube_visibility_allowed(db: Session, visibility: str) -> dict[str, object]:
    if visibility == "private":
        return get_youtube_project_compliance_response(db)

    record = _find_youtube_project_compliance(db)
    if (record.compliance_status if record is not None else "private_only") != "audit_approved":
        raise YouTubeComplianceConflictError(
            YOUTUBE_COMPLIANCE_AUDIT_REQUIRED_CODE,
            "Google currently restricts uploads from this project to private viewing until YouTube compliance approval is recorded.",
        )
    return serialize_youtube_project_compliance(record)


def build_youtube_audit_readiness_report(db: Session) -> dict[str, object]:
    settings = get_settings()
    record = _find_youtube_project_compliance(db)
    current_status = record.compliance_status if record is not None else "private_only"
    sections = _build_report_sections(current_status)
    report = {
        "platform": YOUTUBE_COMPLIANCE_PLATFORM,
        "application_name": settings.app_name,
        "application_purpose": "Story Engine helps a user review a selected final video, approve a publication job, and upload it to YouTube through official OAuth and API flows.",
        "connected_youtube_functionality": "Secure OAuth connection, frozen-asset publication drafting, explicit approval, resumable upload execution, and post-upload status tracking.",
        "current_compliance_status": current_status,
        "requested_scopes": list(YOUTUBE_OAUTH_SCOPES),
        "scope_justifications": _scope_justifications(),
        "sections": sections,
        "generated_at": _utcnow(),
        "application_version": _git_sha(),
    }
    report["markdown"] = _render_report_markdown(report)
    return report
