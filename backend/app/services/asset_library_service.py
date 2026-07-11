from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Asset, ContentIdea, IdeaQueueItem, ManualPostPackage, ManualPostingStatus, PipelineRun, QualityCheck, Video
from app.services.final_asset_service import get_final_asset_selection_payload, get_selected_final_asset
from app.services.performance_learning_service import build_performance_learnings_summary
from app.services.performance_winner_service import build_winner_selection_payload
from app.services.pipeline_service import serialize_model

PLATFORM_CHECKLISTS = {
    "tiktok": [
        "Upload the MP4 in 9:16 format.",
        "Paste the caption and hashtags, then confirm the hook lands in the first line.",
        "Choose the cover thumbnail and publish manually.",
    ],
    "instagram_reels": [
        "Upload the MP4 as a Reel in 9:16 format.",
        "Paste the caption and hashtags, then confirm the thumbnail crop looks clean.",
        "Review profile grid placement before publishing.",
    ],
    "youtube_shorts": [
        "Upload the MP4 as a Short.",
        "Set title, description, and hashtags before publishing.",
        "Confirm the thumbnail and end tag are visible in preview.",
    ],
}

RUNWAY_PLATFORM_CHECKLISTS = {
    "tiktok": [
        "Upload the MP4 in 9:16 format.",
        "Paste the caption and hashtags, then confirm the hook lands in the first line.",
        "Choose the cover thumbnail and confirm the opening frame looks clean.",
    ],
    "instagram_reels": [
        "Upload the MP4 as a Reel in 9:16 format.",
        "Paste the caption and hashtags, then confirm the thumbnail crop looks clean.",
        "Review the opening frame and profile grid placement before publishing.",
    ],
    "youtube_shorts": [
        "Upload the MP4 as a Short.",
        "Set title, description, and hashtags before publishing.",
        "Confirm the thumbnail and opening frame look clean in preview.",
    ],
}


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


def _derive_manual_posting_status(pkg: ManualPostPackage) -> ManualPostingStatus:
    present = {
        "tiktok": bool(pkg.tiktok_post_url),
        "instagram": bool(pkg.instagram_post_url),
        "youtube": bool(pkg.youtube_post_url),
    }
    count = sum(present.values())
    if count == 0:
        return ManualPostingStatus.NOT_POSTED
    if count > 1:
        return ManualPostingStatus.POSTED_MULTIPLE
    if present["tiktok"]:
        return ManualPostingStatus.POSTED_TIKTOK
    if present["instagram"]:
        return ManualPostingStatus.POSTED_INSTAGRAM
    return ManualPostingStatus.POSTED_YOUTUBE


def _build_platform_section(
    label: str,
    variant: dict[str, Any] | None,
    shared_caption: str,
    shared_hashtags: list[str],
    post_url: str | None,
    provider_name: str,
) -> dict[str, Any]:
    variant = variant or {}
    hashtags = variant.get("hashtags") if isinstance(variant.get("hashtags"), list) else shared_hashtags
    caption = str(variant.get("caption") or shared_caption)
    title = str(variant.get("title") or "")
    description = str(variant.get("description") or caption)
    if label == "youtube_shorts":
        full_post_text = f"Title: {title}\n\nDescription:\n{description}\n\nHashtags:\n{' '.join(hashtags)}"
    else:
        full_post_text = f"{caption}\n\n{' '.join(hashtags)}"
    return {
        "recommended_caption": caption,
        "hashtags": hashtags,
        "title": title or None,
        "description": description if label == "youtube_shorts" else None,
        "checklist": (RUNWAY_PLATFORM_CHECKLISTS if provider_name == "runway" else PLATFORM_CHECKLISTS)[label],
        "full_post_text": full_post_text,
        "manual_post_url": post_url,
    }


def _normalize_quality_checklist(checks: dict[str, Any] | None, provider_name: str) -> dict[str, Any]:
    raw_checks = dict(checks or {})
    if provider_name != "runway":
        return raw_checks
    normalized = {key: value for key, value in raw_checks.items() if key != "end_tag_present"}
    if "branding_handled_separately" not in normalized:
        normalized["branding_handled_separately"] = bool(
            normalized.get("video_exists")
            and normalized.get("aspect_ratio_9_16")
            and normalized.get("duration_in_range")
            and normalized.get("provider_generated_video")
        )
    return normalized


