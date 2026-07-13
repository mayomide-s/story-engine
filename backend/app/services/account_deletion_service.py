from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Account,
    Asset,
    ContentIdea,
    GenerationCost,
    IdeaQueueItem,
    ManualPostPackage,
    NarrationDraft,
    NarrationRender,
    OAuthState,
    PerformanceLearning,
    PerformanceSnapshot,
    PipelineEvent,
    PipelineRun,
    PlatformPost,
    PromptLog,
    PublicationJob,
    PublicationTarget,
    QualityCheck,
    Script,
    SocialConnection,
    StoryAdherenceHumanReview,
    StoryAdherenceReview,
    Storyboard,
    Video,
    YouTubeProjectCompliance,
)
from app.services.access_service import validate_access_password
from app.services.pipeline_service import DEFAULT_ACCOUNT_NAME
from app.services.providers import get_storage_provider


ACCOUNT_DELETION_CONFIRMATION_PHRASE = "DELETE MY ACCOUNT"
ACCOUNT_DELETION_CONFIRMATION_REQUIRED_CODE = "account_deletion_confirmation_required"
ACCOUNT_DELETION_PASSWORD_REQUIRED_CODE = "account_deletion_password_required"
DEFAULT_RETENTION_MONTHS = 12


class AccountDeletionConflictError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _naive_utcnow() -> datetime:
    return _utcnow().replace(tzinfo=None)


def _get_default_account_row(db: Session) -> Account:
    account = db.query(Account).filter(Account.name == DEFAULT_ACCOUNT_NAME).first()
    if account is None:
        raise ValueError("Default account not found.")
    return account


def _connected_social_connections(db: Session, account_id: str) -> list[SocialConnection]:
    return (
        db.query(SocialConnection)
        .filter(SocialConnection.account_id == account_id)
        .order_by(SocialConnection.platform.asc(), SocialConnection.created_at.asc())
        .all()
    )


def _account_owned_run_ids(db: Session, account_id: str) -> list[str]:
    return [item.id for item in db.query(PipelineRun.id).filter(PipelineRun.account_id == account_id).all()]


def _count(query) -> int:
    return int(query.count())


def _build_preview_counts(db: Session, account: Account) -> dict[str, int]:
    run_ids = _account_owned_run_ids(db, account.id)
    platform_post_ids = [item.id for item in db.query(PlatformPost.id).filter(PlatformPost.pipeline_run_id.in_(run_ids)).all()] if run_ids else []

    return {
        "connected_accounts": _count(db.query(SocialConnection).filter(SocialConnection.account_id == account.id)),
        "idea_queue_items": _count(db.query(IdeaQueueItem).filter(IdeaQueueItem.account_id == account.id)),
        "pipeline_runs": _count(db.query(PipelineRun).filter(PipelineRun.account_id == account.id)),
        "assets": _count(db.query(Asset).filter(Asset.pipeline_run_id.in_(run_ids))) if run_ids else 0,
        "publication_jobs": _count(db.query(PublicationJob).filter(PublicationJob.pipeline_run_id.in_(run_ids))) if run_ids else 0,
        "publication_targets": _count(
            db.query(PublicationTarget)
            .join(PublicationJob, PublicationJob.id == PublicationTarget.publication_job_id)
            .filter(PublicationJob.pipeline_run_id.in_(run_ids))
        ) if run_ids else 0,
        "platform_posts": _count(db.query(PlatformPost).filter(PlatformPost.pipeline_run_id.in_(run_ids))) if run_ids else 0,
        "performance_snapshots": _count(db.query(PerformanceSnapshot).filter(PerformanceSnapshot.platform_post_id.in_(platform_post_ids))) if platform_post_ids else 0,
        "performance_learnings": _count(db.query(PerformanceLearning).filter(PerformanceLearning.pipeline_run_id.in_(run_ids))) if run_ids else 0,
        "pipeline_events": _count(db.query(PipelineEvent).filter(PipelineEvent.pipeline_run_id.in_(run_ids))) if run_ids else 0,
        "prompt_logs": _count(db.query(PromptLog).filter(PromptLog.pipeline_run_id.in_(run_ids))) if run_ids else 0,
        "generation_costs": _count(db.query(GenerationCost).filter(GenerationCost.pipeline_run_id.in_(run_ids))) if run_ids else 0,
        "quality_checks": _count(db.query(QualityCheck).filter(QualityCheck.pipeline_run_id.in_(run_ids))) if run_ids else 0,
        "narration_drafts": _count(db.query(NarrationDraft).filter(NarrationDraft.pipeline_run_id.in_(run_ids))) if run_ids else 0,
        "narration_renders": _count(db.query(NarrationRender).filter(NarrationRender.pipeline_run_id.in_(run_ids))) if run_ids else 0,
        "compliance_profile": 1 if db.query(YouTubeProjectCompliance.id).first() is not None else 0,
    }


