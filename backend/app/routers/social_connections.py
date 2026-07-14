from __future__ import annotations

from uuid import UUID

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.social_connections import (
    SocialAuthorizeRequest,
    SocialAuthorizeResponse,
    YouTubeComplianceSubmissionPackageResponse,
    YouTubeHumanConfirmationUpdateRequest,
    YouTubeReadinessBlockerResponse,
    YouTubeReadinessEvaluationResponse,
    YouTubeProjectComplianceResponse,
    YouTubeProjectComplianceUpdateRequest,
    YouTubeSubmissionProfileResponse,
    YouTubeSubmissionProfileUpdateRequest,
    SocialConnectionListResponse,
    SocialConnectionMutationResponse,
)
from app.services.access_service import require_app_access, require_csrf_protection
from app.services.rate_limit_service import limit_from_settings
from app.services.social_connection_service import (
    SocialConnectionConfigurationError,
    begin_youtube_authorization,
    complete_youtube_callback,
    disconnect_social_connection,
    list_social_connections,
    refresh_social_connection,
)
from app.services.youtube_compliance_service import (
    YouTubeComplianceConflictError,
    build_youtube_audit_readiness_report,
    build_youtube_readiness_evaluation,
    clear_youtube_human_confirmation,
    get_youtube_project_compliance_response,
    get_youtube_approval_readiness,
    get_youtube_submission_profile_response,
    list_youtube_readiness_blockers,
    set_youtube_human_confirmation,
    update_youtube_project_compliance,
    update_youtube_submission_profile,
)


router = APIRouter(
    prefix="/social-connections",
    tags=["social-connections"],
)


