from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Asset, ManualPostPackage, PipelineRun, PlatformPost, PublicationJob, PublicationTarget, SocialConnection
from app.providers.youtube.publishing import (
    YouTubeVideoState,
    canonical_watch_url,
    compute_retry_delay,
    fetch_youtube_video_state,
    initiate_resumable_upload,
    upload_media_chunks,
)
from app.schemas.publication import PublicationJobResponse, PublicationTargetResponse
from app.services.performance_service import create_platform_post_for_publication_target
from app.services.pipeline_service import add_event
from app.services.publication_error_service import PublicationProviderError
from app.services.publication_media_service import PublicationMediaError, open_publication_media, sha256_for_path
from app.services.publication_service import (
    PublicationConflictError,
    get_publication_job,
    validate_publication_asset_snapshot,
)
from app.services.security import redact_sensitive_data
from app.services.social_connection_service import refresh_youtube_connection_tokens_if_needed
from app.services.social_token_crypto import SocialTokenCryptoError, decrypt_secret, encrypt_secret


ACTIVE_TARGET_STATES = {"queued", "validating", "uploading", "processing"}
SUCCESS_TARGET_STATES = {"uploaded_private", "published"}
FAILURE_TARGET_STATES = {"retryable_failure", "permanent_failure", "outcome_uncertain"}

TARGET_STATE_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"queued", "cancelled"},
    "queued": {"queued", "validating", "cancelled", "retryable_failure", "permanent_failure", "outcome_uncertain"},
    "validating": {"uploading", "processing", "retryable_failure", "permanent_failure", "outcome_uncertain"},
    "uploading": {"uploading", "processing", "retryable_failure", "permanent_failure", "outcome_uncertain"},
    "processing": {"processing", "uploaded_private", "published", "retryable_failure", "permanent_failure", "outcome_uncertain"},
    "retryable_failure": {"queued", "processing", "outcome_uncertain", "permanent_failure"},
    "permanent_failure": set(),
    "outcome_uncertain": {"processing", "permanent_failure"},
    "uploaded_private": set(),
    "published": set(),
    "cancelled": set(),
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _coerce_stored_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _enqueue_start_target(target_id: str, *, countdown: int = 0) -> None:
    from app.workers.jobs import start_youtube_publication_target_task

    start_youtube_publication_target_task.apply_async(args=[target_id], countdown=countdown)


def _enqueue_poll_target(target_id: str, *, countdown: int = 0) -> None:
    from app.workers.jobs import poll_youtube_publication_target_task

    poll_youtube_publication_target_task.apply_async(args=[target_id], countdown=countdown)


def _add_publication_event(
    db: Session,
    run: PipelineRun,
    event_type: str,
    message: str,
    metadata: dict[str, Any],
) -> None:
    add_event(
        db,
        run.id,
        event_type,
        message,
        stage=run.current_stage.value if hasattr(run.current_stage, "value") else str(run.current_stage),
        metadata=redact_sensitive_data(metadata),
    )


def _assert_target_transition(current_state: str, next_state: str) -> None:
    if current_state == next_state:
        return
    allowed = TARGET_STATE_TRANSITIONS.get(current_state, set())
    if next_state not in allowed:
        raise PublicationConflictError(f"Cannot transition publication target from {current_state} to {next_state}.")


def _set_target_state(target: PublicationTarget, next_state: str, *, now: datetime | None = None) -> None:
    _assert_target_transition(target.state, next_state)
    if target.state == next_state:
        return
    target.state = next_state
    target.updated_at = now or _utcnow()


def _recalculate_job_status(db: Session, job: PublicationJob) -> None:
    targets = (
        db.query(PublicationTarget)
        .filter(PublicationTarget.publication_job_id == job.id)
        .all()
    )
    states = {target.state for target in targets}
    now = _utcnow()

    if job.status == "draft":
        return
    if states and states.issubset({"cancelled"}):
        job.status = "cancelled"
        job.completed_at = job.completed_at or now
    elif any(state in ACTIVE_TARGET_STATES for state in states):
        job.status = "active"
        job.completed_at = None
    elif states and states.issubset(SUCCESS_TARGET_STATES):
        job.status = "published"
        job.completed_at = job.completed_at or now
    elif any(state in SUCCESS_TARGET_STATES for state in states) and any(
        state in FAILURE_TARGET_STATES or state == "cancelled" for state in states
    ):
        job.status = "partially_published"
        job.completed_at = job.completed_at or now
    elif states and states.issubset(FAILURE_TARGET_STATES | {"cancelled"}):
        job.status = "failed"
        job.completed_at = job.completed_at or now
    elif job.approved_at:
        job.status = "approved"
        job.completed_at = None
    job.updated_at = now
    db.add(job)


