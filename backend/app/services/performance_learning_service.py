from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import ManualPostPackage, PipelineRun, PipelineStatus, PlatformPost
from app.models.entities import PerformanceLearning
from app.schemas.performance import PerformanceLearningCreatePayload, PerformanceLearningPatchPayload


class PerformanceLearningConflictError(RuntimeError):
    """Raised when a learning mutation conflicts with run or learning state."""


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _coerce_stored_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _serialize_associated_post(post: PlatformPost | None) -> dict[str, Any] | None:
    if post is None:
        return None
    platform = post.platform.value if hasattr(post.platform, "value") else str(post.platform)
    return {
        "id": post.id,
        "platform": platform,
        "custom_platform_name": post.custom_platform_name,
        "post_url": post.post_url,
        "posted_at": _coerce_stored_datetime(post.posted_at),
    }


def _serialize_learning(learning: PerformanceLearning, associated_post: PlatformPost | None = None) -> dict[str, Any]:
    return {
        "id": learning.id,
        "pipeline_run_id": learning.pipeline_run_id,
        "learning_type": learning.learning_type,
        "observation": learning.observation,
        "evidence": learning.evidence,
        "next_action": learning.next_action,
        "platform_post_id": learning.platform_post_id,
        "associated_post": _serialize_associated_post(associated_post),
        "is_archived": learning.is_archived,
        "archived_at": _coerce_stored_datetime(learning.archived_at),
        "created_at": _coerce_stored_datetime(learning.created_at),
        "updated_at": _coerce_stored_datetime(learning.updated_at),
    }


def _get_run_and_package(db: Session, run_id: str) -> tuple[PipelineRun, ManualPostPackage]:
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise ValueError("Pipeline run not found")
    if run.status != PipelineStatus.COMPLETED:
        raise PerformanceLearningConflictError("Performance learnings require a completed pipeline run.")
    if not run.manual_post_package_id:
        raise PerformanceLearningConflictError("Performance learnings require an existing manual post package.")
    package = db.get(ManualPostPackage, run.manual_post_package_id)
    if package is None:
        raise PerformanceLearningConflictError("Performance learnings require an existing manual post package.")
    return run, package


def _validate_platform_post(
    db: Session,
    run: PipelineRun,
    package: ManualPostPackage,
    platform_post_id: str | None,
) -> PlatformPost | None:
    if platform_post_id is None:
        return None
    post = db.get(PlatformPost, platform_post_id)
    if (
        post is None
        or post.pipeline_run_id != run.id
        or post.manual_post_package_id != package.id
    ):
        raise ValueError("Platform post not found")
    return post


def _get_learning_for_run(db: Session, run_id: str, learning_id: str) -> PerformanceLearning:
    learning = db.get(PerformanceLearning, learning_id)
    if learning is None or learning.pipeline_run_id != run_id:
        raise ValueError("Performance learning not found")
    return learning


def list_performance_learnings(db: Session, run_id: str) -> list[dict[str, Any]]:
    learnings = (
        db.query(PerformanceLearning)
        .filter(PerformanceLearning.pipeline_run_id == run_id)
        .order_by(
            PerformanceLearning.is_archived.asc(),
            PerformanceLearning.updated_at.desc(),
            PerformanceLearning.created_at.desc(),
            PerformanceLearning.id.desc(),
        )
        .all()
    )
    if not learnings:
        return []

    post_ids = {learning.platform_post_id for learning in learnings if learning.platform_post_id}
    posts = {
        post.id: post
        for post in db.query(PlatformPost).filter(PlatformPost.id.in_(post_ids)).all()
    } if post_ids else {}

    return [_serialize_learning(learning, posts.get(learning.platform_post_id)) for learning in learnings]


def build_performance_learnings_summary(db: Session, run_id: str, limit: int = 3) -> dict[str, Any]:
    active_learnings = (
        db.query(PerformanceLearning)
        .filter(
            PerformanceLearning.pipeline_run_id == run_id,
            PerformanceLearning.is_archived.is_(False),
        )
        .order_by(
            PerformanceLearning.updated_at.desc(),
            PerformanceLearning.created_at.desc(),
            PerformanceLearning.id.desc(),
        )
        .all()
    )
    if not active_learnings:
        return {"active_count": 0, "items": []}

    post_ids = {learning.platform_post_id for learning in active_learnings[:limit] if learning.platform_post_id}
    posts = {
        post.id: post
        for post in db.query(PlatformPost).filter(PlatformPost.id.in_(post_ids)).all()
    } if post_ids else {}

    return {
        "active_count": len(active_learnings),
        "items": [
            _serialize_learning(learning, posts.get(learning.platform_post_id))
            for learning in active_learnings[:limit]
        ],
    }