@router.get("", response_model=SocialConnectionListResponse)
def get_social_connections(
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    return SocialConnectionListResponse(items=list_social_connections(db))


@router.post(
    "/youtube/authorize",
    response_model=SocialAuthorizeResponse,
    dependencies=[
        Depends(require_csrf_protection),
        Depends(
            limit_from_settings(
                "youtube-authorize",
                attempts_setting="sensitive_rate_limit_attempts",
                window_setting="sensitive_rate_limit_window_seconds",
                include_account=True,
            )
        ),
    ],
)
def authorize_youtube_connection(
    payload: SocialAuthorizeRequest,
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    try:
        return SocialAuthorizeResponse(**begin_youtube_authorization(db, payload.return_path))
    except SocialConnectionConfigurationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/youtube/callback")
def youtube_callback(
    state: str | None = Query(default=None),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        return RedirectResponse(complete_youtube_callback(db, state=state, code=code, error=error), status_code=302)
    except SocialConnectionConfigurationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/youtube/compliance", response_model=YouTubeProjectComplianceResponse)
def get_youtube_compliance(
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    return YouTubeProjectComplianceResponse(**get_youtube_project_compliance_response(db))


@router.patch(
    "/youtube/compliance",
    response_model=YouTubeProjectComplianceResponse,
    dependencies=[
        Depends(require_csrf_protection),
        Depends(
            limit_from_settings(
                "youtube-compliance-write",
                attempts_setting="compliance_write_rate_limit_attempts",
                window_setting="compliance_write_rate_limit_window_seconds",
                include_account=True,
            )
        ),
    ],
)
def update_youtube_compliance(
    payload: YouTubeProjectComplianceUpdateRequest,
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    try:
        return YouTubeProjectComplianceResponse(
            **update_youtube_project_compliance(
                db,
                compliance_status=payload.compliance_status,
                submission_date=payload.submission_date,
                approval_date=payload.approval_date,
                case_reference=payload.case_reference,
                admin_note=payload.admin_note,
                confirm_audit_approved=payload.confirm_audit_approved,
                confirm_google_audit_approval_received=payload.confirm_google_audit_approval_received,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except YouTubeComplianceConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.to_detail()) from exc


@router.get("/youtube/compliance/profile", response_model=YouTubeSubmissionProfileResponse)
def get_youtube_compliance_profile(
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    return YouTubeSubmissionProfileResponse(**get_youtube_submission_profile_response(db))


@router.patch(
    "/youtube/compliance/profile",
    response_model=YouTubeSubmissionProfileResponse,
    dependencies=[
        Depends(require_csrf_protection),
        Depends(
            limit_from_settings(
                "youtube-compliance-profile-write",
                attempts_setting="compliance_write_rate_limit_attempts",
                window_setting="compliance_write_rate_limit_window_seconds",
                include_account=True,
            )
        ),
    ],
)
def update_youtube_compliance_profile(
    payload: YouTubeSubmissionProfileUpdateRequest,
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    try:
        return YouTubeSubmissionProfileResponse(
            **update_youtube_submission_profile(
                db,
                application_display_name=payload.application_display_name,
                product_description=payload.product_description,
                organization_name=payload.organization_name,
                support_contact=payload.support_contact,
                privacy_policy_url=payload.privacy_policy_url,
                terms_of_service_url=payload.terms_of_service_url,
                application_homepage_url=payload.application_homepage_url,
                production_oauth_redirect_uri=payload.production_oauth_redirect_uri,
                production_frontend_url=payload.production_frontend_url,
                production_api_url=payload.production_api_url,
                data_retention_summary=payload.data_retention_summary,
                user_data_deletion_summary=payload.user_data_deletion_summary,
                token_revocation_summary=payload.token_revocation_summary,
                account_disconnection_summary=payload.account_disconnection_summary,
                quota_monitoring_summary=payload.quota_monitoring_summary,
                incident_response_summary=payload.incident_response_summary,
                security_contact_summary=payload.security_contact_summary,
                intended_submission_date=payload.intended_submission_date,
                submission_case_reference=payload.submission_case_reference,
                reviewed_by=payload.reviewed_by,
                admin_note=payload.admin_note,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put(
    "/youtube/compliance/confirmations/{confirmation_key}",
    response_model=YouTubeSubmissionProfileResponse,
    dependencies=[
        Depends(require_csrf_protection),
        Depends(
            limit_from_settings(
                "youtube-compliance-confirmation-write",
                attempts_setting="compliance_write_rate_limit_attempts",
                window_setting="compliance_write_rate_limit_window_seconds",
                include_account=True,
            )
        ),
    ],
)
def set_youtube_compliance_confirmation(
    confirmation_key: str,
    payload: YouTubeHumanConfirmationUpdateRequest,
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    try:
        return YouTubeSubmissionProfileResponse(
            **set_youtube_human_confirmation(
                db,
                confirmation_key=confirmation_key,
                completed=payload.completed,
                reviewed_by=payload.reviewed_by,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete(
    "/youtube/compliance/confirmations/{confirmation_key}",
    response_model=YouTubeSubmissionProfileResponse,
    dependencies=[
        Depends(require_csrf_protection),
        Depends(
            limit_from_settings(
                "youtube-compliance-confirmation-clear",
                attempts_setting="compliance_write_rate_limit_attempts",
                window_setting="compliance_write_rate_limit_window_seconds",
                include_account=True,
            )
        ),
    ],
)
def clear_youtube_compliance_confirmation(
    confirmation_key: str,
    reviewed_by: str | None = Query(default=None),
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    try:
        return YouTubeSubmissionProfileResponse(
            **clear_youtube_human_confirmation(
                db,
                confirmation_key=confirmation_key,
                reviewed_by=reviewed_by,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/youtube/compliance/readiness", response_model=YouTubeReadinessEvaluationResponse)
def get_youtube_compliance_readiness(
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    return YouTubeReadinessEvaluationResponse(**build_youtube_readiness_evaluation(db))


@router.get("/youtube/compliance/blockers", response_model=list[YouTubeReadinessBlockerResponse])
def get_youtube_compliance_blockers(
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    return [YouTubeReadinessBlockerResponse(**item) for item in list_youtube_readiness_blockers(db)]


@router.get("/youtube/compliance/approval-readiness")
def get_youtube_compliance_approval_readiness(
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    return get_youtube_approval_readiness(db)


@router.get("/youtube/compliance/report", response_model=YouTubeComplianceSubmissionPackageResponse)
@router.get("/youtube/compliance/package", response_model=YouTubeComplianceSubmissionPackageResponse)
def get_youtube_compliance_report(
    format: Literal["json", "markdown", "checklist"] = Query(default="json"),
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    report = build_youtube_audit_readiness_report(db)
    if format == "markdown":
        return PlainTextResponse(report["markdown"])
    if format == "checklist":
        return PlainTextResponse(report["checklist_markdown"])
    return YouTubeComplianceSubmissionPackageResponse(**report)


@router.post(
    "/{connection_id}/refresh",
    response_model=SocialConnectionMutationResponse,
    dependencies=[Depends(require_csrf_protection)],
)
def refresh_connection(
    connection_id: UUID,
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    try:
        return SocialConnectionMutationResponse(connection=refresh_social_connection(db, str(connection_id)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SocialConnectionConfigurationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete(
    "/{connection_id}",
    response_model=SocialConnectionMutationResponse,
    dependencies=[Depends(require_csrf_protection)],
)
def disconnect_connection(
    connection_id: UUID,
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    try:
        return SocialConnectionMutationResponse(connection=disconnect_social_connection(db, str(connection_id)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
