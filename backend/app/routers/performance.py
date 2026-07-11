from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.performance import (
    PerformanceLearningCreatePayload,
    PerformanceLearningPatchPayload,
    PerformanceSnapshotCreatePayload,
    PerformanceWinnerSelectionPayload,
    PlatformPostCreatePayload,
    PlatformPostUpdatePayload,
)
from app.services.performance_learning_service import (
    PerformanceLearningConflictError,
    archive_performance_learning,
    create_performance_learning,
    update_performance_learning,
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
def get_run_performance(run_id: UUID, db: Session = Depends(get_db)):
    try:
        return get_run_performance_data(db, str(run_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{run_id}/performance/posts", status_code=status.HTTP_201_CREATED)
def create_run_platform_post(run_id: UUID, payload: PlatformPostCreatePayload, db: Session = Depends(get_db)):
    try:
        return create_platform_post(db, str(run_id), payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/{run_id}/performance/posts/{post_id}")
def update_run_platform_post(run_id: UUID, post_id: UUID, payload: PlatformPostUpdatePayload, db: Session = Depends(get_db)):
    try:
        return update_platform_post(db, str(run_id), str(post_id), payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{run_id}/performance/posts/{post_id}/snapshots", status_code=status.HTTP_201_CREATED)
def create_run_performance_snapshot(
    run_id: UUID,
    post_id: UUID,
    payload: PerformanceSnapshotCreatePayload = Body(...),
    db: Session = Depends(get_db),
):
    try:
        return append_performance_snapshot(db, str(run_id), str(post_id), payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{run_id}/performance/winner")
def select_run_performance_winner(
    run_id: UUID,
    payload: PerformanceWinnerSelectionPayload,
    db: Session = Depends(get_db),
):
    try:
        return select_winner_platform_post(db, str(run_id), payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{run_id}/performance/winner")
def clear_run_performance_winner(run_id: UUID, db: Session = Depends(get_db)):
    try:
        return clear_winner_platform_post(db, str(run_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{run_id}/performance/learnings", status_code=status.HTTP_201_CREATED)
def create_run_performance_learning(
    run_id: UUID,
    payload: PerformanceLearningCreatePayload,
    db: Session = Depends(get_db),
):
    try:
        run_id_str = str(run_id)
        create_performance_learning(db, run_id_str, payload)
        return get_run_performance_data(db, run_id_str)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceLearningConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/{run_id}/performance/learnings/{learning_id}")
def update_run_performance_learning(
    run_id: UUID,
    learning_id: UUID,
    payload: PerformanceLearningPatchPayload,
    db: Session = Depends(get_db),
):
    try:
        run_id_str = str(run_id)
        update_performance_learning(db, run_id_str, str(learning_id), payload)
        return get_run_performance_data(db, run_id_str)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceLearningConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{run_id}/performance/learnings/{learning_id}/archive")
def archive_run_performance_learning(run_id: UUID, learning_id: UUID, db: Session = Depends(get_db)):
    try:
        run_id_str = str(run_id)
        archive_performance_learning(db, run_id_str, str(learning_id))
        return get_run_performance_data(db, run_id_str)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PerformanceLearningConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
