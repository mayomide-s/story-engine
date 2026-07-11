from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Asset,
    ManualPostPackage,
    ManualPostingStatus,
    PerformancePlatform,
    PerformanceSnapshot,
    PipelineRun,
    PipelineStatus,
    PlatformPost,
)
from app.schemas.performance import PlatformPostCreatePayload, PlatformPostUpdatePayload, RunPerformanceResponse
from app.services.final_asset_service import get_final_asset_selection_payload, get_selected_final_asset
from app.services.pipeline_service import add_event, serialize_model


class PerformanceConflictError(RuntimeError):
    """Raised when a performance action conflicts with the current run or stored data."""


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _normalize_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware timestamps are required.")
    return value.astimezone(UTC)


def _coerce_stored_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_completed_run(db: Session, run_id: str) -> tuple[PipelineRun, ManualPostPackage]:
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise ValueError("Pipeline run not found")
    if run.status != PipelineStatus.COMPLETED:
        raise PerformanceConflictError("Performance tracking requires a completed pipeline run.")
    if not run.manual_post_package_id:
        raise PerformanceConflictError("Performance tracking requires an existing manual post package.")
    package = db.get(ManualPostPackage, run.manual_post_package_id)
    if package is None:
        raise PerformanceConflictError("Performance tracking requires an existing manual post package.")
    return run, package


def _resolve_current_final_asset_snapshot(db: Session, run: PipelineRun, package: ManualPostPackage) -> tuple[dict[str, Any], Asset]:
    selection = get_final_asset_selection_payload(db, run, package)
    asset = get_selected_final_asset(db, run, package)
    if selection is None or asset is None:
        raise PerformanceConflictError("Performance tracking requires a usable selected final asset.")
    if asset.pipeline_run_id != run.id:
        raise PerformanceConflictError("Selected final asset does not belong to this pipeline run.")
    return selection, asset


def _legacy_status_for_new_post(existing_status: ManualPostingStatus, platform: str) -> ManualPostingStatus:
    if existing_status != ManualPostingStatus.NOT_POSTED:
        return existing_status
    if platform == PerformancePlatform.TIKTOK.value:
        return ManualPostingStatus.POSTED_TIKTOK
    if platform == PerformancePlatform.INSTAGRAM.value:
        return ManualPostingStatus.POSTED_INSTAGRAM
    if platform == PerformancePlatform.YOUTUBE.value:
        return ManualPostingStatus.POSTED_YOUTUBE
    return ManualPostingStatus.POSTED_MULTIPLE


def _sync_manual_post_package_summary(package: ManualPostPackage, platform_post: PlatformPost) -> dict[str, Any]:
    previous_status = package.manual_posting_status.value if hasattr(package.manual_posting_status, "value") else str(package.manual_posting_status)
    package.manual_posting_status = _legacy_status_for_new_post(package.manual_posting_status, platform_post.platform.value)

    changed_fields: dict[str, Any] = {
        "manual_posting_status": package.manual_posting_status.value if hasattr(package.manual_posting_status, "value") else package.manual_posting_status,
    }
    if platform_post.platform == PerformancePlatform.TIKTOK and not package.tiktok_post_url:
        package.tiktok_post_url = platform_post.post_url
        changed_fields["tiktok_post_url"] = package.tiktok_post_url
    elif platform_post.platform == PerformancePlatform.INSTAGRAM and not package.instagram_post_url:
        package.instagram_post_url = platform_post.post_url
        changed_fields["instagram_post_url"] = package.instagram_post_url
    elif platform_post.platform == PerformancePlatform.YOUTUBE and not package.youtube_post_url:
        package.youtube_post_url = platform_post.post_url
        changed_fields["youtube_post_url"] = package.youtube_post_url

    changed_fields["previous_manual_posting_status"] = previous_status
    return changed_fields


def _serialize_snapshot(snapshot: PerformanceSnapshot) -> dict[str, Any]:
    payload = serialize_model(snapshot) or {}
    payload["captured_at"] = _coerce_stored_datetime(snapshot.captured_at)
    payload["created_at"] = _coerce_stored_datetime(snapshot.created_at)
    return payload


