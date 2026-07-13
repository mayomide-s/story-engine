from __future__ import annotations

import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import YouTubeProjectCompliance
from app.providers.youtube.oauth import YOUTUBE_OAUTH_SCOPES


YOUTUBE_COMPLIANCE_PLATFORM = "youtube"
YOUTUBE_COMPLIANCE_AUDIT_REQUIRED_CODE = "youtube_compliance_audit_required"
YOUTUBE_COMPLIANCE_READINESS_INCOMPLETE_CODE = "youtube_compliance_readiness_incomplete"

YouTubeComplianceStatus = Literal["unknown", "private_only", "audit_pending", "audit_approved"]
ReadinessStatus = Literal["pass", "fail", "needs_confirmation", "not_applicable"]
ReadinessEvidenceSource = Literal[
    "implemented_code",
    "configuration_contract",
    "submission_profile",
    "human_confirmation",
    "runtime_record",
]
ReadinessBlockerSeverity = Literal["blocking", "advisory", "none"]

AuditReportSectionStatus = Literal[
    "implemented_verified",
    "inferred_from_configuration",
    "requires_human_confirmation",
    "not_implemented",
]

HUMAN_CONFIRMATION_DEFINITIONS: list[dict[str, str | bool]] = [
    {
        "key": "legal_review_completed",
        "title": "Legal review completed",
        "description": "A human has reviewed the privacy, terms, support, and organizational information for the submission package.",
        "required_for_approval": True,
    },
    {
        "key": "privacy_policy_verified",
        "title": "Privacy policy verified",
        "description": "A human confirmed that the privacy policy content and URL match the production product behaviour.",
        "required_for_approval": True,
    },
    {
        "key": "terms_of_service_verified",
        "title": "Terms of service verified",
        "description": "A human confirmed that the terms page exists and matches the production product behaviour.",
        "required_for_approval": True,
    },
    {
        "key": "support_contact_verified",
        "title": "Support contact verified",
        "description": "A human confirmed that the support contact is monitored and suitable for YouTube compliance follow-up.",
        "required_for_approval": True,
    },
    {
        "key": "production_urls_verified",
        "title": "Production URLs verified",
        "description": "A human confirmed that the production homepage, frontend, API, and OAuth redirect URIs are final and current.",
        "required_for_approval": True,
    },
    {
        "key": "deletion_and_revocation_reviewed",
        "title": "Deletion and revocation reviewed",
        "description": "A human confirmed that user-data deletion and token revocation instructions are accurate and externally shareable.",
        "required_for_approval": True,
    },
    {
        "key": "incident_response_reviewed",
        "title": "Incident response reviewed",
        "description": "A human confirmed that the incident response description matches the actual operational plan.",
        "required_for_approval": True,
    },
    {
        "key": "monitoring_reviewed",
        "title": "Monitoring and quota review completed",
        "description": "A human confirmed that quota monitoring and operational monitoring evidence are ready for submission.",
        "required_for_approval": True,
    },
    {
        "key": "submission_package_reviewed",
        "title": "Submission package reviewed",
        "description": "A human reviewed the generated submission package, evidence manifest, and blocker list before any compliance status change.",
        "required_for_approval": True,
    },
]


class YouTubeComplianceConflictError(RuntimeError):
    def __init__(self, code: str, message: str, *, extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra or {}

    def to_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.extra}


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


def _normalize_optional_url(value: str | None, *, field_name: str) -> str | None:
    normalized = _normalize_optional_text(value, max_length=2048)
    if normalized is None:
        return None
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute HTTP(S) URL.")
    return normalized


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
            human_confirmations_json={},
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(record)
        db.flush()
    return record


def _compliance_explanation(status: YouTubeComplianceStatus) -> str:
    if status == "audit_approved":
        return "YouTube audit approval is recorded. Private, unlisted, and public can be selected for future uploads."
    if status == "audit_pending":
        return "YouTube audit review is recorded as pending. Private uploads remain available while unlisted and public stay blocked."
    if status == "unknown":
        return "YouTube audit status is unknown. Story Engine safely treats unlisted and public uploads as unavailable until approval is recorded."
    return "This YouTube API project is recorded as private-only. Google restricts uploads from unverified projects to private viewing until compliance approval is recorded."


def _serialize_confirmation_states(record: YouTubeProjectCompliance | None) -> list[dict[str, Any]]:
    values = dict(record.human_confirmations_json or {}) if record is not None else {}
    return [
        {
            "key": item["key"],
            "title": item["title"],
            "description": item["description"],
            "required_for_approval": bool(item["required_for_approval"]),
            "completed": bool(values.get(str(item["key"]), False)),
        }
        for item in HUMAN_CONFIRMATION_DEFINITIONS
    ]


def serialize_youtube_project_compliance(record: YouTubeProjectCompliance | None) -> dict[str, Any]:
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


def get_youtube_project_compliance_response(db: Session) -> dict[str, Any]:
    return serialize_youtube_project_compliance(_find_youtube_project_compliance(db))


def _serialize_submission_profile(record: YouTubeProjectCompliance | None) -> dict[str, Any]:
    return {
        "platform": YOUTUBE_COMPLIANCE_PLATFORM,
        "application_display_name": record.application_display_name if record is not None else None,
        "product_description": record.product_description if record is not None else None,
        "organization_name": record.organization_name if record is not None else None,
        "support_contact": record.support_contact if record is not None else None,
        "privacy_policy_url": record.privacy_policy_url if record is not None else None,
        "terms_of_service_url": record.terms_of_service_url if record is not None else None,
        "application_homepage_url": record.application_homepage_url if record is not None else None,
        "production_oauth_redirect_uri": record.production_oauth_redirect_uri if record is not None else None,
        "production_frontend_url": record.production_frontend_url if record is not None else None,
        "production_api_url": record.production_api_url if record is not None else None,
        "data_retention_summary": record.data_retention_summary if record is not None else None,
        "user_data_deletion_summary": record.user_data_deletion_summary if record is not None else None,
        "token_revocation_summary": record.token_revocation_summary if record is not None else None,
        "account_disconnection_summary": record.account_disconnection_summary if record is not None else None,
        "quota_monitoring_summary": record.quota_monitoring_summary if record is not None else None,
        "incident_response_summary": record.incident_response_summary if record is not None else None,
        "security_contact_summary": record.security_contact_summary if record is not None else None,
        "intended_submission_date": record.intended_submission_date if record is not None else None,
        "submission_case_reference": record.case_reference if record is not None else None,
        "last_reviewed_at": record.last_reviewed_at if record is not None else None,
        "reviewed_by": record.reviewed_by if record is not None else None,
        "admin_note": record.admin_note if record is not None else None,
        "human_confirmations": _serialize_confirmation_states(record),
    }