def _encrypt_session_uri(session_uri: str | None) -> str | None:
    if not session_uri:
        return None
    encrypted, _ = encrypt_secret(session_uri, purpose="YouTube resumable upload session URI")
    return encrypted


def _decrypt_session_uri(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    return decrypt_secret(ciphertext, purpose="YouTube resumable upload session URI")


def _require_target_context(db: Session, target_id: str) -> tuple[PublicationTarget, PublicationJob, PipelineRun, ManualPostPackage, SocialConnection]:
    target = db.get(PublicationTarget, target_id)
    if target is None:
        raise ValueError("Publication target not found")
    job = db.get(PublicationJob, target.publication_job_id)
    if job is None:
        raise PublicationConflictError("Publication target references a missing publication job.")
    run = db.get(PipelineRun, job.pipeline_run_id)
    package = db.get(ManualPostPackage, job.manual_post_package_id)
    connection = db.get(SocialConnection, target.social_connection_id)
    if run is None or package is None or connection is None:
        raise PublicationConflictError("Publication target references missing run, package, or social connection data.")
    return target, job, run, package, connection


def get_publication_target(db: Session, target_id: str) -> dict[str, Any]:
    from app.services.publication_service import _serialize_target

    target, _job, _run, _package, connection = _require_target_context(db, target_id)
    return PublicationTargetResponse(**_serialize_target(target, connection)).model_dump(mode="json")


def get_run_publication_job(db: Session, run_id: str) -> dict[str, Any]:
    from app.services.publication_service import get_latest_publication_job_for_run

    return PublicationJobResponse(**get_latest_publication_job_for_run(db, run_id)).model_dump(mode="json")


def dispatch_publication_job(db: Session, job_id: str) -> dict[str, Any]:
    job = db.get(PublicationJob, job_id)
    if job is None:
        raise ValueError("Publication job not found")
    if job.status == "draft":
        raise PublicationConflictError("Publication jobs must be approved before dispatch.")
    if job.status == "cancelled":
        raise PublicationConflictError("Cancelled publication jobs cannot be dispatched.")

    targets = (
        db.query(PublicationTarget)
        .filter(PublicationTarget.publication_job_id == job.id)
        .order_by(PublicationTarget.created_at.asc(), PublicationTarget.id.asc())
        .all()
    )
    run = db.get(PipelineRun, job.pipeline_run_id)
    if run is None:
        raise PublicationConflictError("Publication job references a missing run.")

    dispatched_target_ids: list[str] = []
    for target in targets:
        if target.state == "pending":
            validate_publication_asset_snapshot(db, job)
            refresh_youtube_connection_tokens_if_needed(db, db.get(SocialConnection, target.social_connection_id))
            _set_target_state(target, "queued")
            target.last_error_code = None
            target.last_error_message = None
            target.updated_at = _utcnow()
            db.add(target)
            dispatched_target_ids.append(target.id)
        elif target.state in ACTIVE_TARGET_STATES | SUCCESS_TARGET_STATES | {"outcome_uncertain"}:
            continue
        elif target.state == "retryable_failure" and target.provider_submission_id:
            continue
        else:
            raise PublicationConflictError(f"Publication target cannot be dispatched from state {target.state}.")

    if dispatched_target_ids:
        _recalculate_job_status(db, job)
        _add_publication_event(
            db,
            run,
            "publication.dispatched",
            "Publication target dispatched",
            {
                "publication_job_id": job.id,
                "publication_target_ids": dispatched_target_ids,
                "status": job.status,
            },
        )
        db.commit()
        for target_id in dispatched_target_ids:
            _enqueue_start_target(target_id)
    return get_publication_job(db, job.id)


def retry_publication_target(db: Session, target_id: str) -> dict[str, Any]:
    target, job, run, _package, _connection = _require_target_context(db, target_id)
    if target.state != "retryable_failure":
        raise PublicationConflictError("Only retryable publication targets can be retried.")
    if target.provider_submission_id:
        raise PublicationConflictError("Targets with a persisted provider video ID must be reconciled instead of retried.")

    _set_target_state(target, "queued")
    target.next_poll_at = None
    target.last_error_code = None
    target.last_error_message = None
    target.updated_at = _utcnow()
    db.add(target)
    _recalculate_job_status(db, job)
    _add_publication_event(
        db,
        run,
        "publication.retry_scheduled",
        "Publication target retry scheduled",
        {
            "publication_job_id": job.id,
            "publication_target_id": target.id,
            "attempt_count": target.attempt_count,
        },
    )
    db.commit()
    _enqueue_start_target(target.id)
    return get_publication_job(db, job.id)


def request_reconcile_publication_target(db: Session, target_id: str) -> dict[str, Any]:
    target, job, run, _package, _connection = _require_target_context(db, target_id)
    if not (target.provider_submission_id or target.provider_upload_uri_encrypted):
        raise PublicationConflictError("This publication target has no persisted provider evidence to reconcile.")
    if target.state not in {"uploading", "processing", "retryable_failure", "outcome_uncertain"}:
        raise PublicationConflictError("This publication target is not in a reconcilable state.")

    if target.state in {"retryable_failure", "outcome_uncertain"} and target.provider_submission_id:
        _set_target_state(target, "processing")
        target.next_poll_at = None
        target.updated_at = _utcnow()
        db.add(target)
        _recalculate_job_status(db, job)
        _add_publication_event(
            db,
            run,
            "publication.reconcile_requested",
            "Publication target reconciliation requested",
            {
                "publication_job_id": job.id,
                "publication_target_id": target.id,
                "provider_video_id": target.provider_submission_id,
            },
        )
        db.commit()
    _enqueue_poll_target(target.id)
    return get_publication_job(db, job.id)


def claim_publication_target(db: Session, target_id: str, *, allowed_states: set[str]) -> str | None:
    now = _utcnow()
    claim_token = uuid.uuid4().hex
    stale_before = now - timedelta(seconds=get_settings().youtube_claim_timeout_seconds)
    result = db.execute(
        update(PublicationTarget)
        .where(
            PublicationTarget.id == target_id,
            PublicationTarget.state.in_(sorted(allowed_states)),
            or_(
                PublicationTarget.worker_claimed_at.is_(None),
                PublicationTarget.worker_claimed_at < stale_before,
            ),
        )
        .values(
            worker_claim_token=claim_token,
            worker_claimed_at=now,
            last_attempt_at=now,
            attempt_count=PublicationTarget.attempt_count + 1,
            updated_at=now,
        )
    )
    db.flush()
    if result.rowcount != 1:
        return None
    return claim_token


def release_publication_target_claim(db: Session, target: PublicationTarget, claim_token: str | None) -> None:
    if claim_token and target.worker_claim_token != claim_token:
        return
    target.worker_claim_token = None
    target.worker_claimed_at = None
    target.updated_at = _utcnow()
    db.add(target)


def _record_progress_event(db: Session, run: PipelineRun, job: PublicationJob, target: PublicationTarget) -> None:
    total = target.upload_bytes_total or 0
    sent = target.upload_bytes_sent or 0
    if total <= 0:
        return
    percentage = max(0, min(100, int((sent / total) * 100)))
    if percentage not in {25, 50, 75, 100}:
        return
    _add_publication_event(
        db,
        run,
        "publication.upload_progress",
        "Publication upload progress updated",
        {
            "publication_job_id": job.id,
            "publication_target_id": target.id,
            "progress_percentage": percentage,
            "attempt_count": target.attempt_count,
        },
    )


def _schedule_retry(target: PublicationTarget, provider_error: PublicationProviderError) -> None:
    now = _utcnow()
    target.last_error_code = provider_error.code
    target.last_error_message = provider_error.safe_message
    target.next_poll_at = now + timedelta(seconds=compute_retry_delay(target.attempt_count))
    _set_target_state(target, "retryable_failure", now=now)


def _schedule_permanent_failure(target: PublicationTarget, provider_error: PublicationProviderError) -> None:
    now = _utcnow()
    target.last_error_code = provider_error.code
    target.last_error_message = provider_error.safe_message
    target.next_poll_at = None
    _set_target_state(target, "permanent_failure", now=now)


def _schedule_uncertain_outcome(target: PublicationTarget, provider_error: PublicationProviderError) -> None:
    now = _utcnow()
    target.last_error_code = provider_error.code
    target.last_error_message = provider_error.safe_message
    target.next_poll_at = now + timedelta(seconds=get_settings().youtube_poll_interval_seconds)
    _set_target_state(target, "outcome_uncertain", now=now)


def _build_platform_post_notes(target: PublicationTarget) -> str:
    return (
        "Automated YouTube publication created by Story Engine. "
        f"Publication target {target.id} confirmed as {target.actual_visibility}."
    )


def _complete_publication_target(
    db: Session,
    *,
    target: PublicationTarget,
    job: PublicationJob,
    run: PipelineRun,
    package: ManualPostPackage,
    video_state: YouTubeVideoState,
) -> None:
    now = _utcnow()
    actual_visibility = video_state.privacy_status or target.visibility
    target.actual_visibility = actual_visibility
    target.provider_processing_status = video_state.processing_status
    target.provider_upload_status = video_state.upload_status
    target.processing_last_checked_at = now
    target.outcome_confirmed_at = now
    target.last_error_code = None
    target.last_error_message = None
    target.next_poll_at = None

    if actual_visibility == "private":
        _set_target_state(target, "uploaded_private", now=now)
        target.public_post_url = None
        target.published_at = now
        _add_publication_event(
            db,
            run,
            "publication.uploaded_private",
            "Publication upload completed privately",
            {
                "publication_job_id": job.id,
                "publication_target_id": target.id,
                "provider_video_id": target.provider_submission_id,
                "actual_visibility": target.actual_visibility,
            },
        )
    else:
        watch_url = canonical_watch_url(target.provider_submission_id or "")
        target.public_post_url = watch_url
        platform_post = None
        if target.platform_post_id:
            platform_post = db.get(PlatformPost, target.platform_post_id)
        if platform_post is None:
            platform_post = create_platform_post_for_publication_target(
                db,
                run=run,
                package=package,
                final_asset_id=job.final_asset_id,
                final_asset_source=job.final_asset_source,
                final_asset_selection_revision=job.final_asset_selection_revision,
                final_asset_metadata_json=dict(job.final_asset_metadata_json or {}),
                post_url=watch_url,
                posted_at=now,
                notes=_build_platform_post_notes(target),
            )
            target.platform_post_id = platform_post.id
        target.published_at = target.published_at or now
        _set_target_state(target, "published", now=now)
        _add_publication_event(
            db,
            run,
            "publication.published",
            "Publication target published",
            {
                "publication_job_id": job.id,
                "publication_target_id": target.id,
                "provider_video_id": target.provider_submission_id,
                "actual_visibility": target.actual_visibility,
                "platform_post_id": target.platform_post_id,
            },
        )

    db.add(target)
    _recalculate_job_status(db, job)


def process_youtube_publication_target(db: Session, target_id: str) -> dict[str, Any]:
    claim_token = claim_publication_target(db, target_id, allowed_states={"queued", "validating", "uploading", "processing", "outcome_uncertain"})
    if claim_token is None:
        return get_publication_target(db, target_id)

    try:
        target, job, run, package, connection = _require_target_context(db, target_id)
        if target.provider_submission_id:
            return _poll_youtube_publication_target_claimed(db, target, job, run, package, connection, claim_token)

        validate_publication_asset_snapshot(db, job)
        connection = refresh_youtube_connection_tokens_if_needed(db, connection)
        if target.provider_upload_uri_encrypted:
            _set_target_state(target, "uploading")
        else:
            _set_target_state(target, "validating")
        db.add(target)
        db.flush()

        _add_publication_event(
            db,
            run,
            "publication.upload_started",
            "Publication upload started",
            {
                "publication_job_id": job.id,
                "publication_target_id": target.id,
                "channel_id": connection.external_account_id,
                "attempt_count": target.attempt_count,
            },
        )
        asset = db.get(Asset, job.final_asset_id)
        if asset is None:
            raise PublicationConflictError("Publication job references a missing frozen asset.")

        with open_publication_media(asset) as media_path:
            media_size = media_path.stat().st_size
            media_hash = sha256_for_path(media_path)
            if media_hash != job.final_asset_sha256:
                raise PublicationProviderError(
                    code="frozen_asset_hash_mismatch",
                    safe_message="The frozen final video no longer matches the approved publication hash.",
                    retryable=False,
                    permanent=True,
                )

            session_uri = _decrypt_session_uri(target.provider_upload_uri_encrypted)
            reused_session = bool(session_uri)
            if not session_uri:
                session_uri = initiate_resumable_upload(
                    db,
                    connection,
                    target=target,
                    media_path=media_path,
                    mime_type=asset.mime_type or "video/mp4",
                )
                target.provider_upload_uri_encrypted = _encrypt_session_uri(session_uri)

            _set_target_state(target, "uploading")
            target.upload_bytes_total = media_size
            target.upload_bytes_sent = target.upload_bytes_sent or 0
            target.last_error_code = None
            target.last_error_message = None
            db.add(target)
            db.flush()
            _recalculate_job_status(db, job)
            db.commit()

            progress = upload_media_chunks(
                db,
                connection,
                session_uri=session_uri,
                media_path=media_path,
                mime_type=asset.mime_type or "video/mp4",
                chunk_size=get_settings().youtube_upload_chunk_size_bytes,
                bytes_sent=target.upload_bytes_sent or 0,
                probe_existing_session=reused_session,
            )
            target.provider_upload_uri_encrypted = _encrypt_session_uri(progress.session_uri)
            target.upload_bytes_total = progress.total_bytes
            target.upload_bytes_sent = progress.bytes_sent
            _record_progress_event(db, run, job, target)

            if not progress.video_id:
                raise PublicationProviderError(
                    code="youtube_outcome_uncertain",
                    safe_message="YouTube upload completion could not be confirmed from the resumable session.",
                    retryable=False,
                    outcome_uncertain=True,
                )

            target.provider_submission_id = progress.video_id
            target.provider_media_id = progress.video_id
            target.provider_upload_status = "uploaded"
            target.submitted_at = target.submitted_at or _utcnow()
            target.last_error_code = None
            target.last_error_message = None
            _set_target_state(target, "processing")
            db.add(target)
            _add_publication_event(
                db,
                run,
                "publication.provider_video_id_received",
                "YouTube video identifier received",
                {
                    "publication_job_id": job.id,
                    "publication_target_id": target.id,
                    "provider_video_id": target.provider_submission_id,
                },
            )
            _add_publication_event(
                db,
                run,
                "publication.processing_started",
                "YouTube processing started",
                {
                    "publication_job_id": job.id,
                    "publication_target_id": target.id,
                    "provider_video_id": target.provider_submission_id,
                },
            )
            _recalculate_job_status(db, job)
            release_publication_target_claim(db, target, claim_token)
            db.commit()
            _enqueue_poll_target(target.id, countdown=get_settings().youtube_poll_interval_seconds)
            return get_publication_target(db, target.id)
    except PublicationProviderError as exc:
        target, job, run, _package, _connection = _require_target_context(db, target_id)
        if exc.outcome_uncertain:
            _schedule_uncertain_outcome(target, exc)
            event_type = "publication.outcome_uncertain"
            event_message = "Publication outcome is uncertain"
        elif exc.retryable and target.attempt_count < get_settings().youtube_max_retry_attempts:
            _schedule_retry(target, exc)
            event_type = "publication.retry_scheduled"
            event_message = "Publication retry scheduled"
        else:
            _schedule_permanent_failure(target, exc)
            event_type = "publication.permanent_failure"
            event_message = "Publication failed permanently"
        _recalculate_job_status(db, job)
        release_publication_target_claim(db, target, claim_token)
        db.add(target)
        _add_publication_event(
            db,
            run,
            event_type,
            event_message,
            {
                "publication_job_id": job.id,
                "publication_target_id": target.id,
                "error_code": target.last_error_code,
                "attempt_count": target.attempt_count,
            },
        )
        db.commit()
        if target.state == "retryable_failure" and not target.provider_submission_id:
            next_poll_at = _coerce_stored_datetime(target.next_poll_at)
            delay = max(1, int((next_poll_at - _utcnow()).total_seconds())) if next_poll_at else 1
            _enqueue_start_target(target.id, countdown=delay)
        return get_publication_target(db, target.id)
    except (PublicationConflictError, PublicationMediaError, SocialTokenCryptoError, RuntimeError) as exc:
        provider_error = PublicationProviderError(
            code="youtube_execution_error",
            safe_message=str(exc),
            retryable=False,
            reconnect_required="reconnect" in str(exc).lower(),
            permanent=True,
        )
        target, job, run, _package, _connection = _require_target_context(db, target_id)
        _schedule_permanent_failure(target, provider_error)
        _recalculate_job_status(db, job)
        release_publication_target_claim(db, target, claim_token)
        db.add(target)
        _add_publication_event(
            db,
            run,
            "publication.permanent_failure",
            "Publication failed permanently",
            {
                "publication_job_id": job.id,
                "publication_target_id": target.id,
                "error_code": target.last_error_code,
                "attempt_count": target.attempt_count,
            },
        )
        db.commit()
        return get_publication_target(db, target.id)
    finally:
        if db.in_transaction():
            try:
                target = db.get(PublicationTarget, target_id)
                if target is not None:
                    release_publication_target_claim(db, target, claim_token)
                    db.commit()
            except Exception:
                db.rollback()
    return get_publication_target(db, target_id)


def _poll_youtube_publication_target_claimed(
    db: Session,
    target: PublicationTarget,
    job: PublicationJob,
    run: PipelineRun,
    package: ManualPostPackage,
    connection: SocialConnection,
    claim_token: str,
) -> dict[str, Any]:
    if not target.provider_submission_id:
        provider_error = PublicationProviderError(
            code="youtube_outcome_uncertain",
            safe_message="The YouTube upload session exists, but the provider video ID was never confirmed.",
            retryable=False,
            outcome_uncertain=True,
        )
        _schedule_uncertain_outcome(target, provider_error)
        _recalculate_job_status(db, job)
        release_publication_target_claim(db, target, claim_token)
        db.add(target)
        _add_publication_event(
            db,
            run,
            "publication.outcome_uncertain",
            "Publication outcome is uncertain",
            {
                "publication_job_id": job.id,
                "publication_target_id": target.id,
                "error_code": target.last_error_code,
            },
        )
        db.commit()
        return get_publication_target(db, target.id)

    try:
        connection = refresh_youtube_connection_tokens_if_needed(db, connection)
        state = fetch_youtube_video_state(db, connection, video_id=target.provider_submission_id)
        now = _utcnow()
        target.processing_last_checked_at = now
        target.provider_upload_status = state.upload_status
        target.provider_processing_status = state.processing_status
        target.actual_visibility = state.privacy_status or target.actual_visibility

        if state.processing_status in {"processing", None} or state.upload_status in {"uploaded"}:
            _set_target_state(target, "processing", now=now)
            target.next_poll_at = now + timedelta(seconds=get_settings().youtube_poll_interval_seconds)
            db.add(target)
            _recalculate_job_status(db, job)
            release_publication_target_claim(db, target, claim_token)
            db.commit()
            _enqueue_poll_target(target.id, countdown=get_settings().youtube_poll_interval_seconds)
            return get_publication_target(db, target.id)

        if state.processing_status == "succeeded" or state.upload_status == "processed":
            _complete_publication_target(db, target=target, job=job, run=run, package=package, video_state=state)
            if target.platform_post_id:
                _add_publication_event(
                    db,
                    run,
                    "publication.platform_post_created",
                    "Platform post created from publication target",
                    {
                        "publication_job_id": job.id,
                        "publication_target_id": target.id,
                        "platform_post_id": target.platform_post_id,
                    },
                )
            release_publication_target_claim(db, target, claim_token)
            db.commit()
            return get_publication_target(db, target.id)

        provider_error = PublicationProviderError(
            code="youtube_processing_failed",
            safe_message="YouTube finished the upload but the video failed processing.",
            retryable=False,
            permanent=True,
        )
        if state.failure_reason or state.rejection_reason:
            provider_error = PublicationProviderError(
                code="youtube_processing_failed",
                safe_message="YouTube rejected or failed this video during processing.",
                retryable=False,
                permanent=True,
            )
        _schedule_permanent_failure(target, provider_error)
        _recalculate_job_status(db, job)
        release_publication_target_claim(db, target, claim_token)
        db.add(target)
        _add_publication_event(
            db,
            run,
            "publication.permanent_failure",
            "Publication failed permanently",
            {
                "publication_job_id": job.id,
                "publication_target_id": target.id,
                "provider_video_id": target.provider_submission_id,
                "error_code": target.last_error_code,
            },
        )
        db.commit()
        return get_publication_target(db, target.id)
    except PublicationProviderError as exc:
        if exc.retryable and target.attempt_count < get_settings().youtube_max_poll_attempts:
            _schedule_retry(target, exc)
            event_type = "publication.retry_scheduled"
            event_message = "Publication retry scheduled"
        elif exc.outcome_uncertain:
            _schedule_uncertain_outcome(target, exc)
            event_type = "publication.outcome_uncertain"
            event_message = "Publication outcome is uncertain"
        else:
            _schedule_permanent_failure(target, exc)
            event_type = "publication.permanent_failure"
            event_message = "Publication failed permanently"
        _recalculate_job_status(db, job)
        release_publication_target_claim(db, target, claim_token)
        db.add(target)
        _add_publication_event(
            db,
            run,
            event_type,
            event_message,
            {
                "publication_job_id": job.id,
                "publication_target_id": target.id,
                "provider_video_id": target.provider_submission_id,
                "error_code": target.last_error_code,
            },
        )
        db.commit()
        if target.state in {"retryable_failure", "processing"}:
            next_poll_at = _coerce_stored_datetime(target.next_poll_at)
            delay = max(1, int((next_poll_at - _utcnow()).total_seconds())) if next_poll_at else 1
            _enqueue_poll_target(target.id, countdown=delay)
        return get_publication_target(db, target.id)
    except (PublicationConflictError, SocialTokenCryptoError, RuntimeError) as exc:
        provider_error = PublicationProviderError(
            code="youtube_execution_error",
            safe_message=str(exc),
            retryable=False,
            reconnect_required="reconnect" in str(exc).lower(),
            permanent=True,
        )
        _schedule_permanent_failure(target, provider_error)
        _recalculate_job_status(db, job)
        release_publication_target_claim(db, target, claim_token)
        db.add(target)
        _add_publication_event(
            db,
            run,
            "publication.permanent_failure",
            "Publication failed permanently",
            {
                "publication_job_id": job.id,
                "publication_target_id": target.id,
                "provider_video_id": target.provider_submission_id,
                "error_code": target.last_error_code,
            },
        )
        db.commit()
        return get_publication_target(db, target.id)


def poll_youtube_publication_target(db: Session, target_id: str, *, claim_token: str | None = None) -> dict[str, Any]:
    own_claim = claim_token is None
    if claim_token is None:
        claim_token = claim_publication_target(db, target_id, allowed_states={"processing", "uploading", "outcome_uncertain", "retryable_failure"})
        if claim_token is None:
            return get_publication_target(db, target_id)

    try:
        target, job, run, package, connection = _require_target_context(db, target_id)
        return _poll_youtube_publication_target_claimed(db, target, job, run, package, connection, claim_token)
    finally:
        if own_claim and db.in_transaction():
            try:
                target = db.get(PublicationTarget, target_id)
                if target is not None:
                    release_publication_target_claim(db, target, claim_token)
                    db.commit()
            except Exception:
                db.rollback()


def scan_recoverable_publication_targets(db: Session) -> list[str]:
    stale_before = _utcnow() - timedelta(seconds=get_settings().youtube_claim_timeout_seconds)
    targets = (
        db.query(PublicationTarget)
        .filter(
            PublicationTarget.state.in_(["queued", "uploading", "processing", "retryable_failure", "outcome_uncertain"]),
            or_(
                PublicationTarget.worker_claimed_at.is_(None),
                PublicationTarget.worker_claimed_at < stale_before,
            ),
        )
        .order_by(PublicationTarget.updated_at.asc(), PublicationTarget.id.asc())
        .all()
    )
    recovered: list[str] = []
    for target in targets:
        if target.provider_submission_id:
            _enqueue_poll_target(target.id)
        elif target.state in {"queued", "uploading", "retryable_failure"}:
            _enqueue_start_target(target.id)
        else:
            continue
        recovered.append(target.id)
    return recovered
