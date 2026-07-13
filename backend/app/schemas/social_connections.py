from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SocialAuthorizeRequest(BaseModel):
    return_path: str | None = None


class SocialAuthorizeResponse(BaseModel):
    platform: Literal["youtube"]
    authorization_url: str
    expires_at: datetime


class SocialConnectionSummaryResponse(BaseModel):
    id: str
    platform: str
    display_name: str | None = None
    username: str | None = None
    external_identity_hint: str
    connection_status: str
    granted_scopes: list[str] = Field(default_factory=list)
    token_expires_at: datetime | None = None
    token_health: str
    is_default: bool
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    last_error_code: str | None = None
    created_at: datetime
    updated_at: datetime


YouTubeComplianceStatus = Literal["unknown", "private_only", "audit_pending", "audit_approved"]
AuditReportSectionStatus = Literal[
    "implemented_verified",
    "inferred_from_configuration",
    "requires_human_confirmation",
    "not_implemented",
]
YouTubeReadinessRequirementStatus = Literal["pass", "fail", "needs_confirmation", "not_applicable"]
YouTubeReadinessEvidenceSource = Literal[
    "implemented_code",
    "configuration_contract",
    "submission_profile",
    "human_confirmation",
    "runtime_record",
]
YouTubeReadinessBlockerSeverity = Literal["blocking", "advisory", "none"]


class YouTubeProjectComplianceResponse(BaseModel):
    platform: Literal["youtube"]
    compliance_status: YouTubeComplianceStatus
    status_updated_at: datetime
    submission_date: date | None = None
    approval_date: date | None = None
    case_reference: str | None = None
    admin_note: str | None = None
    can_publish_private: bool
    can_publish_unlisted: bool
    can_publish_public: bool
    status_explanation: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class YouTubeProjectComplianceUpdateRequest(BaseModel):
    compliance_status: YouTubeComplianceStatus
    submission_date: date | None = None
    approval_date: date | None = None
    case_reference: str | None = None
    admin_note: str | None = None
    confirm_audit_approved: bool = False
    confirm_google_audit_approval_received: bool = False


class YouTubeAuditReadinessScopeResponse(BaseModel):
    scope: str
    required_for: str


class YouTubeAuditReadinessSectionResponse(BaseModel):
    key: str
    title: str
    status: AuditReportSectionStatus
    summary: str
    bullets: list[str] = Field(default_factory=list)


class YouTubeAuditReadinessReportResponse(BaseModel):
    platform: Literal["youtube"]
    application_name: str
    application_purpose: str
    connected_youtube_functionality: str
    current_compliance_status: YouTubeComplianceStatus
    requested_scopes: list[str] = Field(default_factory=list)
    scope_justifications: list[YouTubeAuditReadinessScopeResponse] = Field(default_factory=list)
    sections: list[YouTubeAuditReadinessSectionResponse] = Field(default_factory=list)
    generated_at: datetime
    application_version: str | None = None
    markdown: str


class YouTubeHumanConfirmationResponse(BaseModel):
    key: str
    title: str
    description: str
    required_for_approval: bool
    completed: bool


class YouTubeHumanConfirmationUpdateRequest(BaseModel):
    completed: bool = True
    reviewed_by: str | None = None


class YouTubeSubmissionProfileResponse(BaseModel):
    platform: Literal["youtube"]
    application_display_name: str | None = None
    product_description: str | None = None
    organization_name: str | None = None
    support_contact: str | None = None
    privacy_policy_url: str | None = None
    terms_of_service_url: str | None = None
    application_homepage_url: str | None = None
    production_oauth_redirect_uri: str | None = None
    production_frontend_url: str | None = None
    production_api_url: str | None = None
    data_retention_summary: str | None = None
    user_data_deletion_summary: str | None = None
    token_revocation_summary: str | None = None
    account_disconnection_summary: str | None = None
    quota_monitoring_summary: str | None = None
    incident_response_summary: str | None = None
    security_contact_summary: str | None = None
    intended_submission_date: date | None = None
    submission_case_reference: str | None = None
    last_reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    admin_note: str | None = None
    human_confirmations: list[YouTubeHumanConfirmationResponse] = Field(default_factory=list)


class YouTubeSubmissionProfileUpdateRequest(BaseModel):
    application_display_name: str | None = None
    product_description: str | None = None
    organization_name: str | None = None
    support_contact: str | None = None
    privacy_policy_url: str | None = None
    terms_of_service_url: str | None = None
    application_homepage_url: str | None = None
    production_oauth_redirect_uri: str | None = None
    production_frontend_url: str | None = None
    production_api_url: str | None = None
    data_retention_summary: str | None = None
    user_data_deletion_summary: str | None = None
    token_revocation_summary: str | None = None
    account_disconnection_summary: str | None = None
    quota_monitoring_summary: str | None = None
    incident_response_summary: str | None = None
    security_contact_summary: str | None = None
    intended_submission_date: date | None = None
    submission_case_reference: str | None = None
    reviewed_by: str | None = None
    admin_note: str | None = None


class YouTubeReadinessRequirementResponse(BaseModel):
    key: str
    title: str
    description: str
    category: str
    status: YouTubeReadinessRequirementStatus
    evidence_source: YouTubeReadinessEvidenceSource
    evidence_summary: str
    blocker_severity: YouTubeReadinessBlockerSeverity
    remediation_guidance: str
    human_confirmation_required: bool
    last_evaluated_at: datetime


class YouTubeReadinessBlockerResponse(BaseModel):
    key: str
    title: str
    category: str
    status: YouTubeReadinessRequirementStatus
    blocker_severity: YouTubeReadinessBlockerSeverity
    evidence_summary: str
    remediation_guidance: str


class YouTubeReadinessEvaluationResponse(BaseModel):
    platform: Literal["youtube"]
    current_compliance_status: YouTubeComplianceStatus
    overall_status: YouTubeReadinessRequirementStatus
    blocker_count: int
    blockers: list[YouTubeReadinessBlockerResponse] = Field(default_factory=list)
    requirements: list[YouTubeReadinessRequirementResponse] = Field(default_factory=list)
    human_confirmations: list[YouTubeHumanConfirmationResponse] = Field(default_factory=list)
    can_record_audit_approved: bool
    generated_at: datetime


class YouTubeEvidenceManifestItemResponse(BaseModel):
    key: str
    title: str
    required: bool
    why_needed: str
    acceptable_evidence: str
    current_state: str
    human_action_required: bool


class YouTubeComplianceSubmissionPackageResponse(BaseModel):
    platform: Literal["youtube"]
    executive_summary: dict[str, object]
    oauth_and_access: dict[str, object]
    publishing_workflow: dict[str, object]
    user_controls: dict[str, object]
    security_and_operations: dict[str, object]
    legal_and_policy: dict[str, object]
    readiness: YouTubeReadinessEvaluationResponse
    evidence_matrix: list[YouTubeReadinessRequirementResponse] = Field(default_factory=list)
    evidence_manifest: list[YouTubeEvidenceManifestItemResponse] = Field(default_factory=list)
    submission_checklist: list[str] = Field(default_factory=list)
    human_completion_items: list[str] = Field(default_factory=list)
    generated_at: datetime
    application_version: str | None = None
    markdown: str
    checklist_markdown: str


class SocialConnectionListResponse(BaseModel):
    items: list[SocialConnectionSummaryResponse] = Field(default_factory=list)


class SocialConnectionMutationResponse(BaseModel):
    connection: SocialConnectionSummaryResponse


class SocialConnectionPath(BaseModel):
    connection_id: UUID