def create_performance_learning(db: Session, run_id: str, payload: PerformanceLearningCreatePayload) -> None:
    from app.services.pipeline_service import add_event

    run, package = _get_run_and_package(db, run_id)
    associated_post = _validate_platform_post(
        db,
        run,
        package,
        str(payload.platform_post_id) if payload.platform_post_id is not None else None,
    )
    now = _now_utc()
    learning = PerformanceLearning(
        pipeline_run_id=run.id,
        platform_post_id=associated_post.id if associated_post else None,
        learning_type=payload.learning_type,
        observation=payload.observation,
        evidence=payload.evidence,
        next_action=payload.next_action,
        is_archived=False,
        archived_at=None,
        created_at=now,
        updated_at=now,
    )
    try:
        db.add(learning)
        db.flush()
        add_event(
            db,
            run.id,
            "performance.learning_created",
            "Performance learning created.",
            stage=run.current_stage.value if hasattr(run.current_stage, "value") else str(run.current_stage),
            metadata={
                "learning_id": learning.id,
                "learning_type": learning.learning_type,
                "platform_post_id": learning.platform_post_id,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


def update_performance_learning(
    db: Session,
    run_id: str,
    learning_id: str,
    payload: PerformanceLearningPatchPayload,
) -> None:
    from app.services.pipeline_service import add_event

    run, package = _get_run_and_package(db, run_id)
    learning = _get_learning_for_run(db, run.id, learning_id)
    if learning.is_archived:
        raise PerformanceLearningConflictError("Archived performance learnings are read-only.")

    changed_fields: list[str] = []

    if "platform_post_id" in payload.model_fields_set:
        requested_post_id = str(payload.platform_post_id) if payload.platform_post_id is not None else None
        post = _validate_platform_post(db, run, package, requested_post_id)
        if requested_post_id != learning.platform_post_id:
            learning.platform_post_id = requested_post_id
            changed_fields.append("platform_post_id")

    if "learning_type" in payload.model_fields_set and payload.learning_type != learning.learning_type:
        learning.learning_type = payload.learning_type
        changed_fields.append("learning_type")

    if "observation" in payload.model_fields_set and payload.observation != learning.observation:
        learning.observation = payload.observation
        changed_fields.append("observation")

    if "evidence" in payload.model_fields_set and payload.evidence != learning.evidence:
        learning.evidence = payload.evidence
        changed_fields.append("evidence")

    if "next_action" in payload.model_fields_set and payload.next_action != learning.next_action:
        learning.next_action = payload.next_action
        changed_fields.append("next_action")

    if not changed_fields:
        return

    learning.updated_at = _now_utc()
    try:
        db.add(learning)
        db.flush()
        add_event(
            db,
            run.id,
            "performance.learning_updated",
            "Performance learning updated.",
            stage=run.current_stage.value if hasattr(run.current_stage, "value") else str(run.current_stage),
            metadata={
                "learning_id": learning.id,
                "learning_type": learning.learning_type,
                "platform_post_id": learning.platform_post_id,
                "changed_fields": sorted(changed_fields),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


def archive_performance_learning(db: Session, run_id: str, learning_id: str) -> None:
    from app.services.pipeline_service import add_event

    run, _package = _get_run_and_package(db, run_id)
    learning = _get_learning_for_run(db, run.id, learning_id)
    if learning.is_archived:
        return

    now = _now_utc()
    learning.is_archived = True
    learning.archived_at = now
    learning.updated_at = now
    try:
        db.add(learning)
        db.flush()
        add_event(
            db,
            run.id,
            "performance.learning_archived",
            "Performance learning archived.",
            stage=run.current_stage.value if hasattr(run.current_stage, "value") else str(run.current_stage),
            metadata={
                "learning_id": learning.id,
                "learning_type": learning.learning_type,
                "platform_post_id": learning.platform_post_id,
                "archived_at": now.isoformat(),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