def _serialize_platform_post(db: Session, post: PlatformPost) -> dict[str, Any]:
    payload = serialize_model(post) or {}
    payload["final_asset"] = serialize_model(db.get(Asset, post.final_asset_id))
    payload["platform"] = post.platform.value if hasattr(post.platform, "value") else post.platform
    payload["posted_at"] = _coerce_stored_datetime(post.posted_at)
    payload["created_at"] = _coerce_stored_datetime(post.created_at)
    payload["updated_at"] = _coerce_stored_datetime(post.updated_at)
    payload["snapshots"] = [
        _serialize_snapshot(snapshot)
        for snapshot in (
            db.query(PerformanceSnapshot)
            .filter(PerformanceSnapshot.platform_post_id == post.id)
            .order_by(PerformanceSnapshot.captured_at.desc(), PerformanceSnapshot.created_at.desc())
            .all()
        )
    ]
    return payload


def get_run_performance_data(db: Session, run_id: str) -> dict[str, Any]:
    run, package = _require_completed_run(db, run_id)
    current_selection = get_final_asset_selection_payload(db, run, package)
    posts = (
        db.query(PlatformPost)
        .filter(PlatformPost.pipeline_run_id == run.id)
        .order_by(PlatformPost.posted_at.desc(), PlatformPost.created_at.desc())
        .all()
    )
    payload = RunPerformanceResponse(
        run_id=run.id,
        topic=run.topic,
        current_final_asset_selection=current_selection,
        platform_posts=[_serialize_platform_post(db, post) for post in posts],
    )
    return payload.model_dump(mode="json")


