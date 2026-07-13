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


class SocialConnectionListResponse(BaseModel):
    items: list[SocialConnectionSummaryResponse] = Field(default_factory=list)


class SocialConnectionMutationResponse(BaseModel):
    connection: SocialConnectionSummaryResponse


class SocialConnectionPath(BaseModel):
    connection_id: UUID
