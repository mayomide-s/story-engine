from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Asset, QualityCheck, StoryAdherenceHumanReview, StoryAdherenceReview, Video
from app.services.providers import get_semantic_critic_provider, get_storage_provider
from app.services.security import sanitize_for_json

CRITERION_ORDER = [
    "initial_problem_shown",
    "intended_subject_present",
    "trigger_visible",
    "transformation_attempted",
    "transformation_completed",
    "required_final_state_visible",
    "ending_held_clearly",
    "unrelated_characters_or_actions",
    "unwanted_generated_text",
]

POSITIVE_CRITERIA = {
    "initial_problem_shown": 10,
    "intended_subject_present": 10,
    "trigger_visible": 10,
    "transformation_attempted": 15,
    "transformation_completed": 20,
    "required_final_state_visible": 20,
    "ending_held_clearly": 10,
}

NEGATIVE_CRITERIA = {
    "unrelated_characters_or_actions": 3,
    "unwanted_generated_text": 2,
}

TRUE_FALSE_UNCERTAIN = {"true", "false", "uncertain"}


def get_latest_story_adherence_review(
    db: Session,
    video_id: str | None,
    critic_version: str | None = None,
) -> StoryAdherenceReview | None:
    if not video_id:
        return None
    query = db.query(StoryAdherenceReview).filter(StoryAdherenceReview.video_id == video_id)
    if critic_version:
        query = query.filter(StoryAdherenceReview.critic_version == critic_version)
    return query.order_by(StoryAdherenceReview.created_at.desc()).first()


def get_human_story_adherence_review(db: Session, run_id: str) -> StoryAdherenceHumanReview | None:
    return (
        db.query(StoryAdherenceHumanReview)
        .filter(StoryAdherenceHumanReview.pipeline_run_id == run_id)
        .order_by(StoryAdherenceHumanReview.updated_at.desc())
        .first()
    )


def can_run_semantic_critic() -> tuple[bool, str | None]:
    settings = get_settings()
    if not settings.semantic_critic_enabled:
        return False, "Semantic critic is disabled in this environment."
    if settings.semantic_critic_provider == "openai" and not settings.openai_api_key:
        return False, "Semantic critic is enabled but OPENAI_API_KEY is missing."
    return True, None


def is_technically_reviewable(quality_check: QualityCheck | None, asset: Asset | None) -> bool:
    return bool(quality_check and quality_check.passed and asset and asset.public_url)


