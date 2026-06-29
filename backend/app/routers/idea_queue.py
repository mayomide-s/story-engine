from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.idea_queue import IdeaQueueCreate, IdeaQueueItemResponse, IdeaQueuePatch
from app.services.idea_queue_service import (
    archive_idea_queue_item,
    create_idea_queue_item,
    generate_run_from_idea_queue_item,
    list_idea_queue_items,
    patch_idea_queue_item,
)

router = APIRouter(prefix="/idea-queue", tags=["idea-queue"])


@router.get("", response_model=list[IdeaQueueItemResponse])
def get_idea_queue(db: Session = Depends(get_db)):
    return list_idea_queue_items(db)


@router.post("", response_model=IdeaQueueItemResponse)
def create_idea(payload: IdeaQueueCreate, db: Session = Depends(get_db)):
    return create_idea_queue_item(db, payload)


@router.patch("/{item_id}", response_model=IdeaQueueItemResponse)
def update_idea(item_id: str, payload: IdeaQueuePatch, db: Session = Depends(get_db)):
    try:
        return patch_idea_queue_item(db, item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{item_id}/archive", response_model=IdeaQueueItemResponse)
def archive_idea(item_id: str, db: Session = Depends(get_db)):
    try:
        return archive_idea_queue_item(db, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{item_id}/generate-run")
def generate_run(item_id: str, db: Session = Depends(get_db)):
    try:
        return generate_run_from_idea_queue_item(db, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
