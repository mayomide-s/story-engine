from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import IdeaQueueItem, IdeaQueueStatus, PipelineRun
from app.schemas.idea_queue import IdeaQueueCreate, IdeaQueuePatch
from app.schemas.pipeline_runs import PipelineRunCreate
from app.services.pipeline_service import create_pipeline_run, get_default_account, serialize_model


def create_idea_queue_item(db: Session, payload: IdeaQueueCreate) -> IdeaQueueItem:
    account = get_default_account(db)
    item = IdeaQueueItem(
        account_id=account.id,
        topic=payload.topic,
        style_preset=payload.style_preset,
        target_platform=payload.target_platform,
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
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
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
            priority=item.priority,
        ),
    )
    item.pipeline_run_id = run.id
    item.status = IdeaQueueStatus.GENERATED
    db.commit()
    db.refresh(item)
    return {"idea_queue_item": serialize_model(item), "pipeline_run": serialize_model(db.get(PipelineRun, run.id))}