def get_youtube_submission_profile_response(db: Session) -> dict[str, Any]:
    return _serialize_submission_profile(_find_youtube_project_compliance(db))


def update_youtube_submission_profile(
    db: Session,
    *,
    application_display_name: str | None = None,
    product_description: str | None = None,
    organization_name: str | None = None,
    support_contact: str | None = None,
    privacy_policy_url: str | None = None,
    terms_of_service_url: str | None = None,
    application_homepage_url: str | None = None,
    production_oauth_redirect_uri: str | None = None,
    production_frontend_url: str | None = None,
    production_api_url: str | None = None,
    data_retention_summary: str | None = None,
    user_data_deletion_summary: str | None = None,
    token_revocation_summary: str | None = None,
    account_disconnection_summary: str | None = None,
    quota_monitoring_summary: str | None = None,
    incident_response_summary: str | None = None,
    security_contact_summary: str | None = None,
    intended_submission_date: date | None = None,
    submission_case_reference: str | None = None,
    reviewed_by: str | None = None,
    admin_note: str | None = None,
) -> dict[str, Any]:
    record = get_youtube_project_compliance(db)
    record.application_display_name = _normalize_optional_text(application_display_name, max_length=255)
    record.product_description = _normalize_optional_text(product_description, max_length=4000)
    record.organization_name = _normalize_optional_text(organization_name, max_length=255)
    record.support_contact = _normalize_optional_text(support_contact, max_length=255)
    record.privacy_policy_url = _normalize_optional_url(privacy_policy_url, field_name="privacy_policy_url")
    record.terms_of_service_url = _normalize_optional_url(terms_of_service_url, field_name="terms_of_service_url")
    record.application_homepage_url = _normalize_optional_url(application_homepage_url, field_name="application_homepage_url")
    record.production_oauth_redirect_uri = _normalize_optional_url(
        production_oauth_redirect_uri,
        field_name="production_oauth_redirect_uri",
    )
    record.production_frontend_url = _normalize_optional_url(
        production_frontend_url,
        field_name="production_frontend_url",
    )
    record.production_api_url = _normalize_optional_url(
        production_api_url,
        field_name="production_api_url",
    )
    record.data_retention_summary = _normalize_optional_text(data_retention_summary, max_length=4000)
    record.user_data_deletion_summary = _normalize_optional_text(user_data_deletion_summary, max_length=4000)
    record.token_revocation_summary = _normalize_optional_text(token_revocation_summary, max_length=4000)
    record.account_disconnection_summary = _normalize_optional_text(account_disconnection_summary, max_length=4000)
    record.quota_monitoring_summary = _normalize_optional_text(quota_monitoring_summary, max_length=4000)
    record.incident_response_summary = _normalize_optional_text(incident_response_summary, max_length=4000)
    record.security_contact_summary = _normalize_optional_text(security_contact_summary, max_length=4000)
    record.intended_submission_date = intended_submission_date
    record.case_reference = _normalize_optional_text(submission_case_reference, max_length=255)
    record.reviewed_by = _normalize_optional_text(reviewed_by, max_length=255)
    record.admin_note = _normalize_optional_text(admin_note, max_length=2000)
    record.last_reviewed_at = _utcnow()
    record.updated_at = _utcnow()
    db.add(record)
    db.commit()
    db.refresh(record)
    return _serialize_submission_profile(record)


def set_youtube_human_confirmation(
    db: Session,
    *,
    confirmation_key: str,
    completed: bool,
    reviewed_by: str | None = None,
) -> dict[str, Any]:
    allowed = {str(item["key"]) for item in HUMAN_CONFIRMATION_DEFINITIONS}
    if confirmation_key not in allowed:
        raise ValueError("Unknown human confirmation key.")
    record = get_youtube_project_compliance(db)
    values = dict(record.human_confirmations_json or {})
    values[confirmation_key] = bool(completed)
    record.human_confirmations_json = values
    if reviewed_by is not None:
        record.reviewed_by = _normalize_optional_text(reviewed_by, max_length=255)
    record.last_reviewed_at = _utcnow()
    record.updated_at = _utcnow()
    db.add(record)
    db.commit()
    db.refresh(record)
    return _serialize_submission_profile(record)


def clear_youtube_human_confirmation(
    db: Session,
    *,
    confirmation_key: str,
    reviewed_by: str | None = None,
) -> dict[str, Any]:
    return set_youtube_human_confirmation(
        db,
        confirmation_key=confirmation_key,
        completed=False,
        reviewed_by=reviewed_by,
    )


def _is_https_non_localhost_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    hostname = (parsed.hostname or "").lower()
    return hostname not in {"localhost", "127.0.0.1", "::1"}


def _requirement(
    *,
    key: str,
    title: str,
    description: str,
    category: str,
    status: ReadinessStatus,
    evidence_source: ReadinessEvidenceSource,
    evidence_summary: str,
    blocker_severity: ReadinessBlockerSeverity,
    remediation_guidance: str,
    human_confirmation_required: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "description": description,
        "category": category,
        "status": status,
        "evidence_source": evidence_source,
        "evidence_summary": evidence_summary,
        "blocker_severity": blocker_severity,
        "remediation_guidance": remediation_guidance,
        "human_confirmation_required": human_confirmation_required,
        "last_evaluated_at": _utcnow(),
    }


def _profile_text_pass(value: str | None) -> bool:
    return bool(value and value.strip())


def _profile_url_requirement(
    *,
    key: str,
    title: str,
    description: str,
    category: str,
    value: str | None,
    remediation: str,
) -> dict[str, Any]:
    if not value:
        return _requirement(
            key=key,
            title=title,
            description=description,
            category=category,
            status="fail",
            evidence_source="submission_profile",
            evidence_summary="No URL has been recorded.",
            blocker_severity="blocking",
            remediation_guidance=remediation,
        )
    if not _is_https_non_localhost_url(value):
        return _requirement(
            key=key,
            title=title,
            description=description,
            category=category,
            status="fail",
            evidence_source="submission_profile",
            evidence_summary="The recorded URL is not an HTTPS non-localhost production URL.",
            blocker_severity="blocking",
            remediation_guidance=remediation,
        )
    return _requirement(
        key=key,
        title=title,
        description=description,
        category=category,
        status="pass",
        evidence_source="submission_profile",
        evidence_summary=f"Recorded production URL: {value}",
        blocker_severity="none",
        remediation_guidance=remediation,
    )


