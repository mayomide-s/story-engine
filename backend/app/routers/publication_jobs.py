from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.publication import (
    PublicationJobDraftRequest,
    PublicationJobMutationResponse,
    PublicationJobResponse,
    PublicationTargetResponse,
)
from app.services.access_service import require_app_access
from app.services.publication_service import (
    PublicationConflictError,
    approve_publication_job,
    cancel_publication_job,
    create_publication_job_draft,
    get_publication_job,
)
from app.services.publication_execution_service import (
    dispatch_publication_job,
    get_publication_target,
    get_run_publication_job,
    request_reconcile_publication_target,
    retry_publication_target,
)


router = APIRouter(
    tags=["publication-jobs"],
    dependencies=[Depends(require_app_access)],
)


@router.post("/pipeline-runs/{run_id}/publication-jobs", response_model=PublicationJobMutationResponse, status_code=201)
def create_run_publication_job(run_id: UUID, payload: PublicationJobDraftRequest, db: Session = Depends(get_db)):
    try:
        return PublicationJobMutationResponse(job=create_publication_job_draft(db, str(run_id), payload))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PublicationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/publication-jobs/{job_id}", response_model=PublicationJobResponse)
def get_publication_job_route(job_id: UUID, db: Session = Depends(get_db)):
    try:
        return PublicationJobResponse(**get_publication_job(db, str(job_id)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/pipeline-runs/{run_id}/publication-jobs/latest", response_model=PublicationJobResponse)
def get_latest_run_publication_job_route(run_id: UUID, db: Session = Depends(get_db)):
    try:
        return PublicationJobResponse(**get_run_publication_job(db, str(run_id)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/publication-jobs/{job_id}/approve", response_model=PublicationJobMutationResponse)
def approve_publication_job_route(job_id: UUID, db: Session = Depends(get_db)):
    try:
        return PublicationJobMutationResponse(job=approve_publication_job(db, str(job_id)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PublicationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/publication-jobs/{job_id}/dispatch", response_model=PublicationJobMutationResponse)
def dispatch_publication_job_route(job_id: UUID, db: Session = Depends(get_db)):
    try:
        return PublicationJobMutationResponse(job=dispatch_publication_job(db, str(job_id)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PublicationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/publication-jobs/{job_id}/cancel", response_model=PublicationJobMutationResponse)
def cancel_publication_job_route(job_id: UUID, db: Session = Depends(get_db)):
    try:
        return PublicationJobMutationResponse(job=cancel_publication_job(db, str(job_id)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PublicationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/publication-targets/{target_id}", response_model=PublicationTargetResponse)
def get_publication_target_route(target_id: UUID, db: Session = Depends(get_db)):
    try:
        return get_publication_target(db, str(target_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PublicationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/publication-targets/{target_id}/retry", response_model=PublicationJobMutationResponse)
def retry_publication_target_route(target_id: UUID, db: Session = Depends(get_db)):
    try:
        return PublicationJobMutationResponse(job=retry_publication_target(db, str(target_id)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PublicationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/publication-targets/{target_id}/reconcile", response_model=PublicationJobMutationResponse)
def reconcile_publication_target_route(target_id: UUID, db: Session = Depends(get_db)):
    try:
        return PublicationJobMutationResponse(job=request_reconcile_publication_target(db, str(target_id)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PublicationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