def build_account_deletion_preview(db: Session) -> dict[str, Any]:
    account = _get_default_account_row(db)
    counts = _build_preview_counts(db, account)
    settings = get_settings()
    connections = _connected_social_connections(db, account.id)
    return {
        "account_status": account.account_status,
        "can_delete": account.account_status == "active",
        "requires_password_confirmation": bool(settings.auth_enabled),
        "requires_recent_authentication": False,
        "confirmation_phrase": ACCOUNT_DELETION_CONFIRMATION_PHRASE,
        "provider_video_warning": "Videos already uploaded to YouTube or other providers will remain online and must be removed on those platforms separately.",
        "connected_accounts": [
            {
                "platform": item.platform,
                "display_name": item.display_name,
                "username": item.username,
            }
            for item in connections
        ],
        "deletion_categories": [
            {
                "key": "social-connections",
                "title": "Connected social accounts",
                "count": counts["connected_accounts"],
                "description": "Connected YouTube account records will be disconnected and removed from Story Engine.",
            },
            {
                "key": "drafts-and-runs",
                "title": "Pipeline runs and generated content",
                "count": counts["pipeline_runs"] + counts["assets"] + counts["narration_drafts"] + counts["narration_renders"],
                "description": "Runs, generated assets, narration records, scripts, storyboards, and related content metadata will be deleted.",
            },
            {
                "key": "publishing-history",
                "title": "Publication history",
                "count": counts["publication_jobs"] + counts["publication_targets"] + counts["platform_posts"] + counts["performance_snapshots"] + counts["performance_learnings"],
                "description": "Publication jobs, publication targets, platform posts, performance snapshots, and performance learnings will be deleted from Story Engine.",
            },
            {
                "key": "operational-records",
                "title": "Operational run records",
                "count": counts["pipeline_events"] + counts["prompt_logs"] + counts["generation_costs"] + counts["quality_checks"] + counts["idea_queue_items"],
                "description": "Prompt logs, generation-cost entries, quality checks, idea queue items, and run events tied to the account will be deleted.",
            },
        ],
        "anonymised_categories": [
            {
                "key": "account-tombstone",
                "title": "Account tombstone",
                "count": 1,
                "description": "A minimal deleted-account record is retained to prevent reactivation and keep deletion idempotent.",
            },
            {
                "key": "compliance-profile",
                "title": "Compliance submission profile",
                "count": counts["compliance_profile"],
                "description": "Shared YouTube compliance profile fields that contain personal or reviewer-facing information will be cleared and reset.",
            },
        ],
        "temporarily_retained_categories": [
            {
                "key": "deleted-account-marker",
                "title": "Deleted-account marker",
                "count": 1,
                "description": "The deleted-account marker is retained for up to 12 months for security review and to prevent silent account reactivation.",
            },
        ],
    }


def _validate_account_deletion_request(
    *,
    confirmation_phrase: str,
    acknowledge_provider_videos_remain_online: bool,
    password: str | None,
) -> None:
    settings = get_settings()
    if confirmation_phrase.strip() != ACCOUNT_DELETION_CONFIRMATION_PHRASE:
        raise AccountDeletionConflictError(
            ACCOUNT_DELETION_CONFIRMATION_REQUIRED_CODE,
            "Type DELETE MY ACCOUNT exactly to continue.",
        )
    if not acknowledge_provider_videos_remain_online:
        raise AccountDeletionConflictError(
            ACCOUNT_DELETION_CONFIRMATION_REQUIRED_CODE,
            "You must acknowledge that uploaded provider videos remain online.",
        )
    if settings.auth_enabled:
        if not password or not password.strip():
            raise AccountDeletionConflictError(
                ACCOUNT_DELETION_PASSWORD_REQUIRED_CODE,
                "Password confirmation is required before deleting the account.",
            )
        validate_access_password(password, settings)


