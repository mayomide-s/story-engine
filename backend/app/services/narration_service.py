from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import SessionLocal
from app.models import (
    Asset,
    ContentIdea,
    GenerationCost,
    NarrationDraft,
    NarrationDraftStatus,
    NarrationRender,
    NarrationRenderStatus,
    PipelineEvent,
    PipelineRun,
    PromptLog,
    Script,
    StoryAdherenceHumanReview,
    StoryAdherenceReview,
    Storyboard,
    Video,
)
from app.services.providers import (
    get_narration_writer_provider,
    get_speech_provider,
    get_storage_provider,
)
from app.services.security import redact_sensitive_data, sanitize_for_json

AI_VOICE_DISCLOSURE = "AI-generated narration"
FAILURE_STAGES = {"writer", "speech", "audio_upload", "caption_generation", "composition", "asset_upload", "output_validation"}
NARRATION_OPENING_LEAD_IN_RATIO = 0.04
NARRATION_ENDING_TAIL_RATIO = 0.04
NARRATION_MIN_EDGE_SECONDS = 0.25
NARRATION_MAX_EDGE_SECONDS = 0.5
NARRATION_FINAL_END_EPSILON_SECONDS = 0.01
WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")


class PaidNarrationConfirmationRequiredError(RuntimeError):
    """Raised when a paid narration step needs explicit confirmation."""


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def serialize_model(instance) -> dict[str, Any] | None:
    if instance is None:
        return None
    data: dict[str, Any] = {}
    for column in instance.__table__.columns:
        value = getattr(instance, column.name)
        data[column.name] = value.value if hasattr(value, "value") else value
    return sanitize_for_json(data)


def add_event(
    db: Session,
    run_id: str,
    event_type: str,
    message: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        PipelineEvent(
            pipeline_run_id=run_id,
            event_type=event_type,
            stage="narration",
            message=message,
            metadata_json=sanitize_for_json(metadata or {}),
        )
    )
    db.flush()


def add_cost(
    db: Session,
    *,
    run_id: str,
    provider: str,
    model: str,
    stage: str,
    estimated_cost: float,
    credits_used: float = 0.0,
) -> None:
    db.add(
        GenerationCost(
            pipeline_run_id=run_id,
            provider=provider,
            model=model,
            stage=stage,
            estimated_cost=estimated_cost,
            credits_used=credits_used,
        )
    )


def add_prompt_log(
    db: Session,
    *,
    run_id: str,
    stage: str,
    provider: str,
    model: str,
    prompt_text: str,
    request_json: dict[str, Any],
    response_json: dict[str, Any],
    output_text: str,
    token_usage_json: dict[str, Any],
    cost_estimate: float,
) -> None:
    db.add(
        PromptLog(
            pipeline_run_id=run_id,
            stage=stage,
            provider=provider,
            model=model,
            prompt_text=prompt_text,
            request_json=redact_sensitive_data(request_json),
            response_json=redact_sensitive_data(response_json),
            output_text=output_text,
            token_usage_json=sanitize_for_json(token_usage_json),
            cost_estimate=cost_estimate,
        )
    )


def get_latest_narration_render(db: Session, run_id: str) -> NarrationRender | None:
    return (
        db.query(NarrationRender)
        .filter(NarrationRender.pipeline_run_id == run_id)
        .order_by(NarrationRender.created_at.desc())
        .first()
    )


def get_narration_draft_for_run(db: Session, run_id: str) -> NarrationDraft | None:
    return (
        db.query(NarrationDraft)
        .filter(NarrationDraft.pipeline_run_id == run_id)
        .order_by(NarrationDraft.updated_at.desc())
        .first()
    )


def get_video_asset(db: Session, run_id: str) -> Asset | None:
    return (
        db.query(Asset)
        .filter(Asset.pipeline_run_id == run_id, Asset.asset_type == "video_mp4")
        .order_by(Asset.created_at.desc())
        .first()
    )


def get_asset_by_id(db: Session, asset_id: str | None) -> Asset | None:
    return db.get(Asset, asset_id) if asset_id else None


def _safe_story_contract(run: PipelineRun, script: Script | None, storyboard: Storyboard | None) -> dict[str, Any]:
    if script and isinstance(script.script_json, dict):
        contract = script.script_json.get("story_adherence_contract")
        if isinstance(contract, dict):
            return contract
    if storyboard and isinstance(storyboard.frames_json, dict):
        contract = storyboard.frames_json.get("story_adherence_contract")
        if isinstance(contract, dict):
            return contract
    return {
        "subject": run.topic,
        "initial_state": f"A visible coding problem related to {run.topic}.",
        "trigger": "A single clear action starts the fix.",
        "required_transformation": "The coding problem visibly changes into a solved state.",
        "required_final_state": f"The ending clearly shows {run.topic} working.",
        "final_state_hold": "Hold on the solved result at the end.",
        "prohibited_actions": ["unrelated characters", "location changes", "generated text overlays"],
    }


def _get_story_reviews(
    db: Session,
    run_id: str,
    video_id: str | None,
) -> tuple[StoryAdherenceReview | None, StoryAdherenceHumanReview | None]:
    critic = None
    if video_id:
        critic = (
            db.query(StoryAdherenceReview)
            .filter(StoryAdherenceReview.video_id == video_id)
            .order_by(StoryAdherenceReview.created_at.desc())
            .first()
        )
    human = (
        db.query(StoryAdherenceHumanReview)
        .filter(StoryAdherenceHumanReview.pipeline_run_id == run_id)
        .order_by(StoryAdherenceHumanReview.updated_at.desc())
        .first()
    )
    return critic, human


def get_story_approval_snapshot(db: Session, run: PipelineRun, video: Video | None) -> tuple[str, str]:
    critic, human = _get_story_reviews(db, run.id, video.id if video else None)
    if human and human.decision == "approve":
        return "approved", "human_review"
    if human and human.decision in {"needs_review", "regenerate"}:
        return "unapproved", "human_review"
    if critic and critic.review_status == "accept":
        return "approved", "semantic_critic"
    return "unapproved", "review_required"


def _draft_attempt_timeout() -> timedelta:
    return timedelta(seconds=max(get_settings().narration_timeout_seconds, 30))


def _mark_draft_uncertain_if_needed(db: Session, draft: NarrationDraft) -> NarrationDraft:
    if draft.paid_call_outcome_uncertain:
        return draft
    if draft.status != NarrationDraftStatus.WRITER_GENERATING:
        return draft
    has_output = bool(draft.has_valid_content and draft.full_spoken_text)
    if draft.paid_call_completed_at and not draft.writer_completed_at:
        draft.paid_call_outcome_uncertain = True
    elif (
        draft.paid_call_started_at
        and draft.paid_call_started_at < now_utc() - _draft_attempt_timeout()
        and not draft.writer_completed_at
    ):
        draft.paid_call_outcome_uncertain = True
    if not draft.paid_call_outcome_uncertain:
        return draft
    draft.failure_reason = draft.failure_reason or "A paid narration draft call may have completed before the result was persisted."
    draft.failure_stage = "writer"
    if has_output:
        draft.status = NarrationDraftStatus.READY
        draft.has_valid_content = True
    else:
        draft.status = NarrationDraftStatus.UNAVAILABLE
    db.commit()
    db.refresh(draft)
    return draft


def _mark_render_uncertain_if_needed(db: Session, render: NarrationRender) -> NarrationRender:
    if render.paid_call_outcome_uncertain:
        return render
    if render.status != NarrationRenderStatus.SPEECH_GENERATING:
        return render
    if render.audio_asset_id:
        return render
    if render.paid_call_completed_at or (
        render.paid_call_started_at and render.paid_call_started_at < now_utc() - _draft_attempt_timeout()
    ):
        render.paid_call_outcome_uncertain = True
        render.failure_reason = render.failure_reason or "A paid narration speech call may have completed before the audio asset was persisted."
        render.failure_stage = "speech"
        render.status = NarrationRenderStatus.UNAVAILABLE
        db.commit()
        db.refresh(render)
    return render