def _confirmation_requirement(item: dict[str, str | bool], record: YouTubeProjectCompliance | None) -> dict[str, Any]:
    values = dict(record.human_confirmations_json or {}) if record is not None else {}
    completed = bool(values.get(str(item["key"]), False))
    return _requirement(
        key=f"confirmation:{item['key']}",
        title=str(item["title"]),
        description=str(item["description"]),
        category="legal and organisational information",
        status="pass" if completed else "needs_confirmation",
        evidence_source="human_confirmation",
        evidence_summary="Human confirmation recorded." if completed else "Human confirmation is still required.",
        blocker_severity="none" if completed else "blocking",
        remediation_guidance="Review the relevant evidence and mark this confirmation as complete when it is genuinely verified.",
        human_confirmation_required=bool(item["required_for_approval"]),
    )


def build_youtube_readiness_evaluation(db: Session) -> dict[str, Any]:
    record = _find_youtube_project_compliance(db)
    profile = _serialize_submission_profile(record)
    current_status = record.compliance_status if record is not None else "private_only"

    requirements: list[dict[str, Any]] = [
        _requirement(
            key="product-purpose",
            title="Application purpose documented",
            description="The submission pack must explain what Story Engine does for YouTube publishing.",
            category="product",
            status="pass" if _profile_text_pass(profile["product_description"]) else "fail",
            evidence_source="submission_profile",
            evidence_summary="Product description recorded." if _profile_text_pass(profile["product_description"]) else "Product description is missing.",
            blocker_severity="none" if _profile_text_pass(profile["product_description"]) else "blocking",
            remediation_guidance="Add a concise product description suitable for a YouTube compliance reviewer.",
        ),
        _requirement(
            key="application-display-name",
            title="Application display name recorded",
            description="The submission pack must identify the application by name.",
            category="product",
            status="pass" if _profile_text_pass(profile["application_display_name"]) else "fail",
            evidence_source="submission_profile",
            evidence_summary="Application display name recorded." if _profile_text_pass(profile["application_display_name"]) else "Application display name is missing.",
            blocker_severity="none" if _profile_text_pass(profile["application_display_name"]) else "blocking",
            remediation_guidance="Record the application display name used in the compliance submission.",
        ),
        _requirement(
            key="organization-name",
            title="Organization or developer identity recorded",
            description="The submission pack must identify the organization or individual developer responsible for the project.",
            category="legal and organisational information",
            status="pass" if _profile_text_pass(profile["organization_name"]) else "fail",
            evidence_source="submission_profile",
            evidence_summary="Organization or developer name recorded." if _profile_text_pass(profile["organization_name"]) else "Organization or developer name is missing.",
            blocker_severity="none" if _profile_text_pass(profile["organization_name"]) else "blocking",
            remediation_guidance="Record the organization or individual developer name that will appear in the submission.",
        ),
        _requirement(
            key="oauth-scopes",
            title="OAuth scopes are minimal and documented",
            description="The system should request only the YouTube scopes required for the current publishing workflow.",
            category="OAuth",
            status="pass",
            evidence_source="implemented_code",
            evidence_summary="The integration requests only youtube.upload and youtube.readonly.",
            blocker_severity="none",
            remediation_guidance="Keep the scope set minimal unless a reviewed product requirement changes.",
        ),
        _requirement(
            key="token-encryption",
            title="Token encryption implemented",
            description="Connected YouTube tokens must be encrypted at rest and excluded from browser responses.",
            category="security",
            status="pass",
            evidence_source="implemented_code",
            evidence_summary="Access and refresh tokens are encrypted at rest and excluded from API response payloads.",
            blocker_severity="none",
            remediation_guidance="Keep encrypted token storage and redaction behaviour in place.",
        ),
        _requirement(
            key="user-consent-flow",
            title="User consent flow implemented",
            description="The YouTube connection flow must use OAuth state validation and explicit user consent.",
            category="user consent",
            status="pass",
            evidence_source="implemented_code",
            evidence_summary="OAuth state is stored and consumed once, and the browser never receives refresh tokens.",
            blocker_severity="none",
            remediation_guidance="Preserve state validation and server-side token exchange.",
        ),
        _requirement(
            key="publishing-private-available",
            title="Private publishing remains available",
            description="Private uploads must remain allowed while the project is still private-only.",
            category="publishing workflow",
            status="pass",
            evidence_source="implemented_code",
            evidence_summary="Private publication requests continue through the existing draft, approval, dispatch, and upload flow.",
            blocker_severity="none",
            remediation_guidance="Keep private publishing intact while other visibilities stay guarded.",
        ),
        _requirement(
            key="visibility-policy",
            title="Unlisted/public visibility guard enforced",
            description="Unlisted and public must be blocked until compliance approval is explicitly recorded.",
            category="publishing workflow",
            status="pass",
            evidence_source="implemented_code",
            evidence_summary=f"Current compliance status is {current_status}; unlisted/public creation is still guarded by backend policy.",
            blocker_severity="none",
            remediation_guidance="Keep visibility checks ahead of job and target creation.",
        ),
        _requirement(
            key="error-handling",
            title="Provider-safe error handling implemented",
            description="The publishing workflow must sanitize provider failures and avoid leaking secrets in API errors.",
            category="error handling",
            status="pass",
            evidence_source="implemented_code",
            evidence_summary="Provider failures are converted into safe publication errors and compliance conflicts.",
            blocker_severity="none",
            remediation_guidance="Continue redacting sensitive provider details and secrets from errors.",
        ),
        _requirement(
            key="retry-idempotency",
            title="Retry and idempotency controls implemented",
            description="The publishing workflow must avoid duplicate uploads when retries or worker restarts occur.",
            category="retry and idempotency",
            status="pass",
            evidence_source="implemented_code",
            evidence_summary="Publication targets persist idempotency keys, submission identifiers, and encrypted resumable session URIs.",
            blocker_severity="none",
            remediation_guidance="Preserve persisted upload session and submission identifiers across retries.",
        ),
        _requirement(
            key="duplicate-upload-prevention",
            title="Duplicate upload prevention implemented",
            description="Story Engine should not create duplicate uploads or duplicate PlatformPosts after outcome recovery.",
            category="duplicate-upload prevention",
            status="pass",
            evidence_source="implemented_code",
            evidence_summary="The workflow reconciles persisted provider identifiers and creates at most one PlatformPost for confirmed public or unlisted success.",
            blocker_severity="none",
            remediation_guidance="Keep duplicate-upload prevention checks in provider execution and reconciliation.",
        ),
        _requirement(
            key="child-directed-handling",
            title="Child-directed content handling implemented",
            description="The publishing flow must preserve the user-selected made-for-kids value.",
            category="child-directed content handling",
            status="pass",
            evidence_source="implemented_code",
            evidence_summary="The publication draft includes a made-for-kids setting that is preserved into the provider payload.",
            blocker_severity="none",
            remediation_guidance="Keep the made-for-kids control explicit in the user approval flow.",
        ),
        _requirement(
            key="synthetic-media-disclosure",
            title="Synthetic media disclosure implemented",
            description="The publishing flow must preserve the user-selected synthetic media disclosure value.",
            category="synthetic-media disclosure",
            status="pass",
            evidence_source="implemented_code",
            evidence_summary="The publication draft includes a contains-synthetic-media flag that is preserved into the provider payload.",
            blocker_severity="none",
            remediation_guidance="Keep synthetic-media disclosure explicit in the user approval flow.",
        ),
        _requirement(
            key="subscriber-notification-behaviour",
            title="Subscriber notification behaviour documented",
            description="The YouTube upload behaviour should document whether subscriber notifications are sent.",
            category="subscriber-notification behaviour",
            status="pass",
            evidence_source="implemented_code",
            evidence_summary="notifySubscribers remains false in the current YouTube upload implementation.",
            blocker_severity="none",
            remediation_guidance="Update the submission package if notification behaviour changes in code.",
        ),
        _requirement(
            key="account-deletion-capability",
            title="Technical account deletion capability implemented",
            description="Story Engine should support local account deletion, token removal, and post-deletion access blocking.",
            category="deletion and revocation",
            status="pass",
            evidence_source="implemented_code",
            evidence_summary="Account deletion preview, execution, social-token removal, and access invalidation are implemented.",
            blocker_severity="none",
            remediation_guidance="Keep the account-deletion flow available for reviewer verification.",
        ),
        _requirement(
            key="retention-policy-configuration",
            title="Retention policy controls implemented",
            description="Story Engine should define and expose a default 12-month retention policy for data that is no longer needed.",
            category="data retention",
            status="pass",
            evidence_source="implemented_code",
            evidence_summary="A dry-run retention report is implemented with a 12-month default retention policy representation.",
            blocker_severity="none",
            remediation_guidance="Keep the retention report aligned with future cleanup rules and policy wording.",
        ),
        _requirement(
            key="quota-monitoring",
            title="Quota monitoring summary recorded",
            description="The submission pack should describe how quota usage is monitored operationally.",
            category="quota management",
            status="pass" if _profile_text_pass(profile["quota_monitoring_summary"]) else "fail",
            evidence_source="submission_profile",
            evidence_summary="Quota monitoring summary recorded." if _profile_text_pass(profile["quota_monitoring_summary"]) else "Quota monitoring summary is missing.",
            blocker_severity="none" if _profile_text_pass(profile["quota_monitoring_summary"]) else "blocking",
            remediation_guidance="Document how quota use and failed upload patterns will be monitored in production.",
        ),
        _profile_url_requirement(
            key="privacy-policy-url",
            title="Privacy policy URL recorded",
            description="A production privacy policy URL is required for the compliance submission pack.",
            category="privacy",
            value=profile["privacy_policy_url"],
            remediation="Record the production HTTPS privacy policy URL.",
        ),
        _profile_url_requirement(
            key="terms-of-service-url",
            title="Terms of service URL recorded",
            description="A production terms URL is required for the compliance submission pack.",
            category="terms",
            value=profile["terms_of_service_url"],
            remediation="Record the production HTTPS terms of service URL.",
        ),
        _profile_url_requirement(
            key="application-homepage-url",
            title="Application homepage URL recorded",
            description="A production homepage URL is required for a complete reviewer-facing submission package.",
            category="production configuration",
            value=profile["application_homepage_url"],
            remediation="Record the production HTTPS application homepage URL.",
        ),
        _profile_url_requirement(
            key="production-oauth-redirect-uri",
            title="Production OAuth redirect URI recorded",
            description="A non-localhost production OAuth redirect URI is required before audit approval can be recorded.",
            category="OAuth",
            value=profile["production_oauth_redirect_uri"],
            remediation="Record the production HTTPS OAuth redirect URI that matches the Google Cloud configuration.",
        ),
        _profile_url_requirement(
            key="production-frontend-url",
            title="Production frontend URL recorded",
            description="A non-localhost production frontend URL is required before audit approval can be recorded.",
            category="production configuration",
            value=profile["production_frontend_url"],
            remediation="Record the production HTTPS frontend URL.",
        ),
        _profile_url_requirement(
            key="production-api-url",
            title="Production API URL recorded",
            description="A non-localhost production API URL is required before audit approval can be recorded.",
            category="production configuration",
            value=profile["production_api_url"],
            remediation="Record the production HTTPS API URL.",
        ),
        _requirement(
            key="support-contact",
            title="Support contact recorded",
            description="A support contact is required for reviewers and end users.",
            category="legal and organisational information",
            status="pass" if _profile_text_pass(profile["support_contact"]) else "fail",
            evidence_source="submission_profile",
            evidence_summary="Support contact recorded." if _profile_text_pass(profile["support_contact"]) else "Support contact is missing.",
            blocker_severity="none" if _profile_text_pass(profile["support_contact"]) else "blocking",
            remediation_guidance="Record a support contact suitable for reviewer follow-up and end-user support.",
        ),
        _requirement(
            key="data-retention-summary",
            title="Data retention summary recorded",
            description="The submission pack should describe how long relevant data is retained.",
            category="data retention",
            status="pass" if _profile_text_pass(profile["data_retention_summary"]) else "fail",
            evidence_source="submission_profile",
            evidence_summary="Data retention summary recorded." if _profile_text_pass(profile["data_retention_summary"]) else "Data retention summary is missing.",
            blocker_severity="none" if _profile_text_pass(profile["data_retention_summary"]) else "blocking",
            remediation_guidance="Add a non-secret summary of data retention behaviour suitable for reviewer consumption.",
        ),
        _requirement(
            key="deletion-summary",
            title="User-data deletion summary recorded",
            description="The submission pack should explain how a user can request deletion of data related to the integration.",
            category="deletion and revocation",
            status="pass" if _profile_text_pass(profile["user_data_deletion_summary"]) else "fail",
            evidence_source="submission_profile",
            evidence_summary="User-data deletion summary recorded." if _profile_text_pass(profile["user_data_deletion_summary"]) else "User-data deletion summary is missing.",
            blocker_severity="none" if _profile_text_pass(profile["user_data_deletion_summary"]) else "blocking",
            remediation_guidance="Document the user-data deletion path that will be shared with reviewers and end users.",
        ),
        _requirement(
            key="token-revocation-summary",
            title="Token revocation summary recorded",
            description="The submission pack should explain how token revocation is handled.",
            category="deletion and revocation",
            status="pass" if _profile_text_pass(profile["token_revocation_summary"]) else "fail",
            evidence_source="submission_profile",
            evidence_summary="Token revocation summary recorded." if _profile_text_pass(profile["token_revocation_summary"]) else "Token revocation summary is missing.",
            blocker_severity="none" if _profile_text_pass(profile["token_revocation_summary"]) else "blocking",
            remediation_guidance="Document the token revocation process for connected YouTube accounts.",
        ),
        _requirement(
            key="account-disconnection-summary",
            title="Account disconnection summary recorded",
            description="The submission pack should explain how disconnecting a YouTube account works in the product.",
            category="deletion and revocation",
            status="pass" if _profile_text_pass(profile["account_disconnection_summary"]) else "fail",
            evidence_source="submission_profile",
            evidence_summary="Account disconnection summary recorded." if _profile_text_pass(profile["account_disconnection_summary"]) else "Account disconnection summary is missing.",
            blocker_severity="none" if _profile_text_pass(profile["account_disconnection_summary"]) else "blocking",
            remediation_guidance="Document the account disconnection behaviour shown in the application.",
        ),
        _requirement(
            key="incident-response-summary",
            title="Incident response summary recorded",
            description="The submission pack should describe how operational incidents affecting publishing will be handled.",
            category="incident response",
            status="pass" if _profile_text_pass(profile["incident_response_summary"]) else "fail",
            evidence_source="submission_profile",
            evidence_summary="Incident response summary recorded." if _profile_text_pass(profile["incident_response_summary"]) else "Incident response summary is missing.",
            blocker_severity="none" if _profile_text_pass(profile["incident_response_summary"]) else "blocking",
            remediation_guidance="Add a non-secret incident response summary suitable for compliance review.",
        ),
        _requirement(
            key="security-contact-summary",
            title="Security contact summary recorded",
            description="The submission pack should include security contact or escalation information suitable for reviewer follow-up.",
            category="security",
            status="pass" if _profile_text_pass(profile["security_contact_summary"]) else "fail",
            evidence_source="submission_profile",
            evidence_summary="Security contact summary recorded." if _profile_text_pass(profile["security_contact_summary"]) else "Security contact summary is missing.",
            blocker_severity="none" if _profile_text_pass(profile["security_contact_summary"]) else "blocking",
            remediation_guidance="Record security contact or escalation information that can be shared with reviewers.",
        ),
        _requirement(
            key="submission-reference",
            title="Submission case/reference prepared",
            description="The system should track the intended submission case/reference identifier once one exists.",
            category="legal and organisational information",
            status="pass" if _profile_text_pass(profile["submission_case_reference"]) else "fail",
            evidence_source="submission_profile",
            evidence_summary="Submission case/reference recorded." if _profile_text_pass(profile["submission_case_reference"]) else "Submission case/reference is missing.",
            blocker_severity="none" if _profile_text_pass(profile["submission_case_reference"]) else "blocking",
            remediation_guidance="Record the intended or assigned submission case/reference identifier.",
        ),
        _requirement(
            key="intended-submission-date",
            title="Intended submission date recorded",
            description="The submission package should capture the intended submission timing for operational tracking.",
            category="legal and organisational information",
            status="pass" if profile["intended_submission_date"] else "fail",
            evidence_source="submission_profile",
            evidence_summary="Intended submission date recorded." if profile["intended_submission_date"] else "Intended submission date is missing.",
            blocker_severity="none" if profile["intended_submission_date"] else "blocking",
            remediation_guidance="Record the intended submission date for the compliance package.",
        ),
    ]

    requirements.extend(_confirmation_requirement(item, record) for item in HUMAN_CONFIRMATION_DEFINITIONS)

    blockers = [
        {
            "key": item["key"],
            "title": item["title"],
            "category": item["category"],
            "status": item["status"],
            "blocker_severity": item["blocker_severity"],
            "evidence_summary": item["evidence_summary"],
            "remediation_guidance": item["remediation_guidance"],
        }
        for item in requirements
        if item["blocker_severity"] == "blocking" and item["status"] in {"fail", "needs_confirmation"}
    ]

    if any(item["status"] == "fail" for item in requirements):
        overall_status: ReadinessStatus = "fail"
    elif any(item["status"] == "needs_confirmation" for item in requirements):
        overall_status = "needs_confirmation"
    elif requirements:
        overall_status = "pass"
    else:
        overall_status = "not_applicable"

    return {
        "platform": YOUTUBE_COMPLIANCE_PLATFORM,
        "current_compliance_status": current_status,
        "overall_status": overall_status,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "requirements": requirements,
        "human_confirmations": _serialize_confirmation_states(record),
        "can_record_audit_approved": len(blockers) == 0,
        "generated_at": _utcnow(),
    }