def validate_account_deletion(
    db: Session,
    *,
    confirmation_phrase: str,
    acknowledge_provider_videos_remain_online: bool,
    password: str | None,
) -> dict[str, Any]:
    preview = build_account_deletion_preview(db)
    if preview["account_status"] == "deleted":
        return {
            "can_delete": False,
            "requires_password_confirmation": preview["requires_password_confirmation"],
            "validation_message": "The account has already been deleted.",
            "preview": preview,
        }
    _validate_account_deletion_request(
        confirmation_phrase=confirmation_phrase,
        acknowledge_provider_videos_remain_online=acknowledge_provider_videos_remain_online,
        password=password,
    )
    return {
        "can_delete": True,
        "requires_password_confirmation": preview["requires_password_confirmation"],
        "validation_message": "Account deletion validation passed.",
        "preview": preview,
    }


def _clear_and_delete_social_connections(db: Session, account_id: str) -> tuple[int, int]:
    connections = _connected_social_connections(db, account_id)
    disconnected_count = 0
    for connection in connections:
        if connection.connection_status != "disconnected":
            disconnected_count += 1
        connection.connection_status = "disconnected"
        connection.encrypted_access_token = None
        connection.encrypted_refresh_token = None
        connection.token_cipher_version = None
        connection.token_expires_at = None
        connection.is_default = False
        connection.disconnected_at = _utcnow()
        connection.updated_at = _utcnow()
        db.add(connection)
    db.flush()
    deleted_count = len(connections)
    for connection in connections:
        db.delete(connection)
    return disconnected_count, deleted_count


def _reset_youtube_compliance_profile(db: Session) -> None:
    record = db.query(YouTubeProjectCompliance).filter(YouTubeProjectCompliance.platform == "youtube").first()
    if record is None:
        return
    record.compliance_status = "private_only"
    record.status_updated_at = _utcnow()
    record.submission_date = None
    record.approval_date = None
    record.case_reference = None
    record.application_display_name = None
    record.product_description = None
    record.organization_name = None
    record.support_contact = None
    record.privacy_policy_url = None
    record.terms_of_service_url = None
    record.application_homepage_url = None
    record.production_oauth_redirect_uri = None
    record.production_frontend_url = None
    record.production_api_url = None
    record.data_retention_summary = None
    record.user_data_deletion_summary = None
    record.token_revocation_summary = None
    record.account_disconnection_summary = None
    record.quota_monitoring_summary = None
    record.incident_response_summary = None
    record.security_contact_summary = None
    record.intended_submission_date = None
    record.last_reviewed_at = None
    record.reviewed_by = None
    record.human_confirmations_json = {}
    record.admin_note = None
    record.updated_at = _utcnow()
    db.add(record)


def _local_or_remote_asset_cleanup(storage_key: str) -> bool:
    storage = get_storage_provider()
    try:
        if getattr(storage, "name", "") == "local":
            Path(storage.resolve_path(storage_key)).unlink(missing_ok=True)
            return True
        if getattr(storage, "name", "") == "r2":
            storage.client.delete_object(Bucket=storage.bucket_name, Key=storage_key)
            return True
    except Exception:
        return False
    return False


