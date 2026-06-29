from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.pipeline_runs import (
    AggregatedPipelineRunResponse,
    ContentIdeaPatch,
    PipelineRunCreate,
    PromptActionRequest,
    ReviewConfigPatch,
    ReviewAction,
    ScriptPatch,
    StoryboardPatch,
)
from app.services.pipeline_service import (
    UnsafeResumeError,
    cancel_pipeline,
    create_pipeline_run,
    get_pipeline_run_detail,
    get_pipeline_run_summary,
    list_pipeline_runs,
    patch_idea,
    prompt_action_pipeline,
    patch_review_config,
    patch_script,
    patch_storyboard,
    regenerate_text_only,
    recheck_pipeline_assets,
    resume_pipeline,
)

router = APIRouter(prefix="/pipeline-runs", tags=["pipeline-runs"])


@router.post("")
def create_run(payload: PipelineRunCreate, db: Session = Depends(get_db)):
    try:
        return get_pipeline_run_detail(db, create_pipeline_run(db, payload).id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def get_runs(db: Session = Depends(get_db)):
    return [get_pipeline_run_summary(db, run) for run in list_pipeline_runs(db)]


@router.get("/{run_id}", response_model=AggregatedPipelineRunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    try:
        return get_pipeline_run_detail(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{run_id}/resume")
def resume_run(run_id: str, payload: ReviewAction | None = Body(default=None), db: Session = Depends(get_db)):
    try:
        review_notes = payload.review_notes if payload else "Approved from dashboard"
        run = resume_pipeline(db, run_id, review_notes)
        return get_pipeline_run_detail(db, run.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsafeResumeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{run_id}/cancel")
def cancel_run(run_id: str, payload: ReviewAction | None = Body(default=None), db: Session = Depends(get_db)):
    try:
        run = cancel_pipeline(db, run_id, payload.review_notes if payload else None)
        return get_pipeline_run_detail(db, run.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{run_id}/recheck")
def recheck_run(run_id: str, payload: ReviewAction | None = Body(default=None), db: Session = Depends(get_db)):
    try:
        run = recheck_pipeline_assets(db, run_id, payload.review_notes if payload else None)
        return get_pipeline_run_detail(db, run.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{run_id}/idea")
def update_idea(run_id: str, payload: ContentIdeaPatch, db: Session = Depends(get_db)):
    try:
        run = patch_idea(db, run_id, payload)
        return get_pipeline_run_detail(db, run.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{run_id}/script")
def update_script(run_id: str, payload: ScriptPatch, db: Session = Depends(get_db)):
    try:
        run = patch_script(db, run_id, payload)
        return get_pipeline_run_detail(db, run.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{run_id}/storyboard")
def update_storyboard(run_id: str, payload: StoryboardPatch, db: Session = Depends(get_db)):
    try:
        run = patch_storyboard(db, run_id, payload)
        return get_pipeline_run_detail(db, run.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{run_id}/review-config")
def update_review_config(run_id: str, payload: ReviewConfigPatch, db: Session = Depends(get_db)):
    try:
        run = patch_review_config(db, run_id, payload)
        return get_pipeline_run_detail(db, run.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{run_id}/regenerate-text")
def regenerate_run_text(run_id: str, payload: ReviewAction | None = Body(default=None), db: Session = Depends(get_db)):
    try:
        run = regenerate_text_only(db, run_id, payload.review_notes if payload else None)
        return get_pipeline_run_detail(db, run.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{run_id}/prompt-actions")
def run_prompt_action(run_id: str, payload: PromptActionRequest, db: Session = Depends(get_db)):
    try:
        run = prompt_action_pipeline(db, run_id, payload.action)
        return get_pipeline_run_detail(db, run.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