def list_youtube_readiness_blockers(db: Session) -> list[dict[str, Any]]:
    return list(build_youtube_readiness_evaluation(db)["blockers"])


def get_youtube_approval_readiness(db: Session) -> dict[str, Any]:
    evaluation = build_youtube_readiness_evaluation(db)
    return {
        "platform": YOUTUBE_COMPLIANCE_PLATFORM,
        "current_compliance_status": evaluation["current_compliance_status"],
        "can_record_audit_approved": evaluation["can_record_audit_approved"],
        "blocker_count": evaluation["blocker_count"],
        "blockers": evaluation["blockers"],
        "generated_at": evaluation["generated_at"],
    }


def _build_report_sections(current_status: str, readiness: dict[str, Any]) -> list[dict[str, Any]]:
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
            "key": "visibility-controls",
            "title": "Visibility controls and approval guard",
            "status": "implemented_verified",
            "summary": "Private remains available, while unlisted and public require an audit-approved compliance status and a readiness evaluation with no blockers.",
            "bullets": [
                f"Current compliance status: {current_status}.",
                f"Current blocker count: {readiness['blocker_count']}.",
                "Blocked unlisted/public requests fail before jobs, targets, dispatch, or provider calls.",
                "Audit approval cannot be recorded while required blockers or confirmations remain unresolved.",
            ],
        },
        {
            "key": "token-storage",
            "title": "Token encryption and storage",
            "status": "implemented_verified",
            "summary": "Access and refresh tokens are encrypted at rest and never returned by the social-connection API.",
            "bullets": [
                "Encryption uses SOCIAL_TOKEN_ENCRYPTION_KEY in runtime configuration.",
                "Disconnect clears stored encrypted tokens.",
                "The compliance package and audit events exclude token values.",
            ],
        },
        {
            "key": "deletion-and-retention",
            "title": "Account deletion and retention controls",
            "status": "implemented_verified",
            "summary": "Story Engine supports local account deletion, local token removal, and a dry-run retention report while leaving provider-side video deletion out of scope.",
            "bullets": [
                "Account deletion removes account-owned Story Engine records and invalidates further access.",
                "A minimal deleted-account marker is retained to prevent silent reactivation.",
                "Provider-side Google revocation and uploaded-video deletion remain manual actions.",
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
            "key": "human-completion",
            "title": "Human completion still required",
            "status": "requires_human_confirmation",
            "summary": "Legal, operational, and production details still require explicit human confirmation even when the code paths are implemented.",
            "bullets": [
                "Story Engine does not fabricate policy URLs, company identity, support contacts, or legal assertions.",
                "Story Engine does not infer Google approval from OAuth, private uploads, or upload success.",
            ],
        },
        {
            "key": "not-implemented",
            "title": "Not implemented",
            "status": "not_implemented",
            "summary": "Story Engine does not submit Google forms, deploy production pages, or automate external compliance evidence capture.",
            "bullets": [
                "No automatic Google compliance-form submission.",
                "No automatic privacy, terms, or support-page publication.",
                "No automatic Google Cloud screenshot capture.",
            ],
        },
    ]