def _build_export_pack(
    run: PipelineRun,
    video: Video,
    video_asset: Asset,
    final_video_asset: Asset,
    thumbnail_asset: Asset | None,
    idea: ContentIdea | None,
    quality_check: QualityCheck | None,
    manual_package: ManualPostPackage | None,
    queue_item: IdeaQueueItem | None,
    final_asset_selection: dict[str, Any] | None,
) -> dict[str, Any]:
    hashtags = manual_package.hashtags_json if manual_package else []
    platform_variants = manual_package.platform_variants_json if manual_package else {}
    alternative_captions = platform_variants.get("alternative_captions", []) if isinstance(platform_variants, dict) else []
    alternative_hooks = platform_variants.get("alternative_hooks", []) if isinstance(platform_variants, dict) else []
    manual_posting_status = (
        manual_package.manual_posting_status.value
        if manual_package and hasattr(manual_package.manual_posting_status, "value")
        else (manual_package.manual_posting_status if manual_package else ManualPostingStatus.NOT_POSTED.value)
    )
    tiktok_section = _build_platform_section(
        "tiktok",
        platform_variants.get("tiktok") if isinstance(platform_variants, dict) else None,
        manual_package.caption if manual_package else "",
        hashtags,
        manual_package.tiktok_post_url if manual_package else None,
        video.provider,
    )
    instagram_section = _build_platform_section(
        "instagram_reels",
        platform_variants.get("instagram") if isinstance(platform_variants, dict) else None,
        manual_package.caption if manual_package else "",
        hashtags,
        manual_package.instagram_post_url if manual_package else None,
        video.provider,
    )
    youtube_section = _build_platform_section(
        "youtube_shorts",
        platform_variants.get("youtube") if isinstance(platform_variants, dict) else None,
        manual_package.caption if manual_package else "",
        hashtags,
        manual_package.youtube_post_url if manual_package else None,
        video.provider,
    )
    return {
        "run_id": run.id,
        "topic": run.topic,
        "style_preset": run.style_preset,
        "provider": video.provider,
        "created_at": run.created_at,
        "video_public_url": final_video_asset.public_url,
        "original_video_public_url": video_asset.public_url,
        "thumbnail_public_url": thumbnail_asset.public_url if thumbnail_asset else None,
        "caption": manual_package.caption if manual_package else "",
        "hashtags": hashtags,
        "final_prompt_used": video.prompt_text,
        "quality_score": video.quality_score,
        "quality_checklist": _normalize_quality_checklist(quality_check.checks_json if quality_check else {}, video.provider),
        "quality_critique": quality_check.llm_critique if quality_check else None,
        "idea_title": idea.title if idea else None,
        "idea_hook": idea.hook if idea else None,
        "alternative_captions": alternative_captions if isinstance(alternative_captions, list) else [],
        "alternative_hooks": alternative_hooks if isinstance(alternative_hooks, list) else [],
        "manual_posting_status": manual_posting_status,
        "manual_post_urls": {
            "tiktok": manual_package.tiktok_post_url if manual_package else None,
            "instagram": manual_package.instagram_post_url if manual_package else None,
            "youtube": manual_package.youtube_post_url if manual_package else None,
        },
        "final_asset_id": final_video_asset.id,
        "final_asset_source": final_asset_selection.get("source") if final_asset_selection else "source_video",
        "final_narration_render_id": final_asset_selection.get("narration_render_id") if final_asset_selection else None,
        "final_asset_selection_revision": final_asset_selection.get("selection_revision") if final_asset_selection else 1,
        "final_asset_selected_at": final_asset_selection.get("selected_at") if final_asset_selection else None,
        "narration_transcript": final_asset_selection.get("narration_transcript") if final_asset_selection else None,
        "caption_cues": final_asset_selection.get("caption_cues") if final_asset_selection else [],
        "ai_voice_disclosure": final_asset_selection.get("ai_voice_disclosure") if final_asset_selection else None,
        "voice_is_ai_generated": bool(final_asset_selection.get("voice_is_ai_generated")) if final_asset_selection else False,
        "target_platform": queue_item.target_platform if queue_item else None,
        "linked_pipeline_run_id": run.id,
        "linked_idea_queue_item_id": queue_item.id if queue_item else None,
        "platform_sections": {
            "tiktok": tiktok_section,
            "instagram_reels": instagram_section,
            "youtube_shorts": youtube_section,
        },
    }


def _build_asset_summary(db: Session, run: PipelineRun) -> dict[str, Any] | None:
    video = db.get(Video, run.video_id) if run.video_id else None
    if video is None:
        return None
    video_asset = _find_video_asset(db, run.id, "video_mp4")
    if video_asset is None:
        return None
    manual_package = db.get(ManualPostPackage, run.manual_post_package_id) if run.manual_post_package_id else None
    final_asset_selection = get_final_asset_selection_payload(db, run, manual_package)
    final_video_asset = get_selected_final_asset(db, run, manual_package)
    if final_video_asset is None:
        final_video_asset = video_asset
    thumbnail_asset = _find_video_asset(db, run.id, "thumbnail")
    quality_check = _find_latest_quality_check(db, run.id, video.id)
    idea = db.get(ContentIdea, run.idea_id) if run.idea_id else None
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
        "video_url": final_video_asset.public_url,
        "original_video_url": video_asset.public_url,
        "final_asset_source": final_asset_selection.get("source") if final_asset_selection else "source_video",
        "final_narration_render_id": final_asset_selection.get("narration_render_id") if final_asset_selection else None,
        "target_platform": queue_item.target_platform if queue_item else None,
        "caption": manual_package.caption if manual_package else None,
        "prompt_text": video.prompt_text,
        "manual_posting_status": (
            manual_package.manual_posting_status.value
            if manual_package and hasattr(manual_package.manual_posting_status, "value")
            else (manual_package.manual_posting_status if manual_package else ManualPostingStatus.NOT_POSTED.value)
        ),
    }


