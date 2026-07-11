from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.performance import (
    PerformanceSnapshotCreatePayload,
    PerformanceWinnerSelectionPayload,
    PlatformPostCreatePayload,
    PlatformPostUpdatePayload,
)
from app.services.access_service import require_app_access
from app.services.performance_service import (
    PerformanceConflictError,
    append_performance_snapshot,
    clear_winner_platform_post,
    create_platform_post,
    get_run_performance_data,
    select_winner_platform_post,
    update_platform_post,
)

router = APIRouter(
    prefix="/pipeline-runs",
    tags=["performance"],
    dependencies=[Depends(require_app_access)],
)


@router.get("/{run_id}/performance")
def get_run_performance(run_id: str, db: Session = Depends(get_db)):
    try:
        return get_run_performance_data(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{run_id}/performance/posts", status_code=status.HTTP_201_CREATED)
def create_run_platform_post(run_id: str, payload: PlatformPostCreatePayload, db: Session = Depends(get_db)):
    try:
        return create_platform_post(db, run_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/{run_id}/performance/posts/{post_id}")
def update_run_platform_post(run_id: str, post_id: str, payload: PlatformPostUpdatePayload, db: Session = Depends(get_db)):
    try:
        return update_platform_post(db, run_id, post_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{run_id}/performance/posts/{post_id}/snapshots", status_code=status.HTTP_201_CREATED)
def create_run_performance_snapshot(
    run_id: str,
    post_id: str,
    payload: PerformanceSnapshotCreatePayload = Body(...),
    db: Session = Depends(get_db),
):
    try:
        return append_performance_snapshot(db, run_id, post_id, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{run_id}/performance/winner")
def select_run_performance_winner(
    run_id: str,
    payload: PerformanceWinnerSelectionPayload,
    db: Session = Depends(get_db),
):
    try:
        return select_winner_platform_post(db, run_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{run_id}/performance/winner")
def clear_run_performance_winner(run_id: str, db: Session = Depends(get_db)):
    try:
        return clear_winner_platform_post(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
