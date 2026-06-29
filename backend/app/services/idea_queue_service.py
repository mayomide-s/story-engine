from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import IdeaQueueItem, IdeaQueueStatus, PipelineRun
from app.schemas.idea_queue import IdeaQueueBatchUpdate, IdeaQueueCreate, IdeaQueuePatch
from app.schemas.pipeline_runs import PipelineRunCreate
from app.services.pipeline_service import build_idea_input_config, create_pipeline_run, get_default_account, serialize_model
from app.services.providers import get_llm_provider


def _score_idea_item(item: IdeaQueueItem) -> dict[str, float | str]:
    llm = get_llm_provider()
    priority_value = item.priority.value if hasattr(item.priority, "value") else str(item.priority)
    status_value = item.status.value if hasattr(item.status, "value") else str(item.status)
    llm.generate(
        "idea_queue_score",
        "Score this idea for planning value only. Do not generate video prompts or assets.",
        {
            "topic": item.topic,
            "style_preset": item.style_preset,
            "target_platform": item.target_platform,
            "priority": priority_value,
            "notes": item.notes or "",
            "status": status_value,
        },
    )
    topic_words = len((item.topic or "").split())
    notes_words = len((item.notes or "").split())
    hook_strength = min(0.99, 0.55 + min(topic_words, 6) * 0.04 + (0.06 if priority_value == "high" else 0.0))
    beginner_clarity = 0.92 if (item.input_config_json or {}).get("audience_level") == "beginner" else 0.78 if (item.input_config_json or {}).get("audience_level") == "intermediate" else 0.7
    visual_potential = 0.9 if item.style_preset in {"bug_monster", "neon_club_metaphor", "office_comedy"} else 0.82
    platform_fit = 0.9 if item.target_platform in {"tiktok", "instagram"} else 0.84
    estimated_production_value = min(0.97, 0.62 + (0.08 if notes_words > 2 else 0.0) + (0.06 if item.style_preset != "whiteboard_character" else 0.0))
    overall_score = round((hook_strength + beginner_clarity + visual_potential + platform_fit + estimated_production_value) / 5, 2)
    return {
        "item_id": item.id,
        "hook_strength": round(hook_strength, 2),
        "beginner_clarity": round(beginner_clarity, 2),
        "visual_potential": round(visual_potential, 2),
        "platform_fit": round(platform_fit, 2),
        "estimated_production_value": round(estimated_production_value, 2),
        "overall_score": overall_score,
        "provider": llm.name,
        "model": llm.model,
    }


def _serialize_idea_item(item: IdeaQueueItem) -> dict[str, Any]:
    payload = serialize_model(item) or {}
    payload["idea_score"] = _score_idea_item(item)
    return payload


def create_idea_queue_item(db: Session, payload: IdeaQueueCreate) -> IdeaQueueItem:
    account = get_default_account(db)
    input_config = build_idea_input_config(account.account_config_json or {}, payload.model_dump(exclude_none=True))
    item = IdeaQueueItem(
        account_id=account.id,
        topic=payload.topic,
        style_preset=input_config["style_preset"],
        input_config_json=input_config,
        target_platform=(payload.target_platform or input_config["target_platforms"][0]),
        priority=payload.priority,
        status=payload.status,
        notes=payload.notes,
        planned_date=payload.planned_date,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_idea_queue_items(db: Session) -> list[IdeaQueueItem]:
    return db.query(IdeaQueueItem).order_by(IdeaQueueItem.planned_date.asc().nullslast(), IdeaQueueItem.created_at.desc()).all()


def patch_idea_queue_item(db: Session, item_id: str, payload: IdeaQueuePatch) -> IdeaQueueItem:
    item = db.get(IdeaQueueItem, item_id)
    if not item:
        raise ValueError("Idea queue item not found")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(item, key, value)
    if {"style_preset", "target_platform", "caption_tone", "duration_preference_seconds", "audience_level", "content_format"} & set(updates):
        account = get_default_account(db)
        item.input_config_json = build_idea_input_config(account.account_config_json or {}, updates, existing=item.input_config_json or {})
        item.style_preset = item.input_config_json["style_preset"]
        item.target_platform = updates.get("target_platform") or item.input_config_json["target_platforms"][0]
    db.commit()
    db.refresh(item)
    return item


def archive_idea_queue_item(db: Session, item_id: str) -> IdeaQueueItem:
    item = db.get(IdeaQueueItem, item_id)
    if not item:
        raise ValueError("Idea queue item not found")
    item.status = IdeaQueueStatus.ARCHIVED
    db.commit()
    db.refresh(item)
    return item


def generate_run_from_idea_queue_item(db: Session, item_id: str) -> dict:
    item = db.get(IdeaQueueItem, item_id)
    if not item:
        raise ValueError("Idea queue item not found")
    run = create_pipeline_run(
        db,
        PipelineRunCreate(
            topic=item.topic,
            auto_mode=False,
            style_preset=item.style_preset,
            target_platforms=(item.input_config_json or {}).get("target_platforms"),
            caption_tone=(item.input_config_json or {}).get("caption_tone"),
            duration_preference_seconds=(item.input_config_json or {}).get("duration_preference_seconds"),
            audience_level=(item.input_config_json or {}).get("audience_level"),
            content_format=(item.input_config_json or {}).get("content_format"),
            priority=item.priority,
        ),
    )
    item.pipeline_run_id = run.id
    item.status = IdeaQueueStatus.GENERATED
    db.commit()
    db.refresh(item)
    return {"idea_queue_item": serialize_model(item), "pipeline_run": serialize_model(db.get(PipelineRun, run.id))}


def batch_update_idea_queue_items(db: Session, payload: IdeaQueueBatchUpdate) -> list[dict[str, Any]]:
    if not payload.item_ids:
        return []
    items = db.query(IdeaQueueItem).filter(IdeaQueueItem.id.in_(payload.item_ids)).all()
    if not items:
        raise ValueError("Idea queue items not found")
    account = get_default_account(db)
    for item in items:
        if payload.archive_selected:
            item.status = IdeaQueueStatus.ARCHIVED
        elif payload.status is not None:
            item.status = payload.status
        if payload.target_platform is not None:
            item.target_platform = payload.target_platform
        if payload.style_preset is not None:
            item.style_preset = payload.style_preset
        if payload.priority is not None:
            item.priority = payload.priority
        if payload.planned_date is not None:
            item.planned_date = payload.planned_date
        idea_updates = {
            "style_preset": payload.style_preset if payload.style_preset is not None else item.style_preset,
            "target_platform": payload.target_platform if payload.target_platform is not None else item.target_platform,
        }
        item.input_config_json = build_idea_input_config(account.account_config_json or {}, idea_updates, existing=item.input_config_json or {})
        item.style_preset = item.input_config_json["style_preset"]
    db.commit()
    for item in items:
        db.refresh(item)
    return [_serialize_idea_item(item) for item in items]


def score_idea_queue_items(db: Session, item_ids: list[str]) -> list[dict[str, float | str]]:
    if not item_ids:
        return []
    items = db.query(IdeaQueueItem).filter(IdeaQueueItem.id.in_(item_ids)).all()
    if not items:
        raise ValueError("Idea queue items not found")
    return [_score_idea_item(item) for item in items]


def serialize_idea_queue_item_response(item: IdeaQueueItem) -> dict[str, Any]:
    return _serialize_idea_item(item)