def list_asset_library_items(
    db: Session,
    provider: str | None = None,
    status: str | None = None,
    style_preset: str | None = None,
    platform: str | None = None,
    manual_posting_status: str | None = None,
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
    if manual_posting_status:
        items = [item for item in items if str(item["manual_posting_status"]).lower() == manual_posting_status.lower()]
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
    manual_package = db.get(ManualPostPackage, run.manual_post_package_id) if run.manual_post_package_id else None
    final_asset_selection = get_final_asset_selection_payload(db, run, manual_package)
    final_video_asset = get_selected_final_asset(db, run, manual_package)
    if final_video_asset is None:
        final_video_asset = video_asset
    thumbnail_asset = _find_video_asset(db, run.id, "thumbnail")
    idea = db.get(ContentIdea, run.idea_id) if run.idea_id else None
    quality_check = _find_latest_quality_check(db, run.id, video.id)
    queue_item = _find_linked_idea_queue_item(db, run.id)

    return {
        "pipeline_run": serialize_model(run),
        "video": serialize_model(video),
        "video_asset": serialize_model(video_asset),
        "final_video_asset": serialize_model(final_video_asset),
        "final_asset_selection": final_asset_selection,
        "winner_selection": build_winner_selection_payload(db, run, manual_package),
        "performance_learnings_summary": build_performance_learnings_summary(db, run.id),
        "thumbnail_asset": serialize_model(thumbnail_asset) if thumbnail_asset else None,
        "idea": serialize_model(idea) if idea else None,
        "quality_check": serialize_model(quality_check) if quality_check else None,
        "manual_post_package": serialize_model(manual_package) if manual_package else None,
        "idea_queue_item": serialize_model(queue_item) if queue_item else None,
    }


def get_asset_export_pack(db: Session, run_id: str) -> dict[str, Any]:
    run = db.get(PipelineRun, run_id)
    if not run:
        raise ValueError("Asset library item not found")
    video = db.get(Video, run.video_id) if run.video_id else None
    if video is None:
        raise ValueError("Asset library item not found")
    video_asset = _find_video_asset(db, run.id, "video_mp4")
    if video_asset is None:
        raise ValueError("Asset library item not found")
    manual_package = db.get(ManualPostPackage, run.manual_post_package_id) if run.manual_post_package_id else None
    final_asset_selection = get_final_asset_selection_payload(db, run, manual_package)
    final_video_asset = get_selected_final_asset(db, run, manual_package)
    if final_video_asset is None:
        final_video_asset = video_asset
    thumbnail_asset = _find_video_asset(db, run.id, "thumbnail")
    idea = db.get(ContentIdea, run.idea_id) if run.idea_id else None
    quality_check = _find_latest_quality_check(db, run.id, video.id)
    queue_item = _find_linked_idea_queue_item(db, run.id)
    return _build_export_pack(
        run,
        video,
        video_asset,
        final_video_asset,
        thumbnail_asset,
        idea,
        quality_check,
        manual_package,
        queue_item,
        final_asset_selection,
    )


def update_asset_manual_posting(db: Session, run_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    run = db.get(PipelineRun, run_id)
    if not run or not run.manual_post_package_id:
        raise ValueError("Asset library item not found")
    pkg = db.get(ManualPostPackage, run.manual_post_package_id)
    if pkg is None:
        raise ValueError("Asset library item not found")

    for field in ("tiktok_post_url", "instagram_post_url", "youtube_post_url"):
        if field in updates:
            setattr(pkg, field, updates[field])

    if "manual_posting_status" in updates and updates["manual_posting_status"] is not None:
        pkg.manual_posting_status = updates["manual_posting_status"]
    else:
        pkg.manual_posting_status = _derive_manual_posting_status(pkg)

    db.add(pkg)
    from app.services.pipeline_service import add_event

    add_event(
        db,
        run.id,
        "manual_posting.updated",
        "Manual posting status updated",
        stage=run.current_stage.value if hasattr(run.current_stage, "value") else str(run.current_stage),
        metadata={
            "manual_posting_status": pkg.manual_posting_status.value if hasattr(pkg.manual_posting_status, "value") else pkg.manual_posting_status,
            "tiktok_post_url": pkg.tiktok_post_url,
            "instagram_post_url": pkg.instagram_post_url,
            "youtube_post_url": pkg.youtube_post_url,
        },
    )
    db.commit()
    return get_asset_export_pack(db, run_id)