def _assert_narration_enabled() -> None:
    settings = get_settings()
    if not settings.narration_enabled:
        raise RuntimeError("Narration is disabled in this environment.")


def _require_completed_video(db: Session, run_id: str) -> tuple[PipelineRun, Video, Asset]:
    run = db.get(PipelineRun, run_id)
    if not run:
        raise ValueError("Pipeline run not found")
    if str(run.status.value if hasattr(run.status, "value") else run.status) != "completed":
        raise RuntimeError("Narration is only available for completed runs.")
    video = db.get(Video, run.video_id) if run.video_id else None
    asset = get_video_asset(db, run.id)
    if not video or not asset:
        raise RuntimeError("Narration requires a completed video with an uploaded video asset.")
    return run, video, asset


def _segment_weight(item: dict[str, Any]) -> int:
    spoken_text = str(item.get("spoken_text") or "").strip()
    if spoken_text:
        return max(len(spoken_text.split()), 1)
    caption_text = str(item.get("caption_text") or "").strip()
    return max(len(caption_text), 1)


def calculate_spoken_word_count(full_spoken_text: str) -> int:
    return len(WORD_PATTERN.findall(full_spoken_text))


def _normalize_caption_text(spoken_text: str, caption_text: str | None, *, allow_caption_variation: bool) -> str:
    normalized_spoken = spoken_text.strip()
    normalized_caption = str(caption_text or "").strip()
    if not normalized_caption:
        return normalized_spoken
    if not allow_caption_variation:
        return normalized_spoken
    canonical_spoken = re.sub(r"[^a-z0-9]+", " ", normalized_spoken.lower()).strip()
    canonical_caption = re.sub(r"[^a-z0-9]+", " ", normalized_caption.lower()).strip()
    if canonical_spoken != canonical_caption:
        raise RuntimeError("Narration caption text must remain identical or extremely close to spoken text.")
    return normalized_caption


def _cost_metadata(response: dict[str, Any]) -> tuple[float | None, str]:
    if response.get("cost_estimate") is None:
        return None, "unavailable"
    return float(response.get("cost_estimate") or 0.0), "provided"


def _segment_edge_seconds(source_duration_seconds: float) -> float:
    return round(
        min(
            max(source_duration_seconds * NARRATION_OPENING_LEAD_IN_RATIO, NARRATION_MIN_EDGE_SECONDS),
            NARRATION_MAX_EDGE_SECONDS,
        ),
        2,
    )


def _narration_window_plan(source_duration_seconds: float, narration_duration_seconds: float | None = None) -> dict[str, float]:
    source_duration = max(float(source_duration_seconds), 1.0)
    lead_in = _segment_edge_seconds(source_duration)
    ending_tail = _segment_edge_seconds(source_duration)
    speech_window_start = lead_in
    speech_window_limit = round(max(source_duration - ending_tail, lead_in + 0.1), 2)
    available_speech_window = round(max(speech_window_limit - speech_window_start, 0.1), 2)
    if narration_duration_seconds is None:
        speech_window_end = speech_window_limit
    else:
        speech_window_end = round(min(speech_window_start + max(float(narration_duration_seconds), 0.0), speech_window_limit), 2)
    ending_silence = round(max(source_duration - speech_window_end, 0.0), 2)
    return {
        "source_duration_seconds": round(source_duration, 2),
        "lead_in_seconds": round(lead_in, 2),
        "speech_window_start_seconds": round(speech_window_start, 2),
        "speech_window_end_seconds": round(speech_window_end, 2),
        "available_speech_window_seconds": round(available_speech_window, 2),
        "ending_silence_seconds": round(ending_silence, 2),
    }


def _normalize_segment_timings(
    source_duration_seconds: float,
    raw_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not raw_segments:
        raise RuntimeError("Narration draft requires at least one timed segment.")
    window_plan = _narration_window_plan(source_duration_seconds)
    opening_lead_in = window_plan["lead_in_seconds"]
    ending_tail = _segment_edge_seconds(source_duration_seconds)
    final_end_limit = round(
        min(
            source_duration_seconds - NARRATION_FINAL_END_EPSILON_SECONDS,
            source_duration_seconds - ending_tail,
        ),
        2,
    )
    usable_start = opening_lead_in
    usable_window = round(final_end_limit - usable_start, 2)
    if usable_window <= 0:
        raise RuntimeError("Narration source video is too short for a safe narration timing window.")

    total_weight = sum(_segment_weight(item) for item in raw_segments)
    consumed = 0.0
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_segments):
        start = round(usable_start + consumed, 2)
        if index == len(raw_segments) - 1:
            end = final_end_limit
        else:
            proportion = _segment_weight(item) / max(total_weight, 1)
            duration = round(usable_window * proportion, 2)
            remaining_segments = len(raw_segments) - index - 1
            remaining_floor = remaining_segments * NARRATION_FINAL_END_EPSILON_SECONDS
            end = round(min(start + duration, final_end_limit - remaining_floor), 2)
            if end <= start:
                end = round(start + NARRATION_FINAL_END_EPSILON_SECONDS, 2)
        normalized.append(
            {
                "start_seconds": start,
                "end_seconds": end,
                "spoken_text": str(item.get("spoken_text") or "").strip(),
                "caption_text": str(item.get("caption_text") or "").strip(),
            }
        )
        consumed = round(end - usable_start, 2)
    return normalized


def _normalize_segments(
    payload: dict[str, Any],
    *,
    source_duration_seconds: float | None = None,
) -> tuple[list[dict[str, Any]], str, int]:
    settings = get_settings()
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise RuntimeError("Narration draft requires at least one timed segment.")
    allow_caption_variation = source_duration_seconds is None
    validated_raw_segments: list[dict[str, Any]] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            raise RuntimeError("Narration segments must be objects.")
        spoken_text = str(item.get("spoken_text") or "").strip()
        if not spoken_text:
            raise RuntimeError("Narration spoken text may not be empty.")
        caption_text = _normalize_caption_text(
            spoken_text,
            item.get("caption_text"),
            allow_caption_variation=allow_caption_variation,
        )
        validated_raw_segments.append(
            {
                "start_seconds": round(float(item.get("start_seconds", 0.0) or 0.0), 2),
                "end_seconds": round(float(item.get("end_seconds", 0.0) or 0.0), 2),
                "spoken_text": spoken_text,
                "caption_text": caption_text,
            }
        )
    full_spoken_text = str(payload.get("full_spoken_text") or " ".join(item["spoken_text"] for item in validated_raw_segments)).strip()
    word_count = calculate_spoken_word_count(full_spoken_text)
    if word_count > settings.narration_max_words:
        raise RuntimeError(f"Narration draft exceeds the {settings.narration_max_words}-word limit.")
    segments = (
        _normalize_segment_timings(float(source_duration_seconds), validated_raw_segments)
        if source_duration_seconds is not None
        else validated_raw_segments
    )
    return segments, full_spoken_text, word_count


def _validate_draft_against_duration(source_duration_seconds: float, segments: list[dict[str, Any]]) -> None:
    if not segments:
        raise RuntimeError("Narration draft requires at least one segment.")
    last_end = float(segments[-1]["end_seconds"])
    if last_end >= float(source_duration_seconds):
        raise RuntimeError("Narration draft must end before the source video ends.")


