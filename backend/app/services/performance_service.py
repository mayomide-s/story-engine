from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
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
from app.schemas.performance import PerformanceWinnerSelectionPayload
from app.services.final_asset_service import get_final_asset_selection_payload, get_selected_final_asset
from app.services.performance_learning_service import list_performance_learnings
from app.services.pipeline_service import add_event, serialize_model
from app.services.performance_winner_service import build_winner_selection_payload


class PerformanceConflictError(RuntimeError):
    """Raised when a performance action conflicts with the current run or stored data."""


COMPARISON_METRIC_NAMES = [
    "views",
    "engagement_rate",
    "like_rate",
    "comment_rate",
    "share_rate",
    "save_rate",
    "completion_rate",
    "follower_conversion_rate",
    "average_watch_time_ratio",
]
ROUNDING_QUANTUM = Decimal("0.0001")
MIXED_AGE_WARNING_TEXT = "These posts were measured at different ages after posting, so raw comparisons may not reflect equivalent windows."
INVALID_CAPTURE_AGE_WARNING_TEXT = "One or more snapshots were captured before the recorded posting time. Check the timestamps before relying on the comparison."


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


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _round_decimal(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(ROUNDING_QUANTUM, rounding=ROUND_HALF_UP)


def _rounded_ratio(numerator: Any, denominator: Any) -> Decimal | None:
    numerator_decimal = _to_decimal(numerator)
    denominator_decimal = _to_decimal(denominator)
    if numerator_decimal is None or denominator_decimal is None or denominator_decimal <= 0:
        return None
    return _round_decimal(numerator_decimal / denominator_decimal)


def _resolve_attributed_asset_duration_seconds(post_payload: dict[str, Any]) -> Decimal | None:
    final_asset = post_payload.get("final_asset")
    if isinstance(final_asset, dict):
        duration = _to_decimal(final_asset.get("duration_seconds"))
        if duration is not None and duration > 0:
            return duration
    metadata = post_payload.get("final_asset_metadata_json")
    if isinstance(metadata, dict):
        duration = _to_decimal(metadata.get("duration_seconds"))
        if duration is not None and duration > 0:
            return duration
    return None


def _format_age_label(age_seconds: int) -> str:
    if age_seconds < 3600:
        minutes = max(1, age_seconds // 60)
        return f"{minutes}m after posting"
    if age_seconds < 86400:
        hours = age_seconds // 3600
        return f"{hours}h after posting"
    days = age_seconds // 86400
    hours = (age_seconds % 86400) // 3600
    if hours:
        return f"{days}d {hours}h after posting"
    return f"{days}d after posting"


def _age_bucket(age_seconds: int) -> str:
    if age_seconds < 86400:
        return "under_24h"
    if age_seconds < 259200:
        return "1_3d"
    if age_seconds < 604800:
        return "3_7d"
    if age_seconds < 2592000:
        return "7_30d"
    return "30d_plus"


def _build_comparison_metrics(snapshot_payload: dict[str, Any] | None, duration_seconds: Decimal | None) -> dict[str, Decimal | None]:
    if snapshot_payload is None:
        return {name: None for name in COMPARISON_METRIC_NAMES}

    views = _to_decimal(snapshot_payload.get("views"))
    likes = _to_decimal(snapshot_payload.get("likes"))
    comments = _to_decimal(snapshot_payload.get("comments"))
    shares = _to_decimal(snapshot_payload.get("shares"))
    saves = _to_decimal(snapshot_payload.get("saves"))
    followers_gained = _to_decimal(snapshot_payload.get("followers_gained"))
    watch_time = _to_decimal(snapshot_payload.get("average_watch_time_seconds"))
    completion_rate = _round_decimal(_to_decimal(snapshot_payload.get("completion_rate")))

    engagement_rate = None
    if all(component is not None for component in (likes, comments, shares, saves)) and views is not None and views > 0:
        engagement_rate = _round_decimal((likes + comments + shares + saves) / views)

    return {
        "views": _round_decimal(views),
        "engagement_rate": engagement_rate,
        "like_rate": _rounded_ratio(likes, views),
        "comment_rate": _rounded_ratio(comments, views),
        "share_rate": _rounded_ratio(shares, views),
        "save_rate": _rounded_ratio(saves, views),
        "completion_rate": completion_rate,
        "follower_conversion_rate": _rounded_ratio(followers_gained, views),
        "average_watch_time_ratio": _rounded_ratio(watch_time, duration_seconds),
    }


def _build_age_payload(posted_at: datetime | None, snapshot_payload: dict[str, Any] | None) -> dict[str, Any]:
    if posted_at is None or snapshot_payload is None:
        return {
            "latest_snapshot_age_seconds": None,
            "latest_snapshot_age_label": None,
            "latest_snapshot_age_bucket": None,
            "latest_snapshot_age_status": "unavailable",
        }
    captured_at = snapshot_payload.get("captured_at")
    if not isinstance(captured_at, datetime):
        return {
            "latest_snapshot_age_seconds": None,
            "latest_snapshot_age_label": None,
            "latest_snapshot_age_bucket": None,
            "latest_snapshot_age_status": "unavailable",
        }
    age_seconds = int((captured_at - posted_at).total_seconds())
    if age_seconds < 0:
        return {
            "latest_snapshot_age_seconds": None,
            "latest_snapshot_age_label": "Captured before posting",
            "latest_snapshot_age_bucket": None,
            "latest_snapshot_age_status": "captured_before_posting",
        }
    return {
        "latest_snapshot_age_seconds": age_seconds,
        "latest_snapshot_age_label": _format_age_label(age_seconds),
        "latest_snapshot_age_bucket": _age_bucket(age_seconds),
        "latest_snapshot_age_status": "valid",
    }


def _latest_snapshot_payload(snapshot_payloads: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not snapshot_payloads:
        return None
    return snapshot_payloads[0]


def _serialize_platform_post(db: Session, post: PlatformPost) -> dict[str, Any]:
    payload = serialize_model(post) or {}
    payload["final_asset"] = serialize_model(db.get(Asset, post.final_asset_id))
    payload["platform"] = post.platform.value if hasattr(post.platform, "value") else post.platform
    payload["posted_at"] = _coerce_stored_datetime(post.posted_at)
    payload["created_at"] = _coerce_stored_datetime(post.created_at)
    payload["updated_at"] = _coerce_stored_datetime(post.updated_at)
    payload["snapshots"] = snapshot_payloads = [
        _serialize_snapshot(snapshot)
        for snapshot in (
            db.query(PerformanceSnapshot)
            .filter(PerformanceSnapshot.platform_post_id == post.id)
            .order_by(PerformanceSnapshot.captured_at.desc(), PerformanceSnapshot.created_at.desc(), PerformanceSnapshot.id.desc())
            .all()
        )
    ]
    latest_snapshot = _latest_snapshot_payload(snapshot_payloads)
    attributed_duration = _resolve_attributed_asset_duration_seconds(payload)
    payload["attributed_asset_duration_seconds"] = attributed_duration
    payload["latest_snapshot"] = latest_snapshot
    payload.update(_build_age_payload(payload["posted_at"], latest_snapshot))
    payload["comparison_metrics"] = _build_comparison_metrics(latest_snapshot, attributed_duration)
    return payload


def _build_comparison_summary(post_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    valid_age_seconds = [
        int(post["latest_snapshot_age_seconds"])
        for post in post_payloads
        if post.get("latest_snapshot_age_status") == "valid" and post.get("latest_snapshot_age_seconds") is not None
    ]
    valid_age_buckets = {
        str(post["latest_snapshot_age_bucket"])
        for post in post_payloads
        if post.get("latest_snapshot_age_status") == "valid" and post.get("latest_snapshot_age_bucket")
    }
    has_invalid_capture_age = any(post.get("latest_snapshot_age_status") == "captured_before_posting" for post in post_payloads)
    mixed_age_warning = False
    if len(valid_age_seconds) >= 2:
        mixed_age_warning = len(valid_age_buckets) > 1 or (max(valid_age_seconds) - min(valid_age_seconds)) > 86400

    metrics_summary: dict[str, Any] = {}
    for metric_name in COMPARISON_METRIC_NAMES:
        comparable = [
            (post["id"], post.get("comparison_metrics", {}).get(metric_name))
            for post in post_payloads
            if post.get("comparison_metrics", {}).get(metric_name) is not None
        ]
        comparable_post_count = len(comparable)
        if comparable_post_count == 0:
            metrics_summary[metric_name] = {
                "status": "unavailable",
                "comparable_post_count": 0,
                "leader_post_ids": [],
            }
            continue
        if comparable_post_count == 1:
            metrics_summary[metric_name] = {
                "status": "only_available",
                "comparable_post_count": 1,
                "leader_post_ids": [comparable[0][0]],
            }
            continue
        max_value = max(value for _post_id, value in comparable)
        leader_post_ids = [post_id for post_id, value in comparable if value == max_value]
        metrics_summary[metric_name] = {
            "status": "tie" if len(leader_post_ids) > 1 else "leader",
            "comparable_post_count": comparable_post_count,
            "leader_post_ids": leader_post_ids,
        }

    return {
        "latest_snapshot_ordering": ["captured_at_desc", "created_at_desc", "id_desc"],
        "mixed_age_warning": mixed_age_warning,
        "mixed_age_warning_text": MIXED_AGE_WARNING_TEXT if mixed_age_warning else None,
        "has_invalid_capture_age": has_invalid_capture_age,
        "invalid_capture_age_warning_text": INVALID_CAPTURE_AGE_WARNING_TEXT if has_invalid_capture_age else None,
        "metrics": metrics_summary,
    }


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
        winner_selection=build_winner_selection_payload(db, run, package),
        comparison=_build_comparison_summary(serialized_posts := [_serialize_platform_post(db, post) for post in posts]),
        platform_posts=serialized_posts,
        learnings=list_performance_learnings(db, run.id),
    )
    return payload.model_dump(mode="json")


def select_winner_platform_post(db: Session, run_id: str, payload: PerformanceWinnerSelectionPayload) -> dict[str, Any]:
    run, package = _require_completed_run(db, run_id)
    post_id = str(payload.platform_post_id)
    post = db.get(PlatformPost, post_id)
    if post is None or post.pipeline_run_id != run.id:
        raise ValueError("Platform post not found")
    if post.manual_post_package_id != package.id:
        raise ValueError("Platform post not found")
    if package.winner_platform_post_id == post.id:
        return get_run_performance_data(db, run_id)

    previous_post_id = package.winner_platform_post_id
    now = _now_utc()
    package.winner_platform_post_id = post.id
    package.winner_selected_at = now
    package.winner_selection_revision = int(package.winner_selection_revision or 0) + 1
    db.add(package)
    db.flush()

    add_event(
        db,
        run.id,
        "performance.winner_selected" if previous_post_id is None else "performance.winner_changed",
        "Manual performance winner selected" if previous_post_id is None else "Manual performance winner changed",
        stage=run.current_stage.value if hasattr(run.current_stage, "value") else str(run.current_stage),
        metadata={
            "run_id": run.id,
            "previous_post_id": previous_post_id,
            "new_post_id": post.id,
            "winner_selection_revision": package.winner_selection_revision,
            "selected_at": now.isoformat(),
        },
    )
    db.commit()
    return get_run_performance_data(db, run_id)


def clear_winner_platform_post(db: Session, run_id: str) -> dict[str, Any]:
    run, package = _require_completed_run(db, run_id)
    if not package.winner_platform_post_id:
        return get_run_performance_data(db, run_id)

    previous_post_id = package.winner_platform_post_id
    now = _now_utc()
    package.winner_platform_post_id = None
    package.winner_selected_at = None
    package.winner_selection_revision = int(package.winner_selection_revision or 0) + 1
    db.add(package)
    db.flush()

    add_event(
        db,
        run.id,
        "performance.winner_cleared",
        "Manual performance winner cleared",
        stage=run.current_stage.value if hasattr(run.current_stage, "value") else str(run.current_stage),
        metadata={
            "run_id": run.id,
            "previous_post_id": previous_post_id,
            "new_post_id": None,
            "winner_selection_revision": package.winner_selection_revision,
            "cleared_at": now.isoformat(),
        },
    )
    db.commit()
    return get_run_performance_data(db, run_id)


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


def create_platform_post_for_publication_target(
    db: Session,
    *,
    run: PipelineRun,
    package: ManualPostPackage,
    final_asset_id: str,
    final_asset_source: str,
    final_asset_selection_revision: int,
    final_asset_metadata_json: dict[str, Any] | None,
    post_url: str,
    posted_at: datetime,
    notes: str | None,
) -> PlatformPost:
    existing = (
        db.query(PlatformPost)
        .filter(
            PlatformPost.pipeline_run_id == run.id,
            PlatformPost.platform == PerformancePlatform.YOUTUBE,
            PlatformPost.post_url == post_url,
        )
        .first()
    )
    if existing is not None:
        return existing

    asset = db.get(Asset, final_asset_id)
    if asset is None or asset.pipeline_run_id != run.id:
        raise PerformanceConflictError("Frozen publication asset is missing or belongs to another run.")

    post = PlatformPost(
        pipeline_run_id=run.id,
        manual_post_package_id=package.id,
        final_asset_id=final_asset_id,
        final_asset_source=final_asset_source,
        final_narration_render_id=None,
        final_asset_selection_revision=final_asset_selection_revision,
        final_asset_metadata_json=final_asset_metadata_json or {},
        platform=PerformancePlatform.YOUTUBE,
        custom_platform_name=None,
        post_url=post_url,
        posted_at=_normalize_aware_datetime(posted_at),
        notes=notes,
        created_at=_now_utc(),
        updated_at=_now_utc(),
    )
    try:
        with db.begin_nested():
            db.add(post)
            db.flush()
    except IntegrityError as exc:
        duplicate = (
            db.query(PlatformPost)
            .filter(
                PlatformPost.platform == PerformancePlatform.YOUTUBE,
                PlatformPost.post_url == post_url,
            )
            .first()
        )
        if duplicate is not None:
            return duplicate
        raise PerformanceConflictError("A platform post with this platform and URL already exists.") from exc

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
    db.flush()
    return post


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