def _evidence_manifest(profile: dict[str, Any]) -> list[dict[str, Any]]:
    manual_url_state = "Ready for manual capture" if profile["production_oauth_redirect_uri"] else "Blocked until a production OAuth redirect URI is recorded"
    privacy_state = "Ready for manual capture" if profile["privacy_policy_url"] else "Blocked until a privacy policy URL is recorded"
    terms_state = "Ready for manual capture" if profile["terms_of_service_url"] else "Blocked until a terms URL is recorded"
    support_state = "Ready for manual capture" if profile["support_contact"] else "Blocked until a support contact is recorded"
    return [
        {
            "key": "oauth-consent-screen",
            "title": "OAuth consent screen screenshot",
            "required": True,
            "why_needed": "Shows the scopes, branding, and consent-screen configuration that reviewers will see.",
            "acceptable_evidence": "A current screenshot from Google Cloud Console showing the OAuth consent screen.",
            "current_state": "Human capture required",
            "human_action_required": True,
        },
        {
            "key": "test-user-configuration",
            "title": "Test-user configuration screenshot",
            "required": True,
            "why_needed": "Shows which tester accounts can access the current integration while it is unverified.",
            "acceptable_evidence": "A current screenshot of the Google Cloud test-user configuration.",
            "current_state": "Human capture required",
            "human_action_required": True,
        },
        {
            "key": "oauth-client-redirect-uri",
            "title": "OAuth client redirect URI screenshot",
            "required": True,
            "why_needed": "Shows that the configured production redirect URI matches the submission package.",
            "acceptable_evidence": "A screenshot of the OAuth client redirect URI list in Google Cloud Console.",
            "current_state": manual_url_state,
            "human_action_required": True,
        },
        {
            "key": "youtube-data-api-enabled",
            "title": "YouTube Data API enabled screenshot",
            "required": True,
            "why_needed": "Shows that the required Google API is enabled for the project being submitted.",
            "acceptable_evidence": "A screenshot of the enabled APIs list showing YouTube Data API v3.",
            "current_state": "Human capture required",
            "human_action_required": True,
        },
        {
            "key": "upload-ui",
            "title": "Upload UI screenshot",
            "required": True,
            "why_needed": "Demonstrates the explicit user approval and YouTube publishing controls in Story Engine.",
            "acceptable_evidence": "Screenshots of the publish panel, including visibility selection and approval controls.",
            "current_state": "Human capture required",
            "human_action_required": True,
        },
        {
            "key": "visibility-blocking-ui",
            "title": "Compliance blocking screenshot",
            "required": True,
            "why_needed": "Shows that unlisted and public are blocked before approval and that Story Engine does not self-certify compliance.",
            "acceptable_evidence": "A screenshot of the disabled visibility controls and blocker messaging.",
            "current_state": "Human capture required",
            "human_action_required": True,
        },
        {
            "key": "disconnect-revoke-ui",
            "title": "Disconnect or revoke UI screenshot",
            "required": True,
            "why_needed": "Shows how the user disconnects an account and understands revocation-related behaviour.",
            "acceptable_evidence": "A screenshot of the connected-account management UI and any relevant explanatory text.",
            "current_state": "Human capture required",
            "human_action_required": True,
        },
        {
            "key": "privacy-policy-page",
            "title": "Privacy policy page",
            "required": True,
            "why_needed": "Provides the policy URL and visible content that reviewers can compare with the product behaviour.",
            "acceptable_evidence": "The final production privacy policy URL plus a screenshot or rendered copy of the page.",
            "current_state": privacy_state,
            "human_action_required": True,
        },
        {
            "key": "terms-page",
            "title": "Terms of service page",
            "required": True,
            "why_needed": "Provides the terms URL and visible content that reviewers can compare with the product behaviour.",
            "acceptable_evidence": "The final production terms URL plus a screenshot or rendered copy of the page.",
            "current_state": terms_state,
            "human_action_required": True,
        },
        {
            "key": "support-contact-page",
            "title": "Support contact evidence",
            "required": True,
            "why_needed": "Shows how reviewers and users can contact the operator of the integration.",
            "acceptable_evidence": "A support page, contact form, or written support address that matches the submission profile.",
            "current_state": support_state,
            "human_action_required": True,
        },
        {
            "key": "user-data-deletion-instructions",
            "title": "User-data deletion instructions",
            "required": True,
            "why_needed": "Provides reviewer-facing evidence for how users can request deletion.",
            "acceptable_evidence": "A policy page or support article describing the deletion request path.",
            "current_state": "Human capture required",
            "human_action_required": True,
        },
        {
            "key": "production-architecture-summary",
            "title": "Production deployment architecture summary",
            "required": False,
            "why_needed": "Helps reviewers understand the production components behind the publishing workflow.",
            "acceptable_evidence": "A simple architecture diagram or written summary of the production deployment.",
            "current_state": "Human capture required",
            "human_action_required": True,
        },
        {
            "key": "quota-monitoring-evidence",
            "title": "Quota monitoring evidence",
            "required": False,
            "why_needed": "Supports the operational claim that upload and polling behaviour are monitored responsibly.",
            "acceptable_evidence": "A dashboard screenshot, alert configuration, or operational note.",
            "current_state": "Human capture required",
            "human_action_required": True,
        },
        {
            "key": "incident-response-process",
            "title": "Incident response evidence",
            "required": False,
            "why_needed": "Supports the incident-response description provided in the submission profile.",
            "acceptable_evidence": "An internal process summary, checklist, or runbook reference.",
            "current_state": "Human capture required",
            "human_action_required": True,
        },
    ]


