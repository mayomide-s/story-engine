from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import IdeaQueueItem, IdeaQueueStatus, PipelineRun
from app.schemas.idea_queue import IdeaQueueCreate, IdeaQueuePatch
from app.schemas.pipeline_runs import PipelineRunCreate
from app.services.pipeline_service import build_idea_input_config, create_pipeline_run, get_default_account, serialize_model


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
