from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.publication import (
    PublicationJobDraftRequest,
    PublicationJobMutationResponse,
    PublicationJobResponse,
)
from app.services.access_service import require_app_access
from app.services.publication_service import (
    PublicationConflictError,
    approve_publication_job,
    cancel_publication_job,
    create_publication_job_draft,
    get_publication_job,
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


@router.post("/publication-jobs/{job_id}/approve", response_model=PublicationJobMutationResponse)
def approve_publication_job_route(job_id: UUID, db: Session = Depends(get_db)):
    try:
        return PublicationJobMutationResponse(job=approve_publication_job(db, str(job_id)))
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