def _delete_run_owned_records(db: Session, run: PipelineRun) -> dict[str, int | list[str]]:
    package = db.get(ManualPostPackage, run.manual_post_package_id) if run.manual_post_package_id else None
    if package is not None:
        package.winner_platform_post_id = None
        package.final_narration_render_id = None
        db.add(package)
    run.idea_id = None
    run.script_id = None
    run.storyboard_id = None
    run.video_id = None
    run.manual_post_package_id = None
    db.add(run)
    db.flush()

    post_ids = [item.id for item in db.query(PlatformPost.id).filter(PlatformPost.pipeline_run_id == run.id).all()]
    job_ids = [item.id for item in db.query(PublicationJob.id).filter(PublicationJob.pipeline_run_id == run.id).all()]
    asset_storage_keys = [item.storage_key for item in db.query(Asset.storage_key).filter(Asset.pipeline_run_id == run.id).all()]

    snapshot_count = (
        db.query(PerformanceSnapshot)
        .filter(PerformanceSnapshot.platform_post_id.in_(post_ids))
        .delete(synchronize_session=False)
        if post_ids
        else 0
    )
    learning_count = db.query(PerformanceLearning).filter(PerformanceLearning.pipeline_run_id == run.id).delete(synchronize_session=False)
    target_count = (
        db.query(PublicationTarget)
        .filter(PublicationTarget.publication_job_id.in_(job_ids))
        .delete(synchronize_session=False)
        if job_ids
        else 0
    )
    job_count = db.query(PublicationJob).filter(PublicationJob.pipeline_run_id == run.id).delete(synchronize_session=False)
    post_count = db.query(PlatformPost).filter(PlatformPost.pipeline_run_id == run.id).delete(synchronize_session=False)
    human_review_count = db.query(StoryAdherenceHumanReview).filter(StoryAdherenceHumanReview.pipeline_run_id == run.id).delete(synchronize_session=False)
    review_count = db.query(StoryAdherenceReview).filter(StoryAdherenceReview.pipeline_run_id == run.id).delete(synchronize_session=False)
    render_count = db.query(NarrationRender).filter(NarrationRender.pipeline_run_id == run.id).delete(synchronize_session=False)
    draft_count = db.query(NarrationDraft).filter(NarrationDraft.pipeline_run_id == run.id).delete(synchronize_session=False)
    quality_count = db.query(QualityCheck).filter(QualityCheck.pipeline_run_id == run.id).delete(synchronize_session=False)
    prompt_count = db.query(PromptLog).filter(PromptLog.pipeline_run_id == run.id).delete(synchronize_session=False)
    cost_count = db.query(GenerationCost).filter(GenerationCost.pipeline_run_id == run.id).delete(synchronize_session=False)
    event_count = db.query(PipelineEvent).filter(PipelineEvent.pipeline_run_id == run.id).delete(synchronize_session=False)
    asset_count = db.query(Asset).filter(Asset.pipeline_run_id == run.id).delete(synchronize_session=False)
    idea_count = db.query(ContentIdea).filter(ContentIdea.pipeline_run_id == run.id).delete(synchronize_session=False)
    script_count = db.query(Script).filter(Script.pipeline_run_id == run.id).delete(synchronize_session=False)
    storyboard_count = db.query(Storyboard).filter(Storyboard.pipeline_run_id == run.id).delete(synchronize_session=False)
    video_count = db.query(Video).filter(Video.pipeline_run_id == run.id).delete(synchronize_session=False)
    package_count = db.query(ManualPostPackage).filter(ManualPostPackage.id == package.id).delete(synchronize_session=False) if package is not None else 0
    db.delete(run)

    return {
        "deleted_snapshot_count": int(snapshot_count),
        "deleted_learning_count": int(learning_count),
        "deleted_publication_target_count": int(target_count),
        "deleted_publication_job_count": int(job_count),
        "deleted_platform_post_count": int(post_count),
        "deleted_event_count": int(event_count + human_review_count + review_count + draft_count + render_count + quality_count + prompt_count + cost_count + idea_count + script_count + storyboard_count + video_count + package_count),
        "deleted_asset_count": int(asset_count),
        "asset_storage_keys": asset_storage_keys,
    }


