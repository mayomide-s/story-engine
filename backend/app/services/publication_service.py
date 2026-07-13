from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    Asset,
    ManualPostPackage,
    PipelineRun,
    PipelineStatus,
    PublicationJob,
    PublicationTarget,
    SocialConnection,
)
from app.schemas.publication import PublicationJobDraftRequest, PublicationJobResponse, PublicationTargetResponse
from app.services.final_asset_service import get_final_asset_selection_payload, get_selected_final_asset
from app.services.pipeline_service import add_event, seed_default_account
from app.services.providers import get_storage_provider


YOUTUBE_PLATFORM = "youtube"
ACTIVE_JOB_STATUSES = {"draft", "ready", "approved", "active"}
ACTIVE_TARGET_STATES = {"pending", "validating", "queued", "uploading", "processing"}
SUCCESS_TARGET_STATES = {"uploaded_private", "published"}
FAILURE_TARGET_STATES = {"retryable_failure", "permanent_failure", "outcome_uncertain"}


class PublicationConflictError(RuntimeError):
    """Raised when a publication action conflicts with the current run or stored data."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _require_completed_run_and_package(db: Session, run_id: str) -> tuple[PipelineRun, ManualPostPackage]:
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise ValueError("Pipeline run not found")
    if run.status != PipelineStatus.COMPLETED:
        raise PublicationConflictError("Publication requires a completed pipeline run.")
    if not run.manual_post_package_id:
        raise PublicationConflictError("Publication requires an existing manual post package.")
    package = db.get(ManualPostPackage, run.manual_post_package_id)
    if package is None:
        raise PublicationConflictError("Publication requires an existing manual post package.")
    return run, package


def _require_selected_video_asset(
    db: Session,
    run: PipelineRun,
    package: ManualPostPackage,
) -> tuple[dict[str, Any], Asset]:
    if not package.final_asset_id:
        raise PublicationConflictError("Publication requires a selected final asset.")
    asset = db.get(Asset, package.final_asset_id)
    if asset is None:
        raise PublicationConflictError("Publication requires a selected final asset.")
    selection = get_final_asset_selection_payload(db, run, package)
    if selection is None:
        raise PublicationConflictError("Publication requires a selected final asset.")
    if asset.pipeline_run_id != run.id:
        raise PublicationConflictError("Selected final asset does not belong to this pipeline run.")
    if asset.mime_type != "video/mp4":
        raise PublicationConflictError("Selected final asset must be an MP4 video.")
    return selection, asset


def _read_asset_bytes(asset: Asset) -> bytes:
    storage = get_storage_provider()
    if getattr(storage, "name", "") == "local":
        path = Path(storage.resolve_path(asset.storage_key))
        if not path.exists() or not path.is_file():
            raise PublicationConflictError("Selected final asset file is not readable.")
        return path.read_bytes()
    if getattr(storage, "name", "") == "r2":
        response = storage.client.get_object(Bucket=storage.bucket_name, Key=asset.storage_key)
        return response["Body"].read()
    raise PublicationConflictError("Selected final asset storage provider is not supported for publication.")


def _asset_sha256(asset: Asset) -> str:
    return hashlib.sha256(_read_asset_bytes(asset)).hexdigest()


def _require_active_youtube_connection(db: Session, connection_id: str | None = None) -> SocialConnection:
    account = seed_default_account(db)
    query = db.query(SocialConnection).filter(
        SocialConnection.account_id == account.id,
        SocialConnection.platform == YOUTUBE_PLATFORM,
        SocialConnection.connection_status == "active",
    )
    if connection_id:
        query = query.filter(SocialConnection.id == connection_id)
    else:
        query = query.filter(SocialConnection.is_default.is_(True))
    connection = query.first()
    if connection is None:
        raise PublicationConflictError("An active default YouTube connection is required.")
    if connection.platform != YOUTUBE_PLATFORM:
        raise PublicationConflictError("A YouTube connection is required.")
    if not set(connection.granted_scopes_json or []).issuperset({"https://www.googleapis.com/auth/youtube.upload"}):
        raise PublicationConflictError("The active YouTube connection is missing the youtube.upload scope.")
    return connection


def _normalize_target_payload(payload: PublicationJobDraftRequest) -> dict[str, Any]:
    return {
        "platform": YOUTUBE_PLATFORM,
        "visibility": payload.privacy,
        "title": payload.title.strip(),
        "caption": payload.caption.strip() if payload.caption else None,
        "tags": list(payload.tags),
        "category_id": payload.category_id,
        "options": {
            "category_id": payload.category_id,
            "self_declared_made_for_kids": payload.self_declared_made_for_kids,
            "contains_synthetic_media": payload.contains_synthetic_media,
        },
    }


def _target_idempotency_key(
    *,
    run_id: str,
    connection_id: str,
    asset_id: str,
    selection_revision: int,
    normalized_target: dict[str, Any],
) -> str:
    raw = json.dumps(
        {
            "run_id": run_id,
            "connection_id": connection_id,
            "asset_id": asset_id,
            "selection_revision": selection_revision,
            **normalized_target,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"youtube:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _visibility_semantics(visibility: str) -> tuple[bool, str]:
    if visibility == "private":
        return (
            False,
            "Private YouTube uploads are technical upload successes only and must not create PlatformPost rows.",
        )
    return (
        True,
        "Only confirmed unlisted or public YouTube uploads may later create PlatformPost rows.",
    )


def _target_available_actions(target: PublicationTarget) -> list[str]:
    actions: list[str] = []
    if target.state in {"pending", "queued"}:
        actions.append("cancel")
    if target.state in {"pending", "queued"}:
        actions.append("dispatch")
    if target.state == "retryable_failure":
        actions.append("retry")
    if target.provider_submission_id and target.state in {"processing", "retryable_failure", "outcome_uncertain", "uploading"}:
        actions.append("reconcile")
    return actions


def _job_available_actions(job: PublicationJob, targets: list[PublicationTarget]) -> list[str]:
    actions: list[str] = []
    if job.status == "draft":
        actions.extend(["approve", "cancel"])
    elif job.status == "approved":
        actions.append("dispatch")
        if all(target.state in {"pending", "queued"} for target in targets):
            actions.append("cancel")
    elif job.status == "active" and any("reconcile" in _target_available_actions(target) for target in targets):
        actions.append("reconcile")
    return actions


def _serialize_target(target: PublicationTarget, connection: SocialConnection | None = None) -> dict[str, Any]:
    eligible, semantics = _visibility_semantics(target.visibility)
    options = dict(target.options_json or {})
    total = target.upload_bytes_total
    sent = target.upload_bytes_sent
    progress_percent = None
    if total and total > 0 and sent is not None:
        progress_percent = max(0, min(100, int((sent / total) * 100)))
    return PublicationTargetResponse(
        id=target.id,
        social_connection_id=target.social_connection_id,
        channel_display_name=connection.display_name if connection else None,
        channel_username=connection.username if connection else None,
        channel_external_account_id=connection.external_account_id if connection else None,
        platform=target.platform,
        visibility=target.visibility,
        actual_visibility=target.actual_visibility,
        title=target.title,
        caption=target.caption,
        tags=list(target.tags_json or []),
        category_id=str(options.get("category_id") or ""),
        self_declared_made_for_kids=bool(options.get("self_declared_made_for_kids")),
        contains_synthetic_media=bool(options.get("contains_synthetic_media")),
        options=options,
        state=target.state,
        idempotency_key=target.idempotency_key,
        provider_video_id=target.provider_submission_id,
        provider_submission_id=target.provider_submission_id,
        provider_media_id=target.provider_media_id,
        provider_upload_status=target.provider_upload_status,
        provider_processing_status=target.provider_processing_status,
        public_post_url=target.public_post_url,
        platform_post_id=target.platform_post_id,
        attempt_count=target.attempt_count,
        upload_bytes_total=target.upload_bytes_total,
        upload_bytes_sent=target.upload_bytes_sent,
        upload_progress_percent=progress_percent,
        next_poll_at=target.next_poll_at,
        processing_last_checked_at=target.processing_last_checked_at,
        outcome_confirmed_at=target.outcome_confirmed_at,
        last_error_code=target.last_error_code,
        last_error_message=target.last_error_message,
        reconnect_required=bool(target.last_error_code in {"youtube_credentials_invalid", "youtube_scope_missing", "youtube_oauth_error"}),
        submitted_at=target.submitted_at,
        published_at=target.published_at,
        created_at=target.created_at,
        updated_at=target.updated_at,
        platform_post_creation_eligible=eligible,
        visibility_semantics=semantics,
        available_actions=_target_available_actions(target),
    ).model_dump(mode="json")


def get_publication_job(db: Session, job_id: str) -> dict[str, Any]:
    job = db.get(PublicationJob, job_id)
    if job is None:
        raise ValueError("Publication job not found")
    run = db.get(PipelineRun, job.pipeline_run_id)
    package = db.get(ManualPostPackage, job.manual_post_package_id)
    current_selection = (
        get_final_asset_selection_payload(db, run, package)
        if run is not None and package is not None
        else None
    )
    current_asset_id = None
    current_revision = None
    if isinstance(current_selection, dict):
        asset_payload = current_selection.get("asset")
        if isinstance(asset_payload, dict):
            current_asset_id = asset_payload.get("id")
        current_revision = current_selection.get("selection_revision")
    targets = (
        db.query(PublicationTarget)
        .filter(PublicationTarget.publication_job_id == job.id)
        .order_by(PublicationTarget.created_at.asc(), PublicationTarget.id.asc())
        .all()
    )
    connection_ids = {target.social_connection_id for target in targets}
    connections = {
        connection.id: connection
        for connection in (
            db.query(SocialConnection)
            .filter(SocialConnection.id.in_(connection_ids))
            .all()
            if connection_ids
            else []
        )
    }
    return PublicationJobResponse(
        id=job.id,
        pipeline_run_id=job.pipeline_run_id,
        manual_post_package_id=job.manual_post_package_id,
        final_asset_id=job.final_asset_id,
        final_asset_selection_revision=job.final_asset_selection_revision,
        final_asset_source=job.final_asset_source,
        final_asset_sha256=job.final_asset_sha256,
        final_asset_metadata=dict(job.final_asset_metadata_json or {}),
        status=job.status,
        approved_at=job.approved_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
        targets=[_serialize_target(item, connections.get(item.social_connection_id)) for item in targets],
        selected_asset_is_frozen=True,
        selected_asset_has_changed_since_draft=bool(
            current_asset_id is not None
            and (
                current_asset_id != job.final_asset_id
                or current_revision != job.final_asset_selection_revision
            )
        ),
        available_actions=_job_available_actions(job, targets),
    ).model_dump(mode="json")


def get_latest_publication_job_for_run(db: Session, run_id: str) -> dict[str, Any]:
    job = (
        db.query(PublicationJob)
        .filter(PublicationJob.pipeline_run_id == run_id)
        .order_by(PublicationJob.created_at.desc(), PublicationJob.id.desc())
        .first()
    )
    if job is None:
        raise ValueError("Publication job not found")
    return get_publication_job(db, job.id)


def create_publication_job_draft(
    db: Session,
    run_id: str,
    payload: PublicationJobDraftRequest,
) -> dict[str, Any]:
    run, package = _require_completed_run_and_package(db, run_id)
    selection, asset = _require_selected_video_asset(db, run, package)
    connection = _require_active_youtube_connection(db, str(payload.connection_id) if payload.connection_id else None)
    asset_hash = _asset_sha256(asset)
    normalized_target = _normalize_target_payload(payload)
    idempotency_key = _target_idempotency_key(
        run_id=run.id,
        connection_id=connection.id,
        asset_id=asset.id,
        selection_revision=int(selection.get("selection_revision") or 0),
        normalized_target=normalized_target,
    )

    existing_target = (
        db.query(PublicationTarget)
        .join(PublicationJob, PublicationJob.id == PublicationTarget.publication_job_id)
        .filter(
            PublicationTarget.idempotency_key == idempotency_key,
            PublicationJob.status.in_(ACTIVE_JOB_STATUSES),
        )
        .first()
    )
    if existing_target is not None:
        return get_publication_job(db, existing_target.publication_job_id)

    job = PublicationJob(
        pipeline_run_id=run.id,
        manual_post_package_id=package.id,
        final_asset_id=asset.id,
        final_asset_selection_revision=int(selection.get("selection_revision") or 0),
        final_asset_source=str(selection.get("source") or asset.asset_type),
        final_asset_sha256=asset_hash,
        final_asset_metadata_json=dict(package.final_asset_metadata_json or {}),
        status="draft",
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(job)
    db.flush()

    target = PublicationTarget(
        publication_job_id=job.id,
        social_connection_id=connection.id,
        platform=YOUTUBE_PLATFORM,
        visibility=normalized_target["visibility"],
        title=normalized_target["title"],
        caption=normalized_target["caption"],
        tags_json=list(normalized_target["tags"]),
        options_json=dict(normalized_target["options"]),
        state="pending",
        idempotency_key=idempotency_key,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(target)
    db.flush()

    add_event(
        db,
        run.id,
        "publication.job_draft_created",
        "Publication job draft created",
        stage=run.current_stage.value if hasattr(run.current_stage, "value") else str(run.current_stage),
        metadata={
            "publication_job_id": job.id,
            "publication_target_id": target.id,
            "platform": target.platform,
            "visibility": target.visibility,
            "social_connection_id": connection.id,
            "final_asset_id": job.final_asset_id,
            "final_asset_selection_revision": job.final_asset_selection_revision,
        },
    )
    db.commit()
    return get_publication_job(db, job.id)


def validate_publication_asset_snapshot(db: Session, job: PublicationJob) -> None:
    run = db.get(PipelineRun, job.pipeline_run_id)
    package = db.get(ManualPostPackage, job.manual_post_package_id)
    if run is None or package is None:
        raise PublicationConflictError("Publication job references missing run data.")
    selection, asset = _require_selected_video_asset(db, run, package)
    current_revision = int(selection.get("selection_revision") or 0)
    if asset.id != job.final_asset_id or current_revision != job.final_asset_selection_revision:
        raise PublicationConflictError("The selected final asset has changed since this publication job was drafted.")
    if _asset_sha256(asset) != job.final_asset_sha256:
        raise PublicationConflictError("The frozen final asset no longer matches the stored publication hash.")


def approve_publication_job(db: Session, job_id: str) -> dict[str, Any]:
    job = db.get(PublicationJob, job_id)
    if job is None:
        raise ValueError("Publication job not found")
    if job.status in {"approved", "active", "published", "partially_published"}:
        return get_publication_job(db, job.id)
    if job.status == "cancelled":
        raise PublicationConflictError("Cancelled publication jobs cannot be approved.")

    validate_publication_asset_snapshot(db, job)
    job.status = "approved"
    job.approved_at = job.approved_at or _utcnow()
    job.updated_at = _utcnow()
    db.add(job)
    db.flush()

    run = db.get(PipelineRun, job.pipeline_run_id)
    add_event(
        db,
        job.pipeline_run_id,
        "publication.job_approved",
        "Publication job approved",
        stage=run.current_stage.value if run and hasattr(run.current_stage, "value") else str(run.current_stage) if run else None,
        metadata={
            "publication_job_id": job.id,
            "final_asset_id": job.final_asset_id,
            "final_asset_selection_revision": job.final_asset_selection_revision,
            "status": job.status,
        },
    )
    db.commit()
    return get_publication_job(db, job.id)


def cancel_publication_job(db: Session, job_id: str) -> dict[str, Any]:
    job = db.get(PublicationJob, job_id)
    if job is None:
        raise ValueError("Publication job not found")
    if job.status == "cancelled":
        return get_publication_job(db, job.id)
    if job.status not in {"draft", "ready", "approved"}:
        raise PublicationConflictError("Only unstarted publication jobs can be cancelled in Sprint 1A.")

    targets = (
        db.query(PublicationTarget)
        .filter(PublicationTarget.publication_job_id == job.id)
        .all()
    )
    if any(target.provider_submission_id or target.state not in {"pending", "queued"} for target in targets):
        raise PublicationConflictError("Publication jobs cannot be cancelled after provider submission has started.")
    job.status = "cancelled"
    job.updated_at = _utcnow()
    for target in targets:
        target.state = "cancelled"
        target.updated_at = _utcnow()
        db.add(target)
    db.add(job)
    db.flush()

    run = db.get(PipelineRun, job.pipeline_run_id)
    add_event(
        db,
        job.pipeline_run_id,
        "publication.job_cancelled",
        "Publication job cancelled",
        stage=run.current_stage.value if run and hasattr(run.current_stage, "value") else str(run.current_stage) if run else None,
        metadata={
            "publication_job_id": job.id,
            "publication_target_ids": [target.id for target in targets],
            "status": job.status,
        },
    )
    db.commit()
    return get_publication_job(db, job.id)