def _draft_attempt_metadata(
    response: dict[str, Any],
    *,
    validation_error: str | None = None,
) -> dict[str, Any]:
    estimated_cost, cost_estimation_status = _cost_metadata(response)
    attempt_output = redact_sensitive_data(
        {
            "segments": response.get("segments", []),
            "full_spoken_text": response.get("full_spoken_text", ""),
            "estimated_word_count": calculate_spoken_word_count(str(response.get("full_spoken_text") or "")),
            "provider_request_id": response.get("provider_request_id"),
        }
    )
    metadata = {
        "input_tokens": int((response.get("usage") or {}).get("input_tokens", 0) or 0),
        "output_tokens": int((response.get("usage") or {}).get("output_tokens", 0) or 0),
        "total_tokens": int((response.get("usage") or {}).get("total_tokens", 0) or 0),
        "cost_estimate": estimated_cost,
        "cost_estimation_status": cost_estimation_status,
        "attempt_output": attempt_output,
    }
    if validation_error:
        metadata["validation_error"] = validation_error
    return sanitize_for_json(metadata)


def _draft_attempt_record(
    draft: NarrationDraft,
    *,
    usage_metadata: dict[str, Any] | None = None,
    validation_result: str,
) -> dict[str, Any]:
    metadata = sanitize_for_json(usage_metadata or draft.usage_metadata_json or {})
    return sanitize_for_json(
        {
            "generation_revision": draft.generation_revision,
            "provider_attempt_id": draft.provider_attempt_id,
            "provider_request_id": draft.provider_request_id,
            "started_at": draft.paid_call_started_at.isoformat() if draft.paid_call_started_at else None,
            "completed_at": draft.paid_call_completed_at.isoformat() if draft.paid_call_completed_at else None,
            "writer_provider": draft.writer_provider,
            "writer_model": draft.writer_model,
            "writer_prompt_version": draft.writer_prompt_version,
            "usage_metadata": metadata,
            "estimated_cost": draft.estimated_writer_cost,
            "attempt_output": metadata.get("attempt_output", {}),
            "validation_result": validation_result,
            "validation_error": metadata.get("validation_error"),
            "failure_reason": draft.failure_reason,
            "failure_stage": draft.failure_stage,
            "uncertain_outcome": bool(draft.paid_call_outcome_uncertain),
        }
    )


def _append_draft_attempt_history(
    draft: NarrationDraft,
    *,
    usage_metadata: dict[str, Any] | None = None,
    validation_result: str,
) -> None:
    current_attempts = draft.attempts_json if isinstance(draft.attempts_json, list) else []
    attempt_record = _draft_attempt_record(
        draft,
        usage_metadata=usage_metadata,
        validation_result=validation_result,
    )
    provider_attempt_id = attempt_record.get("provider_attempt_id")
    generation_revision = attempt_record.get("generation_revision")
    filtered = [
        item
        for item in current_attempts
        if not (
            isinstance(item, dict)
            and item.get("generation_revision") == generation_revision
            and item.get("provider_attempt_id") == provider_attempt_id
        )
    ]
    filtered.append(attempt_record)
    draft.attempts_json = sanitize_for_json(filtered)


def _build_writer_payload(db: Session, run: PipelineRun, video: Video) -> dict[str, Any]:
    idea = db.get(ContentIdea, run.idea_id) if run.idea_id else None
    script = db.get(Script, run.script_id) if run.script_id else None
    storyboard = db.get(Storyboard, run.storyboard_id) if run.storyboard_id else None
    critic, human = _get_story_reviews(db, run.id, video.id)
    source_duration = float(video.duration_seconds or 10)
    return {
        "topic": run.topic,
        "audience_level": str((run.input_config_json or {}).get("audience_level") or "beginner"),
        "hook": idea.hook if idea else "",
        "concept": idea.concept if idea else "",
        "storyboard": storyboard.frames_json if storyboard else {},
        "approved_script": script.script_json if script else {},
        "outcome_contract": _safe_story_contract(run, script, storyboard),
        "generation_prompt": video.prompt_text,
        "story_review_explanation": critic.explanation if critic else "",
        "human_story_review_notes": human.notes if human else "",
        "source_duration_seconds": source_duration,
    }


def _write_draft_content(
    draft: NarrationDraft,
    *,
    segments: list[dict[str, Any]],
    full_spoken_text: str,
    word_count: int,
    usage_metadata: dict[str, Any],
    cost_estimate: float | None,
) -> None:
    draft.script_json = {"segments": segments}
    draft.full_spoken_text = full_spoken_text
    draft.estimated_word_count = word_count
    draft.usage_metadata_json = sanitize_for_json(usage_metadata)
    draft.estimated_writer_cost = cost_estimate
    draft.has_valid_content = True
    draft.manually_modified = False
    draft.failure_reason = None
    draft.failure_stage = None
    draft.paid_call_outcome_uncertain = False