def execute_account_deletion(
    db: Session,
    *,
    confirmation_phrase: str,
    acknowledge_provider_videos_remain_online: bool,
    password: str | None,
) -> dict[str, Any]:
    account = _get_default_account_row(db)
    if account.account_status == "deleted":
        return {
            "deleted": True,
            "account_status": "deleted",
            "message": "The account has already been deleted.",
            "disconnected_connection_count": 0,
            "deleted_social_connection_count": 0,
            "deleted_pipeline_run_count": 0,
            "deleted_asset_count": 0,
            "deleted_local_file_count": 0,
            "deleted_publication_job_count": 0,
            "deleted_publication_target_count": 0,
            "deleted_platform_post_count": 0,
            "deleted_snapshot_count": 0,
            "deleted_learning_count": 0,
        }

    _validate_account_deletion_request(
        confirmation_phrase=confirmation_phrase,
        acknowledge_provider_videos_remain_online=acknowledge_provider_videos_remain_online,
        password=password,
    )

    account.account_status = "deletion_in_progress"
    account.deletion_started_at = _naive_utcnow()
    account.updated_at = _naive_utcnow()
    db.add(account)
    db.flush()

    disconnected_count, deleted_social_connection_count = _clear_and_delete_social_connections(db, account.id)
    db.query(OAuthState).filter(OAuthState.account_id == account.id).delete(synchronize_session=False)
    db.query(IdeaQueueItem).filter(IdeaQueueItem.account_id == account.id).delete(synchronize_session=False)

    run_ids = _account_owned_run_ids(db, account.id)
    runs = db.query(PipelineRun).filter(PipelineRun.id.in_(run_ids)).all() if run_ids else []

    deleted_asset_count = 0
    deleted_publication_job_count = 0
    deleted_publication_target_count = 0
    deleted_platform_post_count = 0
    deleted_snapshot_count = 0
    deleted_learning_count = 0
    local_cleanup_keys: list[str] = []

    for run in runs:
        result = _delete_run_owned_records(db, run)
        deleted_asset_count += int(result["deleted_asset_count"])
        deleted_publication_job_count += int(result["deleted_publication_job_count"])
        deleted_publication_target_count += int(result["deleted_publication_target_count"])
        deleted_platform_post_count += int(result["deleted_platform_post_count"])
        deleted_snapshot_count += int(result["deleted_snapshot_count"])
        deleted_learning_count += int(result["deleted_learning_count"])
        local_cleanup_keys.extend(result["asset_storage_keys"])

    _reset_youtube_compliance_profile(db)

    account.niche = "deleted-account"
    account.account_config_json = {}
    account.account_status = "deleted"
    account.deleted_at = _naive_utcnow()
    account.updated_at = _naive_utcnow()
    db.add(account)
    db.commit()

    deleted_local_file_count = 0
    for storage_key in local_cleanup_keys:
        if _local_or_remote_asset_cleanup(storage_key):
            deleted_local_file_count += 1

    return {
        "deleted": True,
        "account_status": "deleted",
        "message": "Your Story Engine account has been permanently deleted. Uploaded provider videos remain online until you remove them on those platforms.",
        "disconnected_connection_count": disconnected_count,
        "deleted_social_connection_count": deleted_social_connection_count,
        "deleted_pipeline_run_count": len(run_ids),
        "deleted_asset_count": deleted_asset_count,
        "deleted_local_file_count": deleted_local_file_count,
        "deleted_publication_job_count": deleted_publication_job_count,
        "deleted_publication_target_count": deleted_publication_target_count,
        "deleted_platform_post_count": deleted_platform_post_count,
        "deleted_snapshot_count": deleted_snapshot_count,
        "deleted_learning_count": deleted_learning_count,
    }


def build_retention_report(db: Session) -> dict[str, Any]:
    cutoff = _naive_utcnow() - timedelta(days=DEFAULT_RETENTION_MONTHS * 30)
    expired_deleted_accounts = _count(
        db.query(Account).filter(Account.account_status == "deleted", Account.deleted_at.is_not(None), Account.deleted_at <= cutoff)
    )
    expired_oauth_states = _count(
        db.query(OAuthState).filter(
            OAuthState.created_at <= cutoff,
        )
    )

    return {
        "default_retention_months": DEFAULT_RETENTION_MONTHS,
        "generated_at": _utcnow(),
        "categories": [
            {
                "key": "deleted-account-tombstones",
                "title": "Deleted-account tombstones",
                "retention_months": DEFAULT_RETENTION_MONTHS,
                "cleanup_action": "review_for_purge",
                "description": "Minimal deleted-account markers may be reviewed for purge after 12 months when no longer needed for security or anti-reactivation safeguards.",
                "automatically_deleted": False,
                "expired_record_count": expired_deleted_accounts,
            },
            {
                "key": "oauth-state-records",
                "title": "OAuth state records",
                "retention_months": DEFAULT_RETENTION_MONTHS,
                "cleanup_action": "eligible_for_cleanup",
                "description": "Expired or consumed OAuth state records are eligible for cleanup once they are no longer needed for audit or troubleshooting.",
                "automatically_deleted": False,
                "expired_record_count": expired_oauth_states,
            },
            {
                "key": "youtube-compliance-profile",
                "title": "YouTube compliance profile",
                "retention_months": DEFAULT_RETENTION_MONTHS,
                "cleanup_action": "excluded_from_automatic_cleanup",
                "description": "Compliance profile records are shared product configuration and are excluded from automatic cleanup in this sprint.",
                "automatically_deleted": False,
                "expired_record_count": 0,
            },
        ],
    }