def _human_completion_items(readiness: dict[str, Any], manifest: list[dict[str, Any]]) -> list[str]:
    items = [f"{item['title']}: {item['remediation_guidance']}" for item in readiness["blockers"]]
    for entry in manifest:
        if entry["human_action_required"]:
            items.append(f"{entry['title']}: {entry['acceptable_evidence']}")
    return items


def _submission_checklist(readiness: dict[str, Any], manifest: list[dict[str, Any]]) -> list[str]:
    checklist = [
        "Confirm the YouTube submission profile fields are complete and current.",
        "Review the generated blocker list and resolve every blocking fail item.",
        "Review and complete every required human confirmation.",
        "Capture the evidence items listed in the evidence manifest.",
        "Verify the production privacy, terms, support, frontend, API, and OAuth redirect URLs.",
        "Record the submission case/reference identifier and intended submission date.",
        "Only record audit approval after Google has explicitly granted it.",
    ]
    if readiness["blocker_count"] > 0:
        checklist.append(f"There are currently {readiness['blocker_count']} blockers to resolve before audit approval can be recorded.")
    if any(entry["required"] for entry in manifest):
        checklist.append("Collect the required screenshots and policy evidence outside Story Engine before submitting the Google form.")
    return checklist


def _render_package_markdown(package: dict[str, Any]) -> str:
    lines = [
        "# YouTube Compliance Submission Package",
        "",
        f"- Application: {package['executive_summary']['application_display_name']}",
        f"- Current compliance status: {package['executive_summary']['current_compliance_status']}",
        f"- Readiness status: {package['executive_summary']['readiness_status']}",
        f"- Blocker count: {package['executive_summary']['blocker_count']}",
        f"- Generated at: {package['generated_at']}",
    ]
    if package.get("application_version"):
        lines.append(f"- Application version: {package['application_version']}")
    lines.extend(["", "## OAuth and access", ""])
    for item in package["oauth_and_access"]["scope_justifications"]:
        lines.append(f"- `{item['scope']}`: {item['required_for']}")
    lines.extend(["", "## Readiness blockers", ""])
    if package["readiness"]["blockers"]:
        for blocker in package["readiness"]["blockers"]:
            lines.append(f"- **{blocker['title']}**: {blocker['remediation_guidance']}")
    else:
        lines.append("- No current blockers.")
    lines.extend(["", "## Evidence matrix", ""])
    for requirement in package["evidence_matrix"]:
        lines.append(f"- `{requirement['key']}` [{requirement['status']}] - {requirement['evidence_summary']}")
    lines.extend(["", "## Submission checklist", ""])
    for item in package["submission_checklist"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Human completion required", ""])
    for item in package["human_completion_items"]:
        lines.append(f"- {item}")
    return "\n".join(lines).strip() + "\n"


def _render_checklist_markdown(package: dict[str, Any]) -> str:
    lines = ["# YouTube Submission Checklist", ""]
    for item in package["submission_checklist"]:
        lines.append(f"- [ ] {item}")
    return "\n".join(lines).strip() + "\n"


def build_youtube_submission_package(db: Session) -> dict[str, Any]:
    settings = get_settings()
    record = _find_youtube_project_compliance(db)
    profile = _serialize_submission_profile(record)
    readiness = build_youtube_readiness_evaluation(db)
    evidence_manifest = _evidence_manifest(profile)
    submission_checklist = _submission_checklist(readiness, evidence_manifest)
    application_version = _git_sha()

    package: dict[str, Any] = {
        "platform": YOUTUBE_COMPLIANCE_PLATFORM,
        "executive_summary": {
            "application_display_name": profile["application_display_name"] or settings.app_name,
            "product_purpose": profile["product_description"] or "No administrator-supplied product description has been recorded yet.",
            "youtube_use_case": "Upload a selected final Story Engine video to YouTube after explicit user review and approval.",
            "current_compliance_status": readiness["current_compliance_status"],
            "readiness_status": readiness["overall_status"],
            "blocker_count": readiness["blocker_count"],
            "generated_at": readiness["generated_at"],
        },
        "oauth_and_access": {
            "requested_scopes": list(YOUTUBE_OAUTH_SCOPES),
            "scope_justifications": _scope_justifications(),
            "consent_flow": "The browser is redirected to Google OAuth, and the backend exchanges the callback code without exposing refresh tokens to the browser.",
            "connection_flow": "Story Engine connects exactly one YouTube channel through the official Google OAuth flow.",
            "disconnect_flow": "Disconnect clears encrypted stored tokens and marks the connection disconnected.",
            "account_deletion_flow": "Account deletion clears local tokens, deletes account-owned Story Engine records, and blocks future authentication without deleting provider-hosted videos.",
            "token_refresh": "The backend refreshes tokens server-side when they approach expiry or when a publication step requires it.",
            "token_encryption": "Access and refresh tokens are encrypted at rest and redacted from API responses, reports, and audit events.",
            "token_revocation": profile["token_revocation_summary"] or "No token revocation summary has been recorded yet.",
        },
        "publishing_workflow": {
            "asset_selection": "Publishing starts only from a completed run with a selected final asset.",
            "frozen_asset_integrity": "The publication job freezes the final asset ID, selection revision, source, and SHA-256 hash before approval.",
            "metadata_confirmation": "The user confirms title, caption, tags, visibility, made-for-kids, and synthetic-media selections before approval.",
            "visibility_policy": "Private remains available. Unlisted and public are blocked unless compliance approval is explicitly recorded and readiness blockers are resolved.",
            "job_creation": "Blocked visibility requests fail before any publication job or target is created.",
            "task_dispatch": "Only approved jobs can be dispatched.",
            "resumable_upload": "YouTube upload execution uses resumable uploads and encrypted stored session URIs.",
            "polling": "Bounded polling verifies processing and visibility outcomes.",
            "reconciliation": "Outcome reconciliation reuses provider identifiers rather than blindly starting a second upload.",
            "duplicate_prevention": "Stable idempotency keys and persisted provider identifiers prevent duplicate uploads.",
            "platform_post_behaviour": "Exactly one PlatformPost is created only after a confirmed public or unlisted outcome.",
        },
        "user_controls": {
            "connection_management": "The UI allows connection, refresh, and disconnect management for YouTube accounts.",
            "visibility_selection": "The user chooses private, unlisted, or public, but unlisted/public remain disabled until compliance approval is recorded.",
            "made_for_kids_selection": "The draft form includes an explicit made-for-kids choice.",
            "synthetic_media_disclosure": "The draft form includes an explicit synthetic-media disclosure choice.",
            "subscriber_notification_behaviour": "notifySubscribers is fixed to false in the current implementation.",
            "deletion_and_revocation_controls": "Disconnect and local account deletion are implemented; provider-side Google revocation and uploaded-video deletion remain manual.",
        },
        "security_and_operations": {
            "secret_storage_approach": "Secrets are supplied through runtime configuration and are not emitted in compliance exports.",
            "encrypted_token_storage": "Connected access and refresh tokens are encrypted at rest.",
            "retry_policy": "Bounded retry and resumable-session recovery avoid duplicate uploads after transient failures.",
            "stale_job_recovery": "Celery recovery tasks can resume or reconcile persisted targets without a blind second upload.",
            "error_sanitisation": "Provider and configuration errors are converted into safe application errors.",
            "audit_logging": "Pipeline events record publication and compliance status changes without secrets.",
            "quota_conscious_behaviour": "Resumable uploads plus bounded polling reduce unnecessary quota use.",
            "incident_response_readiness": profile["incident_response_summary"] or "No incident response summary has been recorded yet.",
            "monitoring_readiness": profile["quota_monitoring_summary"] or "No quota or operational monitoring summary has been recorded yet.",
            "production_configuration_blockers": readiness["blockers"],
        },
        "legal_and_policy": {
            "privacy_policy_url": profile["privacy_policy_url"],
            "terms_of_service_url": profile["terms_of_service_url"],
            "support_contact": profile["support_contact"],
            "retention_statement": profile["data_retention_summary"] or "No retention statement has been recorded yet.",
            "deletion_statement": profile["user_data_deletion_summary"] or "No deletion statement has been recorded yet.",
            "token_revocation_statement": profile["token_revocation_summary"] or "No token revocation statement has been recorded yet.",
            "legal_review_status": next(
                (item["status"] for item in readiness["requirements"] if item["key"] == "confirmation:legal_review_completed"),
                "needs_confirmation",
            ),
            "unresolved_policy_blockers": [
                item for item in readiness["blockers"]
                if item["category"] in {"privacy", "terms", "data retention", "deletion and revocation", "legal and organisational information"}
            ],
        },
        "readiness": readiness,
        "evidence_matrix": readiness["requirements"],
        "evidence_manifest": evidence_manifest,
        "submission_checklist": submission_checklist,
        "human_completion_items": _human_completion_items(readiness, evidence_manifest),
        "generated_at": readiness["generated_at"],
        "application_version": application_version,
    }
    package["markdown"] = _render_package_markdown(package)
    package["checklist_markdown"] = _render_checklist_markdown(package)
    return package


def build_youtube_audit_readiness_report(db: Session) -> dict[str, Any]:
    return build_youtube_submission_package(db)


def update_youtube_project_compliance(
    db: Session,
    *,
    compliance_status: YouTubeComplianceStatus,
    submission_date: date | None,
    approval_date: date | None,
    case_reference: str | None,
    admin_note: str | None,
    confirm_audit_approved: bool,
    confirm_google_audit_approval_received: bool = False,
) -> dict[str, Any]:
    if compliance_status == "audit_approved":
        if not confirm_audit_approved:
            raise ValueError("Explicit confirmation is required before recording audit approval.")
        if not confirm_google_audit_approval_received:
            raise ValueError("You must acknowledge that YouTube compliance approval came from Google and was not inferred by Story Engine.")
        readiness = build_youtube_readiness_evaluation(db)
        blockers = list(readiness["blockers"])
        if not case_reference or not case_reference.strip():
            blockers.append(
                {
                    "key": "approval-case-reference",
                    "title": "Approval case/reference is missing",
                    "category": "legal and organisational information",
                    "status": "fail",
                    "blocker_severity": "blocking",
                    "evidence_summary": "No approval case/reference identifier was supplied.",
                    "remediation_guidance": "Record the Google-issued approval case/reference identifier before marking audit approval.",
                }
            )
        if approval_date is None:
            blockers.append(
                {
                    "key": "approval-date",
                    "title": "Approval date is missing",
                    "category": "legal and organisational information",
                    "status": "fail",
                    "blocker_severity": "blocking",
                    "evidence_summary": "No approval date was supplied.",
                    "remediation_guidance": "Record the date on which Google granted compliance approval.",
                }
            )
        if blockers:
            raise YouTubeComplianceConflictError(
                YOUTUBE_COMPLIANCE_READINESS_INCOMPLETE_CODE,
                "YouTube audit approval cannot be recorded until every readiness blocker is resolved and all required confirmations are complete.",
                extra={"blockers": blockers},
            )

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


def ensure_youtube_visibility_allowed(db: Session, visibility: str) -> dict[str, Any]:
    if visibility == "private":
        return get_youtube_project_compliance_response(db)

    record = _find_youtube_project_compliance(db)
    if (record.compliance_status if record is not None else "private_only") != "audit_approved":
        raise YouTubeComplianceConflictError(
            YOUTUBE_COMPLIANCE_AUDIT_REQUIRED_CODE,
            "Google currently restricts uploads from this project to private viewing until YouTube compliance approval is recorded.",
        )
    return serialize_youtube_project_compliance(record)