def _claim_draft_for_generation(db: Session, draft_id: str, generation_revision: int, task_id: str | None) -> bool:
    draft = db.get(NarrationDraft, draft_id)
    if not draft:
        return False
    rows = (
        db.query(NarrationDraft)
        .filter(
            NarrationDraft.id == draft_id,
            NarrationDraft.generation_revision == generation_revision,
            NarrationDraft.status.in_([NarrationDraftStatus.QUEUED, NarrationDraftStatus.READY, NarrationDraftStatus.FAILED, NarrationDraftStatus.UNAVAILABLE]),
        )
        .update(
            {
                NarrationDraft.status: NarrationDraftStatus.WRITER_GENERATING,
                NarrationDraft.writer_task_id: task_id,
                NarrationDraft.writer_started_at: now_utc(),
                NarrationDraft.failure_reason: None,
                NarrationDraft.failure_stage: "writer",
                NarrationDraft.writer_completed_at: None,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return rows == 1


def create_narration_draft(db: Session, run_id: str, confirm_paid_draft: bool = False) -> NarrationDraft:
    _assert_narration_enabled()
    run, video, _asset = _require_completed_video(db, run_id)
    settings = get_settings()
    existing = get_narration_draft_for_run(db, run_id)
    if existing:
        return _mark_draft_uncertain_if_needed(db, existing)
    provider = get_narration_writer_provider()
    if provider is None:
        raise RuntimeError("Narration writer provider is unavailable.")
    if provider.name != "mock" and not confirm_paid_draft:
        raise PaidNarrationConfirmationRequiredError(
            "Paid narration draft generation requires confirm_paid_draft=true."
        )
    draft = NarrationDraft(
        pipeline_run_id=run.id,
        source_video_id=video.id,
        narration_version=settings.narration_version,
        status=NarrationDraftStatus.QUEUED,
        has_valid_content=False,
        generation_revision=1,
        writer_provider=provider.name,
        writer_model=provider.model,
        writer_prompt_version=settings.narration_writer_prompt_version,
        source_duration_seconds=float(video.duration_seconds or 10),
    )
    db.add(draft)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = get_narration_draft_for_run(db, run.id)
        if existing:
            return _mark_draft_uncertain_if_needed(db, existing)
        raise
    db.refresh(draft)
    _generate_draft_content(db, draft.id, confirm_paid_draft=confirm_paid_draft, regenerate=False)
    return db.get(NarrationDraft, draft.id) or draft


def regenerate_narration_draft(db: Session, run_id: str, confirm_paid_draft: bool = False) -> NarrationDraft:
    _assert_narration_enabled()
    run, _video, _asset = _require_completed_video(db, run_id)
    draft = get_narration_draft_for_run(db, run.id)
    if not draft:
        raise RuntimeError("Create a narration draft before regenerating it.")
    draft = _mark_draft_uncertain_if_needed(db, draft)
    provider = get_narration_writer_provider()
    if provider is None:
        raise RuntimeError("Narration writer provider is unavailable.")
    if provider.name != "mock" and not confirm_paid_draft:
        raise PaidNarrationConfirmationRequiredError(
            "Paid narration draft regeneration requires confirm_paid_draft=true."
        )
    draft.generation_revision += 1
    draft.status = NarrationDraftStatus.READY if draft.has_valid_content else NarrationDraftStatus.QUEUED
    draft.updated_at = now_utc()
    db.commit()
    _generate_draft_content(db, draft.id, confirm_paid_draft=confirm_paid_draft, regenerate=True)
    refreshed = db.get(NarrationDraft, draft.id) or draft
    return _mark_draft_uncertain_if_needed(db, refreshed)


def _generate_draft_content(db: Session, draft_id: str, *, confirm_paid_draft: bool, regenerate: bool) -> None:
    draft = db.get(NarrationDraft, draft_id)
    if not draft:
        raise RuntimeError("Narration draft not found.")
    run = db.get(PipelineRun, draft.pipeline_run_id)
    video = db.get(Video, draft.source_video_id)
    if not run or not video:
        raise RuntimeError("Narration draft source run or video is missing.")
    provider = get_narration_writer_provider()
    if provider is None:
        raise RuntimeError("Narration writer provider is unavailable.")
    if provider.name != "mock" and not confirm_paid_draft:
        raise PaidNarrationConfirmationRequiredError(
            "Paid narration draft generation requires confirm_paid_draft=true."
        )
    if not _claim_draft_for_generation(db, draft.id, draft.generation_revision, task_id=f"request-{uuid.uuid4()}"):
        return
    draft = db.get(NarrationDraft, draft.id) or draft
    previous_script = sanitize_for_json(draft.script_json or {})
    previous_text = draft.full_spoken_text
    previous_count = draft.estimated_word_count
    previous_usage = sanitize_for_json(draft.usage_metadata_json or {})
    previous_cost = draft.estimated_writer_cost
    try:
        payload = _build_writer_payload(db, run, video)
        prompt_text = json.dumps(payload)
        draft.provider_attempt_id = f"draft-{uuid.uuid4()}"
        draft.paid_call_started_at = now_utc()
        draft.paid_call_completed_at = None
        draft.provider_request_id = None
        draft.paid_call_outcome_uncertain = False
        draft.failure_reason = None
        draft.failure_stage = "writer"
        db.commit()

        response = provider.write(payload)
        draft = db.get(NarrationDraft, draft.id) or draft
        draft.provider_request_id = response.get("provider_request_id")
        draft.paid_call_completed_at = now_utc()
        db.commit()

        draft.usage_metadata_json = _draft_attempt_metadata(response)
        draft.estimated_writer_cost = _cost_metadata(response)[0]
        db.commit()

        segments, full_spoken_text, word_count = _normalize_segments(
            response,
            source_duration_seconds=draft.source_duration_seconds,
        )
        _validate_draft_against_duration(draft.source_duration_seconds, segments)
        _write_draft_content(
            draft,
            segments=segments,
            full_spoken_text=full_spoken_text,
            word_count=word_count,
            usage_metadata=draft.usage_metadata_json,
            cost_estimate=draft.estimated_writer_cost,
        )
        draft.writer_completed_at = now_utc()
        draft.status = NarrationDraftStatus.READY
        _append_draft_attempt_history(
            draft,
            usage_metadata=draft.usage_metadata_json,
            validation_result="ready",
        )
        add_prompt_log(
            db,
            run_id=run.id,
            stage="narration_writer",
            provider=provider.name,
            model=provider.model,
            prompt_text=prompt_text,
            request_json=payload,
            response_json=response,
            output_text=full_spoken_text,
            token_usage_json=response.get("usage", {}),
            cost_estimate=float(draft.estimated_writer_cost or 0.0),
        )
        if draft.estimated_writer_cost is not None:
            add_cost(
                db,
                run_id=run.id,
                provider=provider.name,
                model=provider.model,
                stage="narration_writer",
                estimated_cost=draft.estimated_writer_cost,
            )
        add_event(
            db,
            run.id,
            "narration.draft_ready",
            "Narration draft generated",
            metadata={"generation_revision": draft.generation_revision, "regenerated": regenerate},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        draft = db.get(NarrationDraft, draft_id)
        if draft is None:
            raise
        if draft.paid_call_completed_at:
            response = locals().get("response")
            if isinstance(response, dict):
                draft.usage_metadata_json = _draft_attempt_metadata(response, validation_error=str(exc))
                draft.estimated_writer_cost = _cost_metadata(response)[0]
        if draft.has_valid_content:
            draft.status = NarrationDraftStatus.READY
        else:
            draft.status = NarrationDraftStatus.UNAVAILABLE if draft.paid_call_outcome_uncertain else NarrationDraftStatus.FAILED
        draft.failure_reason = str(exc)
        draft.failure_stage = "writer"
        validation_result = "uncertain" if draft.paid_call_outcome_uncertain else "failed_validation"
        _append_draft_attempt_history(
            draft,
            usage_metadata=draft.usage_metadata_json,
            validation_result=validation_result,
        )
        if draft.has_valid_content:
            last_attempt = sanitize_for_json(draft.usage_metadata_json or {})
            draft.script_json = previous_script
            draft.full_spoken_text = previous_text
            draft.estimated_word_count = previous_count
            merged_usage = previous_usage if isinstance(previous_usage, dict) else {}
            if last_attempt:
                merged_usage = {**merged_usage, "last_attempt": last_attempt}
            draft.usage_metadata_json = sanitize_for_json(merged_usage)
            draft.estimated_writer_cost = previous_cost
        add_event(
            db,
            run.id,
            "narration.draft_failed",
            f"Narration draft generation failed: {exc}",
            metadata={"generation_revision": draft.generation_revision, "regenerated": regenerate},
        )
        db.commit()


def patch_narration_draft(db: Session, run_id: str, payload: dict[str, Any]) -> NarrationDraft:
    _assert_narration_enabled()
    run, _video, _asset = _require_completed_video(db, run_id)
    draft = get_narration_draft_for_run(db, run.id)
    if not draft or not draft.has_valid_content:
        raise RuntimeError("No usable narration draft exists for editing.")
    draft = _mark_draft_uncertain_if_needed(db, draft)
    if not draft.has_valid_content:
        raise RuntimeError("No usable narration draft exists for editing.")
    segments, full_spoken_text, word_count = _normalize_segments(payload)
    _validate_draft_against_duration(draft.source_duration_seconds, segments)
    draft.script_json = {"segments": segments}
    draft.full_spoken_text = full_spoken_text
    draft.estimated_word_count = word_count
    draft.manually_modified = True
    draft.status = NarrationDraftStatus.READY
    draft.failure_reason = None
    draft.failure_stage = None
    db.commit()
    add_event(db, run.id, "narration.draft_updated", "Narration draft manually updated")
    db.commit()
    return db.get(NarrationDraft, draft.id) or draft


def _render_idempotency_key(draft: NarrationDraft, voice: str) -> str:
    settings = get_settings()
    payload = "|".join(
        [
            draft.source_video_id,
            draft.narration_version,
            draft.full_spoken_text,
            voice,
            settings.narration_speech_model,
            settings.narration_caption_version,
            settings.narration_render_version,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_narration_render(
    db: Session,
    run_id: str,
    *,
    confirm_paid_narration: bool,
    confirm_unapproved_story: bool = False,
    voice: str | None = None,
) -> NarrationRender:
    _assert_narration_enabled()
    run, video, _asset = _require_completed_video(db, run_id)
    draft = get_narration_draft_for_run(db, run.id)
    if not draft or not draft.has_valid_content:
        raise RuntimeError("Create a usable narration draft before rendering.")
    draft = _mark_draft_uncertain_if_needed(db, draft)
    if draft.paid_call_outcome_uncertain:
        raise RuntimeError("The last paid narration draft call has an uncertain outcome. Review it manually before retrying.")
    if not confirm_paid_narration:
        raise PaidNarrationConfirmationRequiredError(
            "Narrated rendering requires confirm_paid_narration=true."
        )
    story_status, story_source = get_story_approval_snapshot(db, run, video)
    if story_status != "approved" and not confirm_unapproved_story:
        raise PaidNarrationConfirmationRequiredError(
            "This story is not approved yet. Re-submit with confirm_unapproved_story=true to continue."
        )
    provider = get_speech_provider()
    if provider is None:
        raise RuntimeError("Narration speech provider is unavailable.")
    selected_voice = voice or get_settings().narration_voice
    idempotency_key = _render_idempotency_key(draft, selected_voice)
    existing = db.query(NarrationRender).filter(NarrationRender.idempotency_key == idempotency_key).first()
    if existing:
        return _mark_render_uncertain_if_needed(db, existing)
    render = NarrationRender(
        pipeline_run_id=run.id,
        narration_draft_id=draft.id,
        source_video_id=video.id,
        narration_version=draft.narration_version,
        status=NarrationRenderStatus.QUEUED,
        writer_provider=draft.writer_provider,
        writer_model=draft.writer_model,
        writer_prompt_version=draft.writer_prompt_version,
        speech_provider=provider.name,
        speech_model=provider.model,
        voice=selected_voice,
        voice_is_ai_generated=True,
        caption_version=get_settings().narration_caption_version,
        render_version=get_settings().narration_render_version,
        script_json=sanitize_for_json(draft.script_json or {}),
        full_spoken_text=draft.full_spoken_text,
        caption_cues_json=[],
        caption_source_json={},
        source_duration_seconds=draft.source_duration_seconds,
        idempotency_key=idempotency_key,
        usage_metadata_json={},
        estimated_writer_cost=draft.estimated_writer_cost,
        estimated_speech_cost=None,
        provider_request_dispatched=False,
        speech_attempts_json=[],
        story_approval_status_snapshot=story_status,
        story_approval_source_snapshot=story_source,
        ai_voice_disclosure=AI_VOICE_DISCLOSURE,
    )
    db.add(render)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(NarrationRender).filter(NarrationRender.idempotency_key == idempotency_key).first()
        if existing:
            return _mark_render_uncertain_if_needed(db, existing)
        raise
    db.refresh(render)
    add_event(db, run.id, "narration.render_queued", "Narrated render queued", metadata={"render_id": render.id})
    db.commit()
    enqueue_narration_render_task(render.id)
    return db.get(NarrationRender, render.id) or render


def _audio_extension_for_mime(mime_type: str) -> str:
    if mime_type == "audio/mpeg":
        return ".mp3"
    if mime_type == "audio/wav":
        return ".wav"
    return ".bin"


def _storage_key(render_id: str, asset_type: str, extension: str) -> str:
    return f"narration/{render_id}/{asset_type}{extension}"


def _download_asset(asset: Asset, destination: Path) -> None:
    response = httpx.get(asset.public_url, follow_redirects=True, timeout=60.0)
    response.raise_for_status()
    destination.write_bytes(response.content)


def _resolve_local_or_download(asset: Asset) -> tuple[Path, bool]:
    storage = get_storage_provider()
    if storage.name == "local" and asset.storage_key:
        local_path = Path(storage.resolve_path(asset.storage_key))
        if local_path.exists():
            return local_path, False
    temp_dir = Path(tempfile.mkdtemp(prefix="story-engine-narration-source-"))
    target = temp_dir / f"{asset.id}"
    _download_asset(asset, target)
    return target, True


def _probe_media(file_path: Path, stream_selector: str) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        stream_selector,
        "-show_entries",
        "stream=width,height:format=duration,size",
        "-of",
        "json",
        str(file_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    stream = (payload.get("streams") or [{}])[0]
    file_format = payload.get("format", {})
    return {
        "width": int(stream.get("width", 0) or 0),
        "height": int(stream.get("height", 0) or 0),
        "duration_seconds": max(float(file_format.get("duration", 0) or 0), 0.0),
        "size_bytes": int(float(file_format.get("size", 0) or 0)),
    }


def _probe_media_details(file_path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,codec_name,width,height,avg_frame_rate,duration",
        "-of",
        "json",
        str(file_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    return {
        "format_duration_seconds": max(float((payload.get("format") or {}).get("duration", 0) or 0), 0.0),
        "streams": sanitize_for_json(streams),
    }


def _escape_ass_text(text: str) -> str:
    safe = text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
    safe = safe.replace("\r\n", "\n").replace("\r", "\n").replace("\n", r"\N")
    return safe


def _split_caption_lines(text: str) -> str:
    words = text.split()
    if len(words) < 7:
        return _escape_ass_text(text)
    midpoint = math.ceil(len(words) / 2)
    return _escape_ass_text(" ".join(words[:midpoint]) + "\n" + " ".join(words[midpoint:]))


def _format_ass_time(seconds: float) -> str:
    total = max(seconds, 0.0)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = total % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _derive_caption_cues(render: NarrationRender, audio_duration_seconds: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    segments = []
    raw_segments = (render.script_json or {}).get("segments", [])
    for item in raw_segments:
        if isinstance(item, dict):
            segments.append(dict(item))
    if not segments:
        raise RuntimeError("Narration render is missing draft segments.")
    source_duration = max(float(render.source_duration_seconds or 10.0), 1.0)
    window_plan = _narration_window_plan(source_duration, audio_duration_seconds)
    speech_window_start = window_plan["speech_window_start_seconds"]
    speech_window_end = window_plan["speech_window_end_seconds"]
    speech_window_duration = round(max(speech_window_end - speech_window_start, 0.1), 2)
    weights = [max(len(str(item.get("spoken_text") or item.get("caption_text") or "").split()), 1) for item in segments]
    total_weight = sum(weights)
    current = speech_window_start
    cues: list[dict[str, Any]] = []
    for index, item in enumerate(segments):
        weight = weights[index] / total_weight
        duration = speech_window_duration * weight
        end = current + duration
        if index == len(segments) - 1:
            end = speech_window_end
        cues.append(
            {
                "start_seconds": round(current, 2),
                "end_seconds": round(end, 2),
                "caption_text": str(item.get("caption_text") or item.get("spoken_text") or "").strip(),
                "spoken_text": str(item.get("spoken_text") or "").strip(),
            }
        )
        current = end
    last_end = 0.0
    for cue in cues:
        if cue["start_seconds"] < last_end or cue["end_seconds"] <= cue["start_seconds"]:
            raise RuntimeError("Derived caption cues overlap or are invalid.")
        last_end = cue["end_seconds"]
    return cues, {
        "audio_duration_seconds": round(audio_duration_seconds, 2),
        "lead_in_seconds": window_plan["lead_in_seconds"],
        "speech_window_start_seconds": window_plan["speech_window_start_seconds"],
        "speech_window_end_seconds": window_plan["speech_window_end_seconds"],
        "ending_silence_seconds": window_plan["ending_silence_seconds"],
        "available_speech_window_seconds": window_plan["available_speech_window_seconds"],
        "allocation": "word_count_weighted",
    }


def _write_ass_file(destination: Path, cues: list[dict[str, Any]]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    header = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 720",
            "PlayResY: 1280",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Default,DejaVu Sans,54,&H00FFFFFF,&H00FFFFFF,&H00111111,&H66000000,0,0,0,0,100,100,0,0,1,3,0,2,80,80,180,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )
    lines = [header]
    for cue in cues:
        lines.append(
            "Dialogue: 0,{start},{end},Default,,0,0,0,,{text}".format(
                start=_format_ass_time(float(cue["start_seconds"])),
                end=_format_ass_time(float(cue["end_seconds"])),
                text=_split_caption_lines(str(cue["caption_text"])),
            )
        )
    destination.write_text("\n".join(lines), encoding="utf-8")


def _compose_video(
    source_video: Path,
    audio_file: Path,
    caption_file: Path,
    destination: Path,
    *,
    atempo: float | None,
    lead_in_seconds: float,
    source_duration_seconds: float,
) -> None:
    audio_filters = []
    if atempo and abs(atempo - 1.0) > 0.001:
        audio_filters.append(f"atempo={atempo:.4f}")
    lead_in_ms = int(round(max(lead_in_seconds, 0.0) * 1000))
    audio_filters.extend(
        [
            f"adelay={lead_in_ms}:all=1",
            f"apad=pad_dur={source_duration_seconds:.2f}",
            f"atrim=duration={source_duration_seconds:.2f}",
        ]
    )
    caption_filter_path = str(caption_file).replace("\\", "/").replace(":", "\\:")
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_video),
        "-i",
        str(audio_file),
        "-filter_complex",
        f"[1:a]{','.join(audio_filters)}[narration]",
        "-map",
        "0:v:0",
        "-map",
        "[narration]",
        "-vf",
        f"subtitles='{caption_filter_path}'",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-t",
        f"{source_duration_seconds:.2f}",
        str(destination),
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _validate_render_output(
    output_details: dict[str, Any],
    *,
    source_duration_seconds: float,
    expected_width: int,
    expected_height: int,
    caption_cues: list[dict[str, Any]],
    narration_end_seconds: float,
) -> None:
    streams = output_details.get("streams") or []
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(video_streams) != 1 or len(audio_streams) != 1:
        raise RuntimeError("Narrated output must contain exactly one video stream and one audio stream.")
    format_duration = float(output_details.get("format_duration_seconds") or 0.0)
    if abs(format_duration - float(source_duration_seconds)) > 0.1:
        raise RuntimeError("Narrated output duration does not match the source video duration.")
    video_stream = video_streams[0]
    if int(video_stream.get("width") or 0) != expected_width or int(video_stream.get("height") or 0) != expected_height:
        raise RuntimeError("Narrated output dimensions do not match the source video.")
    if caption_cues:
        final_caption_end = max(float(cue.get("end_seconds") or 0.0) for cue in caption_cues)
        if final_caption_end > format_duration + 0.01:
            raise RuntimeError("Narration captions extend beyond the final video duration.")
        if final_caption_end - float(narration_end_seconds) > 0.1:
            raise RuntimeError("Narration captions materially exceed the narration audio window.")


def _save_asset(
    db: Session,
    *,
    run_id: str,
    source_path: Path,
    asset_type: str,
    storage_key: str,
    created_by_stage: str,
    mime_type: str,
    duration_seconds: float | None = None,
    width: int | None = None,
    height: int | None = None,
) -> Asset:
    storage = get_storage_provider()
    stored = storage.save_file(str(source_path), storage_key)
    asset = Asset(
        pipeline_run_id=run_id,
        asset_type=asset_type,
        created_by_stage=created_by_stage,
        storage_key=stored["storage_key"],
        public_url=stored["public_url"],
        mime_type=mime_type,
        size_bytes=stored["size_bytes"],
        duration_seconds=int(round(duration_seconds)) if duration_seconds is not None else None,
        width=width,
        height=height,
    )
    db.add(asset)
    db.flush()
    return asset


def _claim_render_status(db: Session, render_id: str, expected: NarrationRenderStatus, target: NarrationRenderStatus, task_id: str | None = None) -> bool:
    rows = (
        db.query(NarrationRender)
        .filter(NarrationRender.id == render_id, NarrationRender.status == expected)
        .update(
            {
                NarrationRender.status: target,
                NarrationRender.worker_task_id: task_id,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return rows == 1


def _render_speech_metadata(response: dict[str, Any]) -> dict[str, Any]:
    estimated_cost, cost_estimation_status = _cost_metadata(response)
    return sanitize_for_json(
        {
            "usage": sanitize_for_json(response.get("usage", {})),
            "cost_estimate": estimated_cost,
            "cost_estimation_status": cost_estimation_status,
            "response_format": response.get("response_format") or "mp3",
        }
    )


def _speech_attempt_record(
    render: NarrationRender,
    *,
    usage_metadata: dict[str, Any] | None = None,
    attempt_result: str,
) -> dict[str, Any]:
    metadata = sanitize_for_json(usage_metadata or (render.usage_metadata_json or {}).get("speech", {}))
    current_attempts = render.speech_attempts_json if isinstance(render.speech_attempts_json, list) else []
    attempt_revision = len(current_attempts) + 1
    for item in current_attempts:
        if isinstance(item, dict) and item.get("provider_attempt_id") == render.provider_attempt_id and render.provider_attempt_id:
            attempt_revision = int(item.get("attempt_revision") or attempt_revision)
            break
    return sanitize_for_json(
        {
            "attempt_revision": attempt_revision,
            "provider_attempt_id": render.provider_attempt_id,
            "provider_request_id": render.provider_request_id,
            "provider_request_dispatched": bool(render.provider_request_dispatched),
            "started_at": render.paid_call_started_at.isoformat() if render.paid_call_started_at else None,
            "completed_at": render.paid_call_completed_at.isoformat() if render.paid_call_completed_at else None,
            "speech_provider": render.speech_provider,
            "speech_model": render.speech_model,
            "voice": render.voice,
            "response_format": metadata.get("response_format", "mp3"),
            "usage_metadata": metadata,
            "estimated_cost": render.estimated_speech_cost,
            "audio_asset_id": render.audio_asset_id,
            "failure_reason": render.failure_reason,
            "failure_stage": render.failure_stage,
            "failure_kind": render.failure_kind,
            "uncertain_outcome": bool(render.paid_call_outcome_uncertain),
            "attempt_result": attempt_result,
        }
    )


def _append_speech_attempt_history(
    render: NarrationRender,
    *,
    usage_metadata: dict[str, Any] | None = None,
    attempt_result: str,
) -> None:
    current_attempts = render.speech_attempts_json if isinstance(render.speech_attempts_json, list) else []
    attempt_record = _speech_attempt_record(render, usage_metadata=usage_metadata, attempt_result=attempt_result)
    provider_attempt_id = attempt_record.get("provider_attempt_id")
    filtered = [
        item
        for item in current_attempts
        if not (
            isinstance(item, dict)
            and provider_attempt_id
            and item.get("provider_attempt_id") == provider_attempt_id
        )
    ]
    filtered.append(attempt_record)
    render.speech_attempts_json = sanitize_for_json(filtered)


def _queue_speech_retry(db: Session, render_id: str) -> bool:
    rows = (
        db.query(NarrationRender)
        .filter(
            NarrationRender.id == render_id,
            NarrationRender.audio_asset_id.is_(None),
            NarrationRender.status.in_([NarrationRenderStatus.FAILED, NarrationRenderStatus.UNAVAILABLE]),
        )
        .update(
            {
                NarrationRender.status: NarrationRenderStatus.QUEUED,
                NarrationRender.worker_task_id: None,
                NarrationRender.failure_reason: None,
                NarrationRender.failure_stage: None,
                NarrationRender.failure_kind: None,
                NarrationRender.provider_request_dispatched: False,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return rows == 1


def enqueue_narration_render_task(render_id: str) -> None:
    provider = get_speech_provider()
    if provider is not None and provider.name == "mock":
        db = SessionLocal()
        try:
            process_narration_render(db, render_id, mode="full", task_id="inline-mock-render")
        finally:
            db.close()
        return
    from app.workers.jobs import narration_render_task

    narration_render_task.delay(render_id)


def enqueue_narration_recompose_task(render_id: str) -> None:
    provider = get_speech_provider()
    if provider is not None and provider.name == "mock":
        db = SessionLocal()
        try:
            process_narration_render(db, render_id, mode="recompose", task_id="inline-mock-recompose")
        finally:
            db.close()
        return
    from app.workers.jobs import narration_recompose_task

    narration_recompose_task.delay(render_id)


def retry_narration_speech(
    db: Session,
    run_id: str,
    render_id: str,
    *,
    confirm_paid_narration: bool,
    confirm_possible_duplicate_charge: bool = False,
) -> NarrationRender:
    _assert_narration_enabled()
    run, _video, _asset = _require_completed_video(db, run_id)
    render = db.get(NarrationRender, render_id)
    if not render or render.pipeline_run_id != run.id:
        raise RuntimeError("Narration render not found.")
    if not confirm_paid_narration:
        raise PaidNarrationConfirmationRequiredError("Speech retry requires confirm_paid_narration=true.")
    if render.audio_asset_id:
        raise RuntimeError("Speech retry is unavailable once an audio asset exists. Recompose the existing render instead.")
    if render.paid_call_outcome_uncertain and not confirm_possible_duplicate_charge:
        raise PaidNarrationConfirmationRequiredError(
            "Speech retry may duplicate a previous paid call. Re-submit with confirm_possible_duplicate_charge=true."
        )
    if render.status == NarrationRenderStatus.QUEUED:
        return render
    if render.status not in {NarrationRenderStatus.FAILED, NarrationRenderStatus.UNAVAILABLE}:
        raise RuntimeError("Speech retry is only available for failed or unavailable renders without audio.")
    if not _queue_speech_retry(db, render.id):
        return db.get(NarrationRender, render.id) or render
    queued = db.get(NarrationRender, render.id) or render
    add_event(db, run.id, "narration.speech_retry_queued", "Narration speech retry queued", metadata={"render_id": queued.id})
    db.commit()
    enqueue_narration_render_task(queued.id)
    return db.get(NarrationRender, queued.id) or queued


def process_narration_render(db: Session, render_id: str, *, mode: str = "full", task_id: str | None = None) -> NarrationRender | None:
    render = db.get(NarrationRender, render_id)
    if not render:
        return None
    render = _mark_render_uncertain_if_needed(db, render)
    if render.paid_call_outcome_uncertain and not render.audio_asset_id:
        return render
    run = db.get(PipelineRun, render.pipeline_run_id)
    if not run:
        return render
    source_asset = get_video_asset(db, run.id)
    if not source_asset:
        render.status = NarrationRenderStatus.FAILED
        render.failure_reason = "Source video asset is missing."
        render.failure_stage = "asset_upload"
        db.commit()
        return render

    temp_dir = Path(tempfile.mkdtemp(prefix="story-engine-narration-render-"))
    source_path: Path | None = None
    delete_source = False
    audio_path: Path | None = None
    delete_audio = False
    stored_output_path: Path | None = None
    delete_stored_output = False
    try:
        if render.audio_asset_id:
            audio_asset = db.get(Asset, render.audio_asset_id)
        else:
            audio_asset = None
        if mode == "full" and audio_asset is None:
            if not _claim_render_status(db, render.id, NarrationRenderStatus.QUEUED, NarrationRenderStatus.SPEECH_GENERATING, task_id):
                refreshed = db.get(NarrationRender, render.id)
                if refreshed and refreshed.audio_asset_id:
                    audio_asset = db.get(Asset, refreshed.audio_asset_id)
                    render = refreshed
                else:
                    return refreshed
            render = db.get(NarrationRender, render.id) or render
            provider = get_speech_provider()
            if provider is None:
                raise RuntimeError("Narration speech provider is unavailable.")
            render.speech_started_at = now_utc()
            render.provider_attempt_id = f"speech-{uuid.uuid4()}"
            render.paid_call_started_at = now_utc()
            render.paid_call_completed_at = None
            render.provider_request_id = None
            render.provider_request_dispatched = False
            render.paid_call_outcome_uncertain = False
            render.failure_stage = "speech"
            render.failure_reason = None
            render.failure_kind = None
            db.commit()
            audio_path = temp_dir / f"speech{_audio_extension_for_mime('audio/wav' if provider.name == 'mock' else 'audio/mpeg')}"
            response = provider.synthesize(text=render.full_spoken_text, voice=render.voice, destination=audio_path)
            render = db.get(NarrationRender, render.id) or render
            render.provider_request_dispatched = True
            render.provider_request_id = response.get("provider_request_id")
            render.paid_call_completed_at = now_utc()
            db.commit()
            try:
                audio_asset = _save_asset(
                    db,
                    run_id=render.pipeline_run_id,
                    source_path=Path(response["source_path"]),
                    asset_type="narration_audio",
                    storage_key=_storage_key(render.id, "audio", _audio_extension_for_mime(response["mime_type"])),
                    created_by_stage="narration_speech",
                    mime_type=response["mime_type"],
                    duration_seconds=float(response.get("duration_seconds") or 0.0),
                )
                render.audio_asset_id = audio_asset.id
                render.speech_completed_at = now_utc()
                render.status = NarrationRenderStatus.SPEECH_READY
                speech_metadata = _render_speech_metadata(response)
                render.usage_metadata_json = {
                    **(render.usage_metadata_json or {}),
                    "speech": speech_metadata,
                }
                render.estimated_speech_cost = _cost_metadata(response)[0]
                render.failure_reason = None
                render.failure_stage = None
                render.failure_kind = None
                _append_speech_attempt_history(
                    render,
                    usage_metadata=speech_metadata,
                    attempt_result="speech_ready",
                )
                if render.estimated_speech_cost is not None:
                    add_cost(
                        db,
                        run_id=render.pipeline_run_id,
                        provider=provider.name,
                        model=provider.model,
                        stage="narration_speech",
                        estimated_cost=render.estimated_speech_cost,
                    )
                db.commit()
                add_event(db, render.pipeline_run_id, "narration.speech_ready", "Narration audio generated", metadata={"render_id": render.id})
                db.commit()
            except Exception:
                db.rollback()
                render = db.get(NarrationRender, render.id) or render
                render.failure_stage = "audio_upload"
                render.failure_reason = "Narration audio upload failed."
                render.status = NarrationRenderStatus.FAILED
                _append_speech_attempt_history(render, attempt_result="failed")
                db.commit()
                return render
        render = db.get(NarrationRender, render.id) or render
        if render.audio_asset_id is None:
            return render
        if render.status != NarrationRenderStatus.COMPOSING:
            expected = render.status
            if mode != "recompose" and render.status == NarrationRenderStatus.PENDING_REVIEW and render.rendered_video_asset_id:
                return render
            if not _claim_render_status(db, render.id, expected, NarrationRenderStatus.COMPOSING, task_id):
                refreshed = db.get(NarrationRender, render.id)
                if refreshed and refreshed.rendered_video_asset_id and mode != "recompose":
                    return refreshed
                if refreshed and refreshed.status == NarrationRenderStatus.COMPOSING:
                    return refreshed
            render = db.get(NarrationRender, render.id) or render
        audio_asset = db.get(Asset, render.audio_asset_id)
        if not audio_asset:
            raise RuntimeError("Narration audio asset is missing.")
        source_path, delete_source = _resolve_local_or_download(source_asset)
        audio_path, delete_audio = _resolve_local_or_download(audio_asset)
        try:
            audio_meta = _probe_media(audio_path, "a:0")
            source_meta = _probe_media(source_path, "v:0")
            render.original_audio_duration_seconds = round(audio_meta["duration_seconds"], 2)
            source_duration = float(render.source_duration_seconds or source_meta["duration_seconds"])
            window_plan = _narration_window_plan(source_duration)
            narration_window = window_plan["available_speech_window_seconds"]
            render.usable_narration_window_seconds = round(narration_window, 2)
            atempo_factor = 1.0
            final_audio_duration = audio_meta["duration_seconds"]
            if final_audio_duration > narration_window:
                required_factor = final_audio_duration / narration_window
                max_adjust = 1 + (get_settings().narration_max_atempo_adjustment_percent / 100.0)
                if required_factor > max_adjust:
                    render.status = NarrationRenderStatus.NEEDS_REVISION
                    render.failure_reason = "Narration audio does not fit the available window without an excessive speed change."
                    render.failure_stage = "speech"
                    db.commit()
                    return render
                atempo_factor = required_factor
                final_audio_duration = narration_window
            render.applied_atempo_factor = round(atempo_factor, 4)
            render.final_audio_duration_seconds = round(final_audio_duration, 2)
            render.narration_duration_seconds = round(final_audio_duration, 2)
            render.failure_stage = "caption_generation"
            cues, cue_source = _derive_caption_cues(render, final_audio_duration)
            render.caption_cues_json = sanitize_for_json(cues)
            render.caption_source_json = sanitize_for_json(cue_source)
            caption_path = temp_dir / "captions.ass"
            _write_ass_file(caption_path, cues)
            caption_asset = _save_asset(
                db,
                run_id=render.pipeline_run_id,
                source_path=caption_path,
                asset_type="narration_captions",
                storage_key=_storage_key(render.id, "captions", ".ass"),
                created_by_stage="narration_caption_generation",
                mime_type="text/x-ass",
            )
            render.caption_asset_id = caption_asset.id
            output_path = temp_dir / "narrated.mp4"
            render.failure_stage = "composition"
            _compose_video(
                source_path,
                audio_path,
                caption_path,
                output_path,
                atempo=render.applied_atempo_factor,
                lead_in_seconds=window_plan["lead_in_seconds"],
                source_duration_seconds=source_duration,
            )
            output_meta = _probe_media(output_path, "v:0")
            render.failure_stage = "asset_upload"
            rendered_asset = _save_asset(
                db,
                run_id=render.pipeline_run_id,
                source_path=output_path,
                asset_type="narrated_video_mp4",
                storage_key=_storage_key(render.id, "video", ".mp4"),
                created_by_stage="narration_composition",
                mime_type="video/mp4",
                duration_seconds=output_meta["duration_seconds"],
                width=output_meta["width"],
                height=output_meta["height"],
            )
            render.rendered_video_asset_id = rendered_asset.id
            stored_output_path, delete_stored_output = _resolve_local_or_download(rendered_asset)
            render.failure_stage = "output_validation"
            output_details = _probe_media_details(stored_output_path)
            _validate_render_output(
                output_details,
                source_duration_seconds=source_duration,
                expected_width=source_meta["width"],
                expected_height=source_meta["height"],
                caption_cues=render.caption_cues_json if isinstance(render.caption_cues_json, list) else [],
                narration_end_seconds=render.caption_source_json.get("speech_window_end_seconds", window_plan["speech_window_end_seconds"]),
            )
            render.status = NarrationRenderStatus.PENDING_REVIEW
            render.failure_reason = None
            render.failure_stage = None
            db.commit()
            add_event(db, render.pipeline_run_id, "narration.render_ready", "Narrated video is ready for review", metadata={"render_id": render.id})
            db.commit()
        finally:
            if stored_output_path is not None and delete_stored_output:
                for file_path in stored_output_path.parent.glob("*"):
                    file_path.unlink(missing_ok=True)
                stored_output_path.parent.rmdir()
            if audio_path is not None and delete_audio:
                for file_path in audio_path.parent.glob("*"):
                    file_path.unlink(missing_ok=True)
                audio_path.parent.rmdir()
    except Exception as exc:
        db.rollback()
        render = db.get(NarrationRender, render.id) or render
        if render.status != NarrationRenderStatus.NEEDS_REVISION:
            render.status = NarrationRenderStatus.FAILED
        render.failure_reason = str(exc)
        if render.failure_stage == "speech" and "unexpected keyword argument" in str(exc):
            render.failure_kind = "client_configuration"
            render.provider_request_dispatched = False
        if render.failure_stage not in FAILURE_STAGES:
            render.failure_stage = "composition"
        if render.failure_stage == "speech":
            _append_speech_attempt_history(render, attempt_result="failed")
        db.commit()
    finally:
        if source_path is not None and delete_source:
            for file_path in source_path.parent.glob("*"):
                file_path.unlink(missing_ok=True)
            source_path.parent.rmdir()
        for file_path in temp_dir.glob("*"):
            file_path.unlink(missing_ok=True)
        temp_dir.rmdir()
    return db.get(NarrationRender, render.id) or render


def recompose_narration_render(db: Session, run_id: str, render_id: str) -> NarrationRender:
    _assert_narration_enabled()
    run, _video, _asset = _require_completed_video(db, run_id)
    render = db.get(NarrationRender, render_id)
    if not render or render.pipeline_run_id != run.id:
        raise RuntimeError("Narration render not found.")
    if not render.audio_asset_id:
        raise RuntimeError("Narration recompose requires an existing audio asset.")
    enqueue_narration_recompose_task(render.id)
    return db.get(NarrationRender, render.id) or render


def record_narration_human_review(
    db: Session,
    run_id: str,
    render_id: str,
    decision: str,
    notes: str | None,
) -> NarrationRender:
    run, _video, _asset = _require_completed_video(db, run_id)
    render = db.get(NarrationRender, render_id)
    if not render or render.pipeline_run_id != run.id:
        raise RuntimeError("Narration render not found.")
    render.human_review_status = decision
    render.human_review_notes = notes
    render.human_reviewed_at = now_utc()
    if decision == "approve":
        render.status = NarrationRenderStatus.APPROVED
    elif decision == "needs_revision":
        render.status = NarrationRenderStatus.NEEDS_REVISION
    elif decision == "reject":
        render.status = NarrationRenderStatus.REJECTED
    add_event(db, run.id, "narration.human_reviewed", "Narrated render reviewed by a human", metadata={"render_id": render.id, "decision": decision})
    db.commit()
    return db.get(NarrationRender, render.id) or render


def build_narration_payloads(db: Session, run: PipelineRun) -> dict[str, Any]:
    draft = get_narration_draft_for_run(db, run.id)
    if draft:
        draft = _mark_draft_uncertain_if_needed(db, draft)
    renders = (
        db.query(NarrationRender)
        .filter(NarrationRender.pipeline_run_id == run.id)
        .order_by(NarrationRender.created_at.desc())
        .all()
    )
    normalized_renders = []
    for render in renders:
        normalized = _mark_render_uncertain_if_needed(db, render)
        payload = serialize_model(normalized) or {}
        payload["audio_asset"] = serialize_model(get_asset_by_id(db, normalized.audio_asset_id))
        payload["caption_asset"] = serialize_model(get_asset_by_id(db, normalized.caption_asset_id))
        payload["rendered_video_asset"] = serialize_model(get_asset_by_id(db, normalized.rendered_video_asset_id))
        normalized_renders.append(payload)
    draft_payload = serialize_model(draft) if draft else None
    latest_render = normalized_renders[0] if normalized_renders else None
    return {
        "narration_draft": draft_payload,
        "latest_narration_render": latest_render,
        "narration_renders": normalized_renders,
    }
