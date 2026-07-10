from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import Asset, ManualPostPackage, ManualPostingStatus, NarrationRender, PipelineRun
from app.services.providers import get_storage_provider

SOURCE_VIDEO = "source_video"
NARRATION_RENDER = "narration_render"
FINAL_ASSET_EVENT_TYPE = "final_asset.selected"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _serialize_model(instance) -> dict[str, Any] | None:
    if instance is None:
        return None
    from app.services.pipeline_service import serialize_model

    return serialize_model(instance)


def _record_event(
    db: Session,
    run: PipelineRun,
    message: str,
    metadata: dict[str, Any],
) -> None:
    from app.services.pipeline_service import add_event

    add_event(
        db,
        run.id,
        FINAL_ASSET_EVENT_TYPE,
        message,
        stage=run.current_stage.value if hasattr(run.current_stage, "value") else str(run.current_stage),
        metadata=metadata,
    )


def _latest_asset(db: Session, run_id: str, asset_type: str) -> Asset | None:
    return (
        db.query(Asset)
        .filter(Asset.pipeline_run_id == run_id, Asset.asset_type == asset_type)
        .order_by(Asset.created_at.desc())
        .first()
    )


def get_source_video_asset(db: Session, run: PipelineRun) -> Asset | None:
    return _latest_asset(db, run.id, "video_mp4")


def _asset_exists_for_selection(asset: Asset) -> bool:
    storage = get_storage_provider()
    if getattr(storage, "name", "") != "local":
        return True
    return Path(storage.resolve_path(asset.storage_key)).exists()


def _narration_selection_metadata(render: NarrationRender) -> dict[str, Any]:
    return {
        "narration_transcript": render.full_spoken_text or None,
        "caption_cues": list(render.caption_cues_json or []),
        "ai_voice_disclosure": render.ai_voice_disclosure or None,
        "voice_is_ai_generated": bool(render.voice_is_ai_generated),
        "narration_render_status": render.status.value if hasattr(render.status, "value") else render.status,
        "caption_version": render.caption_version,
        "render_version": render.render_version,
    }


def _source_selection_metadata() -> dict[str, Any]:
    return {
        "narration_transcript": None,
        "caption_cues": [],
        "ai_voice_disclosure": None,
        "voice_is_ai_generated": False,
        "narration_render_status": None,
        "caption_version": None,
        "render_version": None,
    }


def ensure_manual_package_final_asset_defaults(db: Session, run: PipelineRun, package: ManualPostPackage | None) -> ManualPostPackage | None:
    if package is None:
        return None
    source_asset = get_source_video_asset(db, run)
    if source_asset is None:
        return package
    changed = False
    if not package.final_asset_source:
        package.final_asset_source = SOURCE_VIDEO
        changed = True
    if not package.final_asset_id:
        package.final_asset_id = source_asset.id
        changed = True
    if not package.final_asset_selected_at:
        package.final_asset_selected_at = package.updated_at or package.created_at or _utcnow()
        changed = True
    if not package.final_asset_selection_revision or package.final_asset_selection_revision < 1:
        package.final_asset_selection_revision = 1
        changed = True
    if package.final_asset_source == SOURCE_VIDEO and not package.final_asset_metadata_json:
        package.final_asset_metadata_json = _source_selection_metadata()
        changed = True
    if changed:
        db.add(package)
        db.flush()
    return package


def get_final_asset_selection_payload(db: Session, run: PipelineRun, package: ManualPostPackage | None) -> dict[str, Any] | None:
    package = ensure_manual_package_final_asset_defaults(db, run, package)
    original_asset = get_source_video_asset(db, run)
    if package is None or original_asset is None:
        return None

    selected_asset = db.get(Asset, package.final_asset_id) if package.final_asset_id else original_asset
    if selected_asset is None:
        selected_asset = original_asset

    metadata = dict(package.final_asset_metadata_json or {})
    return {
        "source": package.final_asset_source or SOURCE_VIDEO,
        "asset": _serialize_model(selected_asset),
        "narration_render_id": package.final_narration_render_id,
        "selection_revision": package.final_asset_selection_revision or 1,
        "selected_at": package.final_asset_selected_at,
        "narration_transcript": metadata.get("narration_transcript"),
        "caption_cues": list(metadata.get("caption_cues") or []),
        "ai_voice_disclosure": metadata.get("ai_voice_disclosure"),
        "voice_is_ai_generated": bool(metadata.get("voice_is_ai_generated", False)),
        "original_video_asset": _serialize_model(original_asset),
        "can_revert_to_source": (package.final_asset_source or SOURCE_VIDEO) != SOURCE_VIDEO,
    }


