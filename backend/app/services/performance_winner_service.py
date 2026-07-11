from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import ManualPostPackage, PipelineRun, PlatformPost


def empty_winner_selection_payload(selection_revision: int = 0) -> dict[str, Any]:
    return {
        "platform_post_id": None,
        "selected_at": None,
        "selection_revision": selection_revision,
        "post": None,
    }


def _serialize_winner_post(post: PlatformPost) -> dict[str, Any]:
    platform = post.platform.value if hasattr(post.platform, "value") else str(post.platform)
    return {
        "id": post.id,
        "platform": platform,
        "custom_platform_name": post.custom_platform_name,
        "post_url": post.post_url,
        "posted_at": post.posted_at,
        "final_asset_id": post.final_asset_id,
        "final_asset_source": post.final_asset_source,
    }


def build_winner_selection_payload(
    db: Session,
    run: PipelineRun,
    package: ManualPostPackage | None,
) -> dict[str, Any]:
    if package is None:
        return empty_winner_selection_payload()

    selection_revision = int(package.winner_selection_revision or 0)
    winner_post_id = package.winner_platform_post_id
    if not winner_post_id:
        return empty_winner_selection_payload(selection_revision)

    post = db.get(PlatformPost, winner_post_id)
    if (
        post is None
        or post.pipeline_run_id != run.id
        or post.manual_post_package_id != package.id
    ):
        return empty_winner_selection_payload(selection_revision)

    return {
        "platform_post_id": post.id,
        "selected_at": package.winner_selected_at,
        "selection_revision": selection_revision,
        "post": _serialize_winner_post(post),
    }
