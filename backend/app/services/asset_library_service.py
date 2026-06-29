from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Asset, ContentIdea, IdeaQueueItem, ManualPostPackage, PipelineRun, QualityCheck, Video
from app.services.pipeline_service import serialize_model


def _find_video_asset(db: Session, run_id: str, asset_type: str) -> Asset | None:
    return (
        db.query(Asset)
        .filter(Asset.pipeline_run_id == run_id, Asset.asset_type == asset_type)
        .order_by(Asset.created_at.desc())
        .first()
    )


def _find_latest_quality_check(db: Session, run_id: str, video_id: str | None) -> QualityCheck | None:
    if not video_id:
        return None
    return (
        db.query(QualityCheck)
        .filter(QualityCheck.pipeline_run_id == run_id, QualityCheck.video_id == video_id)
        .order_by(QualityCheck.created_at.desc())
        .first()
    )


def _find_linked_idea_queue_item(db: Session, run_id: str) -> IdeaQueueItem | None:
    return (
        db.query(IdeaQueueItem)
        .filter(IdeaQueueItem.pipeline_run_id == run_id)
        .order_by(IdeaQueueItem.updated_at.desc())
        .first()
    )


def _build_asset_summary(db: Session, run: PipelineRun) -> dict[str, Any] | None:
    video = db.get(Video, run.video_id) if run.video_id else None
    if video is None:
        return None
    video_asset = _find_video_asset(db, run.id, "video_mp4")
    if video_asset is None:
        return None
    thumbnail_asset = _find_video_asset(db, run.id, "thumbnail")
    quality_check = _find_latest_quality_check(db, run.id, video.id)
    idea = db.get(ContentIdea, run.idea_id) if run.idea_id else None
    manual_package = db.get(ManualPostPackage, run.manual_post_package_id) if run.manual_post_package_id else None
    queue_item = _find_linked_idea_queue_item(db, run.id)
    return {
        "run_id": run.id,
        "topic": run.topic,
        "style_preset": run.style_preset,
        "provider": video.provider,
        "run_status": run.status.value if hasattr(run.status, "value") else run.status,
        "video_status": video.status.value if hasattr(video.status, "value") else video.status,
        "quality_score": video.quality_score,
        "created_at": run.created_at,
        "thumbnail_url": thumbnail_asset.public_url if thumbnail_asset else None,
        "video_url": video_asset.public_url,
        "target_platform": queue_item.target_platform if queue_item else None,
        "caption": manual_package.caption if manual_package else None,
        "prompt_text": video.prompt_text,
    }


def list_asset_library_items(
    db: Session,
    provider: str | None = None,
    status: str | None = None,
    style_preset: str | None = None,
    platform: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    runs = (
        db.query(PipelineRun)
        .filter(PipelineRun.video_id.is_not(None))
        .order_by(PipelineRun.created_at.desc())
        .all()
    )
    items = [item for run in runs if (item := _build_asset_summary(db, run)) is not None]

    if provider:
        items = [item for item in items if item["provider"] == provider]
    if status:
        normalized = status.lower()
        items = [
            item
            for item in items
            if str(item["video_status"]).lower() == normalized or str(item["run_status"]).lower() == normalized
        ]
    if style_preset:
        items = [item for item in items if item["style_preset"] == style_preset]
    if platform:
        items = [item for item in items if item["target_platform"] == platform]
    if search:
        query = search.lower()
        items = [
            item
            for item in items
            if query in (item["topic"] or "").lower()
            or query in (item["caption"] or "").lower()
            or query in (item["prompt_text"] or "").lower()
        ]
    return items


def get_asset_library_detail(db: Session, run_id: str) -> dict[str, Any]:
    run = db.get(PipelineRun, run_id)
    if not run:
        raise ValueError("Asset library item not found")
    video = db.get(Video, run.video_id) if run.video_id else None
    if video is None:
        raise ValueError("Asset library item not found")

    video_asset = _find_video_asset(db, run.id, "video_mp4")
    if video_asset is None:
        raise ValueError("Asset library item not found")
    thumbnail_asset = _find_video_asset(db, run.id, "thumbnail")
    idea = db.get(ContentIdea, run.idea_id) if run.idea_id else None
    quality_check = _find_latest_quality_check(db, run.id, video.id)
    manual_package = db.get(ManualPostPackage, run.manual_post_package_id) if run.manual_post_package_id else None
    queue_item = _find_linked_idea_queue_item(db, run.id)

    return {
        "pipeline_run": serialize_model(run),
        "video": serialize_model(video),
        "video_asset": serialize_model(video_asset),
        "thumbnail_asset": serialize_model(thumbnail_asset) if thumbnail_asset else None,
        "idea": serialize_model(idea) if idea else None,
        "quality_check": serialize_model(quality_check) if quality_check else None,
        "manual_post_package": serialize_model(manual_package) if manual_package else None,
        "idea_queue_item": serialize_model(queue_item) if queue_item else None,
    }