def get_selected_final_asset(db: Session, run: PipelineRun, package: ManualPostPackage | None) -> Asset | None:
    selection = get_final_asset_selection_payload(db, run, package)
    if selection is None:
        return None
    asset_id = selection.get("asset", {}).get("id") if isinstance(selection.get("asset"), dict) else None
    return db.get(Asset, asset_id) if asset_id else None


def _validate_selection_change(package: ManualPostPackage, same_selection: bool, confirm_change_after_posting: bool) -> None:
    posted_urls_present = any(
        [
            bool(package.tiktok_post_url),
            bool(package.instagram_post_url),
            bool(package.youtube_post_url),
        ]
    )
    posting_started = (
        package.manual_posting_status != ManualPostingStatus.NOT_POSTED
        or posted_urls_present
    )
    if posting_started and not same_selection and not confirm_change_after_posting:
        raise RuntimeError("confirm_change_after_posting=true is required after manual posting has started.")


def _validate_narration_render_selection(db: Session, run: PipelineRun, render_id: str | None) -> tuple[NarrationRender, Asset]:
    if not render_id:
        raise ValueError("Narration render not found")
    render = db.get(NarrationRender, render_id)
    if render is None:
        raise ValueError("Narration render not found")
    if render.pipeline_run_id != run.id:
        raise RuntimeError("Narration render belongs to another run.")
    render_status = render.status.value if hasattr(render.status, "value") else render.status
    if render_status != "approved":
        raise RuntimeError("Narration render is not approved.")
    if not render.rendered_video_asset_id:
        raise RuntimeError("Narration render is missing its narrated video asset.")
    asset = db.get(Asset, render.rendered_video_asset_id)
    if asset is None:
        raise RuntimeError("Narrated video asset is missing.")
    if asset.pipeline_run_id != run.id:
        raise RuntimeError("Narrated video asset does not belong to this run.")
    if asset.asset_type != "narrated_video_mp4":
        raise RuntimeError("Narrated video asset is invalid.")
    if not _asset_exists_for_selection(asset):
        raise RuntimeError("Narrated video asset file is missing from storage.")
    return render, asset


def select_final_asset(
    db: Session,
    run_id: str,
    source: str,
    narration_render_id: str | None = None,
    confirm_change_after_posting: bool = False,
) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise ValueError("Pipeline run not found")
    if not run.manual_post_package_id:
        raise ValueError("Manual post package missing")
    package = db.get(ManualPostPackage, run.manual_post_package_id)
    if package is None:
        raise ValueError("Manual post package missing")
    package = ensure_manual_package_final_asset_defaults(db, run, package)
    source_asset = get_source_video_asset(db, run)
    if source_asset is None:
        raise RuntimeError("Source video asset missing")

    previous_asset_id = package.final_asset_id
    previous_source = package.final_asset_source or SOURCE_VIDEO
    previous_render_id = package.final_narration_render_id

    if source == SOURCE_VIDEO:
        target_asset = source_asset
        target_render = None
        target_metadata = _source_selection_metadata()
    elif source == NARRATION_RENDER:
        target_render, target_asset = _validate_narration_render_selection(db, run, narration_render_id)
        target_metadata = _narration_selection_metadata(target_render)
    else:
        raise RuntimeError("Final asset source must be source_video or narration_render.")

    same_selection = (
        previous_asset_id == target_asset.id
        and previous_source == source
        and previous_render_id == (target_render.id if target_render else None)
    )
    _validate_selection_change(package, same_selection, confirm_change_after_posting)
    if same_selection:
        return run

    package.final_asset_id = target_asset.id
    package.final_asset_source = source
    package.final_narration_render_id = target_render.id if target_render else None
    package.final_asset_metadata_json = target_metadata
    package.final_asset_selection_revision = (package.final_asset_selection_revision or 1) + 1
    package.final_asset_selected_at = _utcnow()
    db.add(package)
    db.flush()

    posted_urls_present = any([bool(package.tiktok_post_url), bool(package.instagram_post_url), bool(package.youtube_post_url)])
    _record_event(
        db,
        run,
        "Final asset selection updated",
        {
            "previous_asset_id": previous_asset_id,
            "previous_source": previous_source,
            "previous_narration_render_id": previous_render_id,
            "new_asset_id": target_asset.id,
            "new_source": source,
            "new_narration_render_id": target_render.id if target_render else None,
            "selection_revision": package.final_asset_selection_revision,
            "manual_posting_status": package.manual_posting_status.value if hasattr(package.manual_posting_status, "value") else package.manual_posting_status,
            "had_existing_post_urls": posted_urls_present,
        },
    )
    db.commit()
    db.refresh(run)
    return run