def _probe_media(file_path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height:format=duration,size",
        "-of",
        "json",
        str(file_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    stream = payload.get("streams", [{}])[0]
    file_format = payload.get("format", {})
    return {
        "width": int(stream.get("width", 0) or 0),
        "height": int(stream.get("height", 0) or 0),
        "duration_seconds": max(float(file_format.get("duration", 0) or 0), 0.0),
        "size_bytes": int(float(file_format.get("size", 0) or 0)),
    }


def _probe_image(file_path: Path) -> dict[str, int]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(file_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    stream = payload.get("streams", [{}])[0]
    return {
        "width": int(stream.get("width", 0) or 0),
        "height": int(stream.get("height", 0) or 0),
    }


def _download_video_to_temp(asset: Asset, destination: Path) -> None:
    response = httpx.get(asset.public_url, follow_redirects=True, timeout=60.0)
    response.raise_for_status()
    destination.write_bytes(response.content)


def resolve_video_source_path(asset: Asset) -> tuple[Path, bool]:
    storage = get_storage_provider()
    if storage.name == "local" and asset.storage_key:
        local_path = Path(storage.resolve_path(asset.storage_key))
        if local_path.exists():
            return local_path, False
    temp_dir = Path(tempfile.mkdtemp(prefix="story-engine-semantic-video-"))
    target = temp_dir / f"{asset.id}.mp4"
    _download_video_to_temp(asset, target)
    return target, True


def build_sample_timestamps(duration_seconds: float) -> tuple[list[float], str]:
    duration_seconds = max(duration_seconds, 0.5)
    if abs(duration_seconds - 10.0) <= 0.35:
        timestamps = [1.0, 4.0, 7.0, 8.3, 9.5]
        strategy = "fixed_10s"
    else:
        timestamps = [duration_seconds * ratio for ratio in (0.10, 0.40, 0.70, 0.83, 0.95)]
        strategy = "scaled_by_duration"
    max_timestamp = max(duration_seconds - 0.1, 0.0)
    clamped = [round(min(max(timestamp, 0.0), max_timestamp), 2) for timestamp in timestamps]
    return clamped, strategy


def _sha256_hex(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def _data_url(file_path: Path) -> str:
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def sample_story_frames(video_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    metadata = _probe_media(video_path)
    timestamps, strategy = build_sample_timestamps(metadata["duration_seconds"])
    temp_dir = Path(tempfile.mkdtemp(prefix="story-engine-semantic-frames-"))
    frames: list[dict[str, Any]] = []
    try:
        for index, timestamp in enumerate(timestamps, start=1):
            frame_path = temp_dir / f"frame-{index}.jpg"
            command = [
                "ffmpeg",
                "-y",
                "-ss",
                f"{timestamp:.2f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                str(frame_path),
            ]
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            frame_metadata = _probe_image(frame_path)
            frames.append(
                {
                    "timestamp_seconds": timestamp,
                    "frame_hash": _sha256_hex(frame_path),
                    "width": frame_metadata["width"],
                    "height": frame_metadata["height"],
                    "data_url": _data_url(frame_path),
                }
            )
    finally:
        for frame_file in temp_dir.glob("*"):
            frame_file.unlink(missing_ok=True)
        temp_dir.rmdir()
    sampled_frames = {
        "video_duration_seconds": round(metadata["duration_seconds"], 2),
        "sampling_strategy": strategy,
        "frames": [
            {
                "timestamp_seconds": frame["timestamp_seconds"],
                "frame_hash": frame["frame_hash"],
                "width": frame["width"],
                "height": frame["height"],
                "persisted_asset": None,
            }
            for frame in frames
        ],
    }
    return frames, sanitize_for_json(sampled_frames)


def _normalize_evidence(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("Semantic critic response is missing structured criterion evidence.")
    value = str(item.get("value", "")).lower()
    if value not in TRUE_FALSE_UNCERTAIN:
        raise ValueError(f"Invalid critic evidence value: {value}")
    evidence_frames = item.get("evidence_frames", [])
    if not isinstance(evidence_frames, list):
        evidence_frames = []
    return {
        "value": value,
        "confidence": round(float(item.get("confidence", 0.0) or 0.0), 2),
        "evidence_frames": [round(float(frame), 2) for frame in evidence_frames[:5]],
        "reason": str(item.get("reason", "")).strip(),
    }


def normalize_critic_observations(payload: dict[str, Any]) -> dict[str, Any]:
    criteria = payload.get("criteria")
    if not isinstance(criteria, dict):
        raise ValueError("Semantic critic response is missing criteria.")
    normalized = {key: _normalize_evidence(criteria.get(key)) for key in CRITERION_ORDER}
    return {
        "summary": str(payload.get("summary", "")).strip(),
        "issues": [str(item) for item in payload.get("issues", [])] if isinstance(payload.get("issues"), list) else [],
        "criteria": normalized,
    }


def _criterion_score(value: str, *, positive: bool) -> float:
    if positive:
        return 1.0 if value == "true" else 0.5 if value == "uncertain" else 0.0
    return 1.0 if value == "false" else 0.5 if value == "uncertain" else 0.0


def compute_story_adherence_verdict(observations: dict[str, Any]) -> tuple[float, str, str]:
    criteria = observations["criteria"]
    weighted_total = 0.0
    possible_total = float(sum(POSITIVE_CRITERIA.values()) + sum(NEGATIVE_CRITERIA.values()))

    for criterion, weight in POSITIVE_CRITERIA.items():
        weighted_total += weight * _criterion_score(criteria[criterion]["value"], positive=True)
    for criterion, weight in NEGATIVE_CRITERIA.items():
        weighted_total += weight * _criterion_score(criteria[criterion]["value"], positive=False)

    score = round((weighted_total / possible_total) * 100, 1)
    final_state = criteria["required_final_state_visible"]["value"]
    transformation_completed = criteria["transformation_completed"]["value"]
    transformation_attempted = criteria["transformation_attempted"]["value"]
    hold = criteria["ending_held_clearly"]["value"]
    subject = criteria["intended_subject_present"]["value"]
    unrelated = criteria["unrelated_characters_or_actions"]["value"]
    unwanted_text = criteria["unwanted_generated_text"]["value"]

    if final_state == "false" or transformation_completed == "false" or transformation_attempted == "false":
        return score, "regenerate", "The required transformation did not visibly complete in the sampled frames."
    if subject == "false":
        return score, "needs_review", "The intended subject is not clearly visible in the sampled frames."
    if final_state == "uncertain" or hold in {"false", "uncertain"}:
        return score, "needs_review", "The final state is present but the ending hold is not clearly proven by the sampled frames."
    if unrelated == "true" or unwanted_text == "true":
        return score, "needs_review", "The generated result includes unrelated elements that weaken story adherence."
    if any(criteria[name]["value"] == "uncertain" for name in POSITIVE_CRITERIA):
        return score, "needs_review", "Core story beats are partially supported, but some evidence remains uncertain."
    return score, "accept", "All core story requirements are visibly supported in the sampled frames."


def build_critic_prompt(contract: dict[str, Any], topic: str, prompt_text: str, video: Video, sampled_frames: dict[str, Any]) -> str:
    frame_times = ", ".join(f"{frame['timestamp_seconds']}s" for frame in sampled_frames.get("frames", []))
    prohibited_actions = contract.get("prohibited_actions", [])
    return (
        "You are reviewing sampled video frames for story adherence, not full-video understanding. "
        "Judge only what is visibly supported by the provided frames. Do not assume unseen actions occurred between frames. "
        f"Topic: {topic}. "
        f"Contract subject: {contract.get('subject', '')}. "
        f"Initial problem: {contract.get('initial_state', '')}. "
        f"Trigger: {contract.get('trigger', '')}. "
        f"Required transformation: {contract.get('required_transformation', '')}. "
        f"Required final state: {contract.get('required_final_state', '')}. "
        f"Final hold requirement: {contract.get('final_state_hold', '')}. "
        f"Prohibited actions: {', '.join(str(item) for item in prohibited_actions)}. "
        f"Video provider/model context: provider={video.provider}, duration={video.duration_seconds}s, aspect_ratio={video.aspect_ratio}. "
        f"Sampled frames are at: {frame_times}. "
        f"Generation prompt: {prompt_text}"
    )


def run_semantic_critic(
    db: Session,
    *,
    pipeline_run_id: str,
    topic: str,
    contract: dict[str, Any],
    video: Video,
    asset: Asset,
) -> StoryAdherenceReview | None:
    settings = get_settings()
    existing = get_latest_story_adherence_review(db, video.id, settings.semantic_critic_version)
    if existing:
        return existing

    can_run, reason = can_run_semantic_critic()
    if not can_run:
        return None

    provider = get_semantic_critic_provider()
    if provider is None:
        return None

    video_path, delete_video_after = resolve_video_source_path(asset)
    try:
        frames, sampled_frames = sample_story_frames(video_path)
        prompt = build_critic_prompt(contract, topic, video.prompt_text, video, sampled_frames)
        observations: dict[str, Any] | None = None
        provider_error = ""
        for attempt in range(2):
            try:
                raw = provider.review(prompt, frames, {"topic": topic, "contract": contract, "sampled_frames": sampled_frames})
                observations = normalize_critic_observations(raw)
                break
            except ValueError as exc:
                provider_error = str(exc)
                if attempt == 1:
                    raise
        if observations is None:
            raise RuntimeError(provider_error or "Semantic critic did not return observations.")

        score, review_status, rule_reason = compute_story_adherence_verdict(observations)
        explanation_parts = [rule_reason]
        if observations.get("summary"):
            explanation_parts.append(observations["summary"])
        if observations.get("issues"):
            explanation_parts.append("Issues: " + "; ".join(observations["issues"]))
        review = StoryAdherenceReview(
            pipeline_run_id=pipeline_run_id,
            video_id=video.id,
            critic_version=settings.semantic_critic_version,
            model=provider.model,
            review_status=review_status,
            score=score,
            criteria_json=sanitize_for_json(observations["criteria"]),
            explanation=" ".join(part for part in explanation_parts if part).strip(),
            sampled_frames_json=sampled_frames,
            failure_reason=None,
        )
        db.add(review)
        db.flush()
        return review
    except Exception as exc:
        review = StoryAdherenceReview(
            pipeline_run_id=pipeline_run_id,
            video_id=video.id,
            critic_version=settings.semantic_critic_version,
            model=getattr(provider, "model", settings.semantic_critic_model),
            review_status="unavailable",
            score=None,
            criteria_json={},
            explanation="Sampled-frame story review was unavailable. Manual review is required.",
            sampled_frames_json={},
            failure_reason=str(exc),
        )
        db.add(review)
        db.flush()
        return review
    finally:
        if delete_video_after:
            for file_path in video_path.parent.glob("*"):
                file_path.unlink(missing_ok=True)
            video_path.parent.rmdir()


def serialize_human_review(review: StoryAdherenceHumanReview | None) -> dict[str, Any] | None:
    if review is None:
        return None
    return sanitize_for_json(
        {
            "decision": review.decision,
            "notes": review.notes,
            "created_at": review.created_at,
            "updated_at": review.updated_at,
        }
    )


def build_story_adherence_payload(
    *,
    contract: dict[str, Any],
    latest_quality: QualityCheck | None,
    review: StoryAdherenceReview | None,
    human_review: StoryAdherenceHumanReview | None,
    has_video: bool,
) -> dict[str, Any]:
    settings = get_settings()
    can_run, reason = can_run_semantic_critic()
    base = {
        "available": bool(review and review.review_status != "unavailable"),
        "review_source": "sampled_frame_story_review" if review else "none",
        "review_status": "preview_only" if not has_video else (review.review_status if review else "unavailable"),
        "score": review.score if review else None,
        "critic_version": review.critic_version if review else settings.semantic_critic_version,
        "model": review.model if review else settings.semantic_critic_model,
        "subject": contract.get("subject"),
        "initial_state": contract.get("initial_state"),
        "trigger": contract.get("trigger"),
        "required_transformation": contract.get("required_transformation"),
        "required_final_state": contract.get("required_final_state"),
        "final_state_hold": contract.get("final_state_hold"),
        "prohibited_actions": contract.get("prohibited_actions", []),
        "duration_plan": contract.get("duration_plan", {}),
        "criteria": review.criteria_json if review else {},
        "sampled_frames": review.sampled_frames_json if review else {},
        "explanation": review.explanation if review else (
            "Preview only. Story adherence evidence is defined below, but no video has been generated yet."
            if not has_video
            else (reason or "Sampled-frame story review is unavailable in this environment. Manual review is required.")
        ),
        "failure_reason": review.failure_reason if review else None,
        "technical_quality_score": latest_quality.score if latest_quality else None,
        "technical_quality_result": (
            "Pass" if latest_quality and latest_quality.passed else "Needs Review" if latest_quality else "Not Run"
        ),
        "human_review": serialize_human_review(human_review),
    }
    if review:
        base["available"] = review.review_status not in {"unavailable"}
    elif has_video and settings.semantic_critic_enabled and can_run:
        base["explanation"] = "Sampled-frame story review has not been run yet for this completed video."
    return sanitize_for_json(base)


def record_human_story_review(
    db: Session,
    *,
    run_id: str,
    decision: str,
    notes: str | None,
    review: StoryAdherenceReview | None,
) -> StoryAdherenceHumanReview:
    existing = get_human_story_adherence_review(db, run_id)
    if existing is None:
        existing = StoryAdherenceHumanReview(
            pipeline_run_id=run_id,
            story_adherence_review_id=review.id if review else None,
            decision=decision,
            notes=notes,
        )
        db.add(existing)
    else:
        existing.story_adherence_review_id = review.id if review else existing.story_adherence_review_id
        existing.decision = decision
        existing.notes = notes
    db.flush()
    return existing
