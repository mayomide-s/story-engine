from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.idea_queue import IdeaQueueBatchUpdate, IdeaQueueCreate, IdeaQueueItemResponse, IdeaQueuePatch, IdeaQueueScoreRequest, IdeaScoreResponse
from app.services.idea_queue_service import (
    archive_idea_queue_item,
    batch_update_idea_queue_items,
    create_idea_queue_item,
    generate_run_from_idea_queue_item,
    list_idea_queue_items,
    patch_idea_queue_item,
    score_idea_queue_items,
    serialize_idea_queue_item_response,
)
from app.services.access_service import require_app_access

router = APIRouter(prefix="/idea-queue", tags=["idea-queue"], dependencies=[Depends(require_app_access)])


@router.get("", response_model=list[IdeaQueueItemResponse])
def get_idea_queue(db: Session = Depends(get_db)):
    return [serialize_idea_queue_item_response(item) for item in list_idea_queue_items(db)]


@router.post("", response_model=IdeaQueueItemResponse)
def create_idea(payload: IdeaQueueCreate, db: Session = Depends(get_db)):
    return serialize_idea_queue_item_response(create_idea_queue_item(db, payload))


@router.patch("/{item_id}", response_model=IdeaQueueItemResponse)
def update_idea(item_id: str, payload: IdeaQueuePatch, db: Session = Depends(get_db)):
    try:
        return serialize_idea_queue_item_response(patch_idea_queue_item(db, item_id, payload))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{item_id}/archive", response_model=IdeaQueueItemResponse)
def archive_idea(item_id: str, db: Session = Depends(get_db)):
    try:
        return serialize_idea_queue_item_response(archive_idea_queue_item(db, item_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{item_id}/generate-run")
def generate_run(item_id: str, db: Session = Depends(get_db)):
    try:
        return generate_run_from_idea_queue_item(db, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/batch-update", response_model=list[IdeaQueueItemResponse])
def batch_update(payload: IdeaQueueBatchUpdate, db: Session = Depends(get_db)):
    try:
        return batch_update_idea_queue_items(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/score", response_model=list[IdeaScoreResponse])
def score_selected(payload: IdeaQueueScoreRequest, db: Session = Depends(get_db)):
    try:
        return score_idea_queue_items(db, payload.item_ids)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
