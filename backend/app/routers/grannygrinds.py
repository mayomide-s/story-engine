from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.grannygrinds import (
    GrannyCharacterResponse,
    GrannyGrindCreate,
    GrannyGrindJobResponse,
    GrannyGrindPublishRequest,
    GrannyGrindRegenerate,
    GrannyGrindReview,
)
from app.services.access_service import require_app_access, require_csrf_protection
from app.services.grannygrinds_service import (
    GrannyGrindsConflictError,
    approve_grannygrind_job,
    create_grannygrind_job,
    create_grannygrind_uploaded_job,
    get_grannygrind_job,
    list_granny_characters,
    list_grannygrind_jobs,
    regenerate_grannygrind_job,
    reject_grannygrind_job,
    request_instagram_publish,
)


router = APIRouter(
    prefix="/grannygrinds",
    tags=["grannygrinds"],
    dependencies=[Depends(require_app_access), Depends(require_csrf_protection)],
)


@router.get("/characters", response_model=list[GrannyCharacterResponse])
def characters():
    return list_granny_characters()


@router.get("/jobs", response_model=list[GrannyGrindJobResponse])
def jobs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return list_grannygrind_jobs(db, limit=limit)


@router.post("/jobs", response_model=GrannyGrindJobResponse, status_code=201)
def create_job(payload: GrannyGrindCreate, db: Session = Depends(get_db)):
    try:
        return create_grannygrind_job(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GrannyGrindsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/upload", response_model=GrannyGrindJobResponse, status_code=201)
async def upload_job(
    source_post_url: str = Form(...),
    source_creator_handle: str | None = Form(default=None),
    source_credit_text: str | None = Form(default=None),
    rights_status: str = Form(default="credited"),
    confirm_paid_generation: bool = Form(default=False),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = (file.filename or "").lower()
    if not filename.endswith(".mp4") and file.content_type != "video/mp4":
        raise HTTPException(status_code=422, detail="First-10 uploads must be MP4 video files.")

    max_bytes = 250 * 1024 * 1024
    written = 0
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="grannygrinds-upload-", suffix=".mp4", delete=False) as handle:
            temp_path = Path(handle.name)
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(status_code=413, detail="Uploaded video exceeds the 250 MB limit.")
                handle.write(chunk)
        if written == 0:
            raise HTTPException(status_code=422, detail="Uploaded video is empty.")

        return create_grannygrind_uploaded_job(
            db,
            source_path=temp_path,
            source_post_url=source_post_url,
            source_creator_handle=source_creator_handle,
            source_credit_text=source_credit_text,
            rights_status=rights_status,
            confirm_paid_generation=confirm_paid_generation,
        )
    except GrannyGrindsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@router.get("/jobs/{job_id}", response_model=GrannyGrindJobResponse)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    try:
        return get_grannygrind_job(db, str(job_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/regenerate", response_model=GrannyGrindJobResponse)
def regenerate_job(job_id: UUID, payload: GrannyGrindRegenerate, db: Session = Depends(get_db)):
    try:
        return regenerate_grannygrind_job(
            db,
            str(job_id),
            confirm_paid_generation=payload.confirm_paid_generation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GrannyGrindsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/approve", response_model=GrannyGrindJobResponse)
def approve_job(job_id: UUID, payload: GrannyGrindReview, db: Session = Depends(get_db)):
    try:
        return approve_grannygrind_job(db, str(job_id), notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GrannyGrindsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/reject", response_model=GrannyGrindJobResponse)
def reject_job(job_id: UUID, payload: GrannyGrindReview, db: Session = Depends(get_db)):
    try:
        return reject_grannygrind_job(db, str(job_id), notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GrannyGrindsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/publish", response_model=GrannyGrindJobResponse)
def publish_job(job_id: UUID, payload: GrannyGrindPublishRequest, db: Session = Depends(get_db)):
    try:
        return request_instagram_publish(
            db,
            str(job_id),
            caption=payload.caption,
            share_to_feed=payload.share_to_feed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GrannyGrindsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
