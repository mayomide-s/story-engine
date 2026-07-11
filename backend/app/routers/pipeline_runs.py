from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.pipeline_runs import (
    AggregatedPipelineRunResponse,
    ContentIdeaPatch,
    FinalAssetSelectionPayload,
    HumanStoryAdherenceReviewPayload,
    NarrationDraftCreatePayload,
    NarrationDraftPatchPayload,
    NarrationHumanReviewPayload,
    NarrationRenderCreatePayload,
    NarrationSpeechRetryPayload,
    PipelineRunCreate,
    PromptActionRequest,
    ReviewConfigPatch,
    ReviewAction,
    ScriptPatch,
    StoryAdherenceRecheckPayload,
    StoryboardPatch,
)
from app.services.final_asset_service import select_final_asset
from app.services.pipeline_service import (
    PaidGenerationConfirmationRequiredError,
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
    record_story_adherence_human_review,
    regenerate_text_only,
    recheck_pipeline_assets,
    recheck_story_adherence,
    resume_pipeline,
)
from app.services.access_service import require_app_access
from app.services.narration_service import (
    PaidNarrationConfirmationRequiredError,
    create_narration_draft,
    create_narration_render,
    patch_narration_draft,
    record_narration_human_review,
    recompose_narration_render,
    retry_narration_speech,
    regenerate_narration_draft,
)

router = APIRouter(prefix="/pipeline-runs", tags=["pipeline-runs"], dependencies=[Depends(require_app_access)])


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
        confirm_paid_generation = payload.confirm_paid_generation if payload else False
        run = resume_pipeline(db, run_id, review_notes, confirm_paid_generation)
        return get_pipeline_run_detail(db, run.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PaidGenerationConfirmationRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnsafeResumeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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


@router.post("/{run_id}/story-adherence/recheck")
def recheck_run_story_adherence(
    run_id: str,
    payload: StoryAdherenceRecheckPayload | None = Body(default=None),
    db: Session = Depends(get_db),
):
    try:
        run = recheck_story_adherence(db, run_id, payload)
        return get_pipeline_run_detail(db, run.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{run_id}/story-adherence/human-review")
def save_human_story_review(
    run_id: str,
    payload: HumanStoryAdherenceReviewPayload,
    db: Session = Depends(get_db),
):
    try:
        run = record_story_adherence_human_review(db, run_id, payload)
        return get_pipeline_run_detail(db, run.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{run_id}/narration/draft")
def create_run_narration_draft(run_id: str, payload: NarrationDraftCreatePayload | None = Body(default=None), db: Session = Depends(get_db)):
    try:
        create_narration_draft(db, run_id, confirm_paid_draft=payload.confirm_paid_draft if payload else False)
        return get_pipeline_run_detail(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PaidNarrationConfirmationRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{run_id}/narration/draft/regenerate")
def regenerate_run_narration_draft(run_id: str, payload: NarrationDraftCreatePayload | None = Body(default=None), db: Session = Depends(get_db)):
    try:
        regenerate_narration_draft(db, run_id, confirm_paid_draft=payload.confirm_paid_draft if payload else False)
        return get_pipeline_run_detail(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PaidNarrationConfirmationRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{run_id}/narration/draft")
def update_run_narration_draft(run_id: str, payload: NarrationDraftPatchPayload, db: Session = Depends(get_db)):
    try:
        patch_narration_draft(db, run_id, payload.model_dump(exclude_none=True))
        return get_pipeline_run_detail(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{run_id}/narration/render")
def render_run_narration(run_id: str, payload: NarrationRenderCreatePayload, db: Session = Depends(get_db)):
    try:
        create_narration_render(
            db,
            run_id,
            confirm_paid_narration=payload.confirm_paid_narration,
            confirm_unapproved_story=payload.confirm_unapproved_story,
            voice=payload.voice,
        )
        return get_pipeline_run_detail(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PaidNarrationConfirmationRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{run_id}/narration/renders/{render_id}/recompose")
def recompose_run_narration(run_id: str, render_id: str, db: Session = Depends(get_db)):
    try:
        recompose_narration_render(db, run_id, render_id)
        return get_pipeline_run_detail(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{run_id}/narration/renders/{render_id}/retry-speech")
def retry_run_narration_speech(
    run_id: str,
    render_id: str,
    payload: NarrationSpeechRetryPayload,
    db: Session = Depends(get_db),
):
    try:
        retry_narration_speech(
            db,
            run_id,
            render_id,
            confirm_paid_narration=payload.confirm_paid_narration,
            confirm_possible_duplicate_charge=payload.confirm_possible_duplicate_charge,
        )
        return get_pipeline_run_detail(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PaidNarrationConfirmationRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{run_id}/narration/human-review")
def save_narration_human_review(run_id: str, payload: NarrationHumanReviewPayload, db: Session = Depends(get_db)):
    try:
        record_narration_human_review(db, run_id, payload.narration_render_id, payload.decision, payload.notes)
        return get_pipeline_run_detail(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{run_id}/final-asset/select", response_model=AggregatedPipelineRunResponse)
def select_run_final_asset(run_id: str, payload: FinalAssetSelectionPayload, db: Session = Depends(get_db)):
    try:
        run = select_final_asset(
            db,
            run_id,
            payload.source,
            narration_render_id=payload.narration_render_id,
            confirm_change_after_posting=payload.confirm_change_after_posting,
        )
        return get_pipeline_run_detail(db, run.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