def create_platform_post(db: Session, run_id: str, payload: PlatformPostCreatePayload) -> dict[str, Any]:
    run, package = _require_completed_run(db, run_id)
    selection, asset = _resolve_current_final_asset_snapshot(db, run, package)
    posted_at = _normalize_aware_datetime(payload.posted_at)

    duplicate = (
        db.query(PlatformPost)
        .filter(PlatformPost.platform == PerformancePlatform(payload.platform), PlatformPost.post_url == payload.post_url)
        .first()
    )
    if duplicate:
        raise PerformanceConflictError("A platform post with this platform and URL already exists.")

    post = PlatformPost(
        pipeline_run_id=run.id,
        manual_post_package_id=package.id,
        final_asset_id=asset.id,
        final_asset_source=str(selection.get("source") or "source_video"),
        final_narration_render_id=selection.get("narration_render_id"),
        final_asset_selection_revision=selection.get("selection_revision"),
        final_asset_metadata_json={
            "narration_transcript": selection.get("narration_transcript"),
            "caption_cues": selection.get("caption_cues") or [],
            "ai_voice_disclosure": selection.get("ai_voice_disclosure"),
            "voice_is_ai_generated": bool(selection.get("voice_is_ai_generated")),
        },
        platform=PerformancePlatform(payload.platform),
        custom_platform_name=payload.custom_platform_name,
        post_url=payload.post_url,
        posted_at=posted_at,
        notes=payload.notes,
        created_at=_now_utc(),
        updated_at=_now_utc(),
    )
    try:
        db.add(post)
        db.flush()

        summary_changes = _sync_manual_post_package_summary(package, post)
        db.add(package)
        add_event(
            db,
            run.id,
            "performance.post_created",
            "Platform post recorded",
            stage=run.current_stage.value if hasattr(run.current_stage, "value") else str(run.current_stage),
            metadata={
                "platform_post_id": post.id,
                "platform": post.platform.value,
                "final_asset_id": post.final_asset_id,
                "final_asset_source": post.final_asset_source,
                "final_asset_selection_revision": post.final_asset_selection_revision,
                "manual_post_package_updates": summary_changes,
            },
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise PerformanceConflictError("A platform post with this platform and URL already exists.") from exc
    return _serialize_platform_post(db, post)


def _get_platform_post_for_run(db: Session, run_id: str, post_id: str) -> tuple[PipelineRun, PlatformPost]:
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise ValueError("Pipeline run not found")
    post = db.get(PlatformPost, post_id)
    if post is None or post.pipeline_run_id != run.id:
        raise ValueError("Platform post not found")
    return run, post


def update_platform_post(db: Session, run_id: str, post_id: str, payload: PlatformPostUpdatePayload) -> dict[str, Any]:
    run, post = _get_platform_post_for_run(db, run_id, post_id)
    next_platform = payload.platform or (post.platform.value if hasattr(post.platform, "value") else str(post.platform))
    next_custom_platform_name = payload.custom_platform_name if "custom_platform_name" in payload.model_fields_set else post.custom_platform_name
    merged = PlatformPostCreatePayload(
        platform=next_platform,
        custom_platform_name=next_custom_platform_name,
        post_url=payload.post_url or post.post_url,
        posted_at=payload.posted_at or _coerce_stored_datetime(post.posted_at),
        notes=payload.notes if "notes" in payload.model_fields_set else post.notes,
    )

    changed_fields: dict[str, Any] = {}
    if merged.platform != (post.platform.value if hasattr(post.platform, "value") else str(post.platform)):
        post.platform = PerformancePlatform(merged.platform)
        changed_fields["platform"] = merged.platform
    if merged.custom_platform_name != post.custom_platform_name:
        post.custom_platform_name = merged.custom_platform_name
        changed_fields["custom_platform_name"] = merged.custom_platform_name
    if merged.post_url != post.post_url:
        duplicate = (
            db.query(PlatformPost)
            .filter(
                PlatformPost.id != post.id,
                PlatformPost.platform == PerformancePlatform(merged.platform),
                PlatformPost.post_url == merged.post_url,
            )
            .first()
        )
        if duplicate:
            raise PerformanceConflictError("A platform post with this platform and URL already exists.")
        post.post_url = merged.post_url
        changed_fields["post_url"] = merged.post_url
    normalized_posted_at = _normalize_aware_datetime(merged.posted_at)
    if normalized_posted_at != post.posted_at:
        post.posted_at = normalized_posted_at
        changed_fields["posted_at"] = normalized_posted_at.isoformat()
    if merged.notes != post.notes:
        post.notes = merged.notes
        changed_fields["notes_changed"] = True

    post.updated_at = _now_utc()
    db.add(post)
    if changed_fields:
        add_event(
            db,
            run.id,
            "performance.post_updated",
            "Platform post metadata updated",
            stage=run.current_stage.value if hasattr(run.current_stage, "value") else str(run.current_stage),
            metadata={"platform_post_id": post.id, "changed_fields": changed_fields},
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise PerformanceConflictError("A platform post with this platform and URL already exists.") from exc
    return _serialize_platform_post(db, post)


def append_performance_snapshot(db: Session, run_id: str, post_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    run, post = _get_platform_post_for_run(db, run_id, post_id)
    snapshot = PerformanceSnapshot(
        platform_post_id=post.id,
        captured_at=_normalize_aware_datetime(payload["captured_at"]),
        views=payload.get("views"),
        likes=payload.get("likes"),
        comments=payload.get("comments"),
        shares=payload.get("shares"),
        saves=payload.get("saves"),
        average_watch_time_seconds=payload.get("average_watch_time_seconds"),
        completion_rate=payload.get("completion_rate"),
        followers_gained=payload.get("followers_gained"),
        notes=payload.get("notes"),
        created_at=_now_utc(),
    )
    try:
        db.add(snapshot)
        db.flush()
        add_event(
            db,
            run.id,
            "performance.snapshot_added",
            "Performance snapshot recorded",
            stage=run.current_stage.value if hasattr(run.current_stage, "value") else str(run.current_stage),
            metadata={
                "platform_post_id": post.id,
                "performance_snapshot_id": snapshot.id,
                "captured_at": snapshot.captured_at.isoformat(),
                "metrics_present": [
                    name
                    for name in (
                        "views",
                        "likes",
                        "comments",
                        "shares",
                        "saves",
                        "average_watch_time_seconds",
                        "completion_rate",
                        "followers_gained",
                    )
                    if getattr(snapshot, name) is not None
                ],
            },
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise PerformanceConflictError("A performance snapshot already exists for this post at the same captured_at timestamp.") from exc
    return _serialize_snapshot(snapshot)
