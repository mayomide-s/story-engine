from __future__ import annotations

import json
import math
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.grannygrinds import GrannyGrindJob
from app.providers.grannygrinds import InstagramReelsPublisher, RunwayAlephClient
from app.schemas.grannygrinds import GrannyGrindCreate
from app.services.providers import get_storage_provider


GRANNY_CHARACTER_SPECS = (
    {
        "key": "mabel",
        "name": "Mabel",
        "rotation_order": 1,
        "seed": 11031,
        "look": "a photorealistic woman in her late seventies with a short silver bob, warm lined face, and compact athletic build",
        "wardrobe": "a powder-blue floral midi dress, cream knitted cardigan, white ankle socks, and off-white low-top skate shoes",
    },
    {
        "key": "gloria",
        "name": "Gloria",
        "rotation_order": 2,
        "seed": 22061,
        "look": "a photorealistic woman in her early eighties with grey braids tucked under a burgundy headscarf, expressive lined face, and lean athletic build",
        "wardrobe": "a burgundy velour tracksuit, simple gold hoop earrings, and black low-top skate shoes",
    },
    {
        "key": "dorothy",
        "name": "Dorothy",
        "rotation_order": 3,
        "seed": 33091,
        "look": "a photorealistic woman in her late seventies with short white curls, glasses, a cheerful lined face, and sturdy athletic build",
        "wardrobe": "a mustard knitted vest over a pale blouse, brown plaid calf-length skirt, beige ankle socks, and beige low-top skate shoes",
    },
)


class GrannyGrindsConflictError(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def list_granny_characters() -> list[dict[str, Any]]:
    return [
        {
            "key": item["key"],
            "name": item["name"],
            "wardrobe": item["wardrobe"],
            "rotation_order": item["rotation_order"],
        }
        for item in GRANNY_CHARACTER_SPECS
    ]


def _character_for_key(key: str) -> dict[str, Any]:
    for character in GRANNY_CHARACTER_SPECS:
        if character["key"] == key:
            return character
    raise ValueError(f"Unknown GrannyGrinds character: {key}")


def _next_character(db: Session) -> dict[str, Any]:
    count = int(db.query(func.count(GrannyGrindJob.id)).scalar() or 0)
    return GRANNY_CHARACTER_SPECS[count % len(GRANNY_CHARACTER_SPECS)]


def build_granny_prompt(character: dict[str, Any]) -> str:
    return (
        "Edit this existing skateboarding video in place. Replace ONLY the primary skateboarder with "
        f"{character['look']}, wearing {character['wardrobe']}. "
        "The replacement granny must perform the exact same body motion as the original skater: preserve pose, "
        "limb positions, speed, balance, trajectory, board contact points, trick timing, takeoff, rotation, catch, "
        "landing, and roll-away. Keep the skateboard itself unchanged. Keep every other person unchanged. "
        "Preserve the original camera framing, camera motion, lens feel, cuts, background, architecture, obstacles, "
        "rails, stairs, ground, lighting, shadows, weather, color, depth of field, and scene timing. "
        "Do not add or remove objects. Do not change the environment. Do not add text, logos, effects, or stylization. "
        "The result must look like the exact same real video, except the primary skater is this photorealistic granny "
        "in her fixed wardrobe."
    )


def _serialize_job(job: GrannyGrindJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "source_post_url": job.source_post_url,
        "source_media_url": job.source_media_url,
        "source_creator_handle": job.source_creator_handle,
        "source_credit_text": job.source_credit_text,
        "rights_status": job.rights_status,
        "granny_key": job.granny_key,
        "granny_name": job.granny_name,
        "prompt_text": job.prompt_text,
        "status": job.status,
        "source_public_url": job.source_public_url,
        "source_metadata_json": job.source_metadata_json or {},
        "runway_task_id": job.runway_task_id,
        "transformed_public_url": job.transformed_public_url,
        "transformed_metadata_json": job.transformed_metadata_json or {},
        "qc_json": job.qc_json or {},
        "review_notes": job.review_notes,
        "instagram_media_id": job.instagram_media_id,
        "instagram_permalink": job.instagram_permalink,
        "last_error": job.last_error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def get_grannygrind_job(db: Session, job_id: str) -> dict[str, Any]:
    job = db.get(GrannyGrindJob, job_id)
    if job is None:
        raise ValueError("GrannyGrinds job not found.")
    return _serialize_job(job)


def list_grannygrind_jobs(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    jobs = (
        db.query(GrannyGrindJob)
        .order_by(GrannyGrindJob.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [_serialize_job(job) for job in jobs]


def create_grannygrind_job(db: Session, payload: GrannyGrindCreate) -> dict[str, Any]:
    character = _next_character(db)
    job = GrannyGrindJob(
        source_post_url=str(payload.source_post_url),
        source_media_url=str(payload.source_media_url),
        source_creator_handle=(payload.source_creator_handle or "").strip() or None,
        source_credit_text=(payload.source_credit_text or "").strip() or None,
        rights_status=payload.rights_status,
        granny_key=character["key"],
        granny_name=character["name"],
        prompt_text=build_granny_prompt(character),
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    from app.workers.jobs import process_grannygrind_job_task

    process_grannygrind_job_task.delay(job.id)
    return _serialize_job(job)


def _validate_download_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Source media URL must be an absolute HTTP(S) URL.")
    settings = get_settings()
    if parsed.scheme != "https" and not settings.is_development_like_environment():
        raise ValueError("Source media URL must use HTTPS outside local development.")


def _download_file(url: str, destination: Path, *, max_bytes: int = 250 * 1024 * 1024) -> None:
    _validate_download_url(url)
    total = 0
    with httpx.stream("GET", url, timeout=120.0, follow_redirects=True) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("Source media exceeds the 250 MB GrannyGrinds ingest limit.")
                handle.write(chunk)
    if destination.stat().st_size == 0:
        raise ValueError("Downloaded source media is empty.")


def _parse_fps(value: str | None) -> float:
    if not value:
        return 0.0
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        denominator_value = float(denominator)
        return float(numerator) / denominator_value if denominator_value else 0.0
    return float(value)


def probe_video(file_path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(file_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    video_stream = next((item for item in streams if item.get("codec_type") == "video"), None)
    if not video_stream:
        raise ValueError("Media file does not contain a video stream.")
    audio_stream = next((item for item in streams if item.get("codec_type") == "audio"), None)
    file_format = payload.get("format") or {}
    duration = float(file_format.get("duration") or video_stream.get("duration") or 0.0)
    fps = _parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate"))
    return {
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "duration_seconds": duration,
        "fps": fps,
        "frame_rate_raw": video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate"),
        "video_codec": video_stream.get("codec_name"),
        "has_audio": audio_stream is not None,
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        "audio_sample_rate": int(audio_stream.get("sample_rate") or 0) if audio_stream else None,
        "size_bytes": int(file_format.get("size") or file_path.stat().st_size),
    }


def validate_aleph_source(metadata: dict[str, Any]) -> None:
    duration = float(metadata["duration_seconds"])
    if duration < 2 or duration > 30:
        raise ValueError("Aleph 2.0 requires source clips between 2 and 30 seconds.")
    fps = float(metadata["fps"])
    if fps <= 0 or fps > 30.01:
        raise ValueError("Aleph 2.0 requires a source frame rate of 30 FPS or lower for this preservation-first pipeline.")
    width = int(metadata["width"])
    height = int(metadata["height"])
    if width <= 0 or height <= 0:
        raise ValueError("Source video dimensions are invalid.")
    if max(width, height) > 1920 or (width * height) > (1920 * 1080):
        raise ValueError("First-10 GrannyGrinds clips are limited to 1080p-class inputs so the output can preserve source resolution.")


def _runway_input_url(job: GrannyGrindJob) -> str:
    if job.source_public_url and job.source_public_url.startswith("https://"):
        return job.source_public_url
    if job.source_media_url.startswith("https://"):
        return job.source_media_url
    raise ValueError("Runway requires a publicly reachable HTTPS source video URL.")


def process_grannygrind_job(db: Session, job_id: str) -> None:
    job = db.get(GrannyGrindJob, job_id)
    if job is None:
        return
    if job.status not in {"queued", "failed"}:
        return

    job.status = "ingesting"
    job.last_error = None
    db.add(job)
    db.commit()

    try:
        with tempfile.TemporaryDirectory(prefix="grannygrinds-ingest-") as tmp:
            source_path = Path(tmp) / "source.mp4"
            _download_file(job.source_media_url, source_path)
            metadata = probe_video(source_path)
            validate_aleph_source(metadata)

            storage = get_storage_provider()
            storage_key = f"grannygrinds/source/{job.id}.mp4"
            stored = storage.save_file(str(source_path), storage_key)
            job.source_storage_key = stored["storage_key"]
            job.source_public_url = stored["public_url"]
            job.source_metadata_json = metadata
            db.add(job)
            db.commit()

        character = _character_for_key(job.granny_key)
        runway = RunwayAlephClient()
        submission = runway.submit_edit(
            video_url=_runway_input_url(job),
            prompt=job.prompt_text,
            seed=int(character["seed"]),
        )
        job.runway_task_id = submission["task_id"]
        job.runway_response_json = {
            "submission": submission["response"],
            "request": submission["request"],
            "poll_count": 0,
        }
        job.status = "submitted"
        db.add(job)
        db.commit()

        from app.workers.jobs import poll_grannygrind_job_task

        poll_grannygrind_job_task.apply_async(
            args=[job.id],
            countdown=get_settings().grannygrinds_poll_interval_seconds,
        )
    except Exception as exc:
        job.status = "failed"
        job.last_error = str(exc)[:4000]
        db.add(job)
        db.commit()


def _materialize_source(job: GrannyGrindJob, destination: Path) -> None:
    storage = get_storage_provider()
    if storage.name == "local" and job.source_storage_key:
        source_path = Path(storage.resolve_path(job.source_storage_key))
        if source_path.exists():
            destination.write_bytes(source_path.read_bytes())
            return
    source_url = job.source_public_url or job.source_media_url
    _download_file(source_url, destination)


def _remux_original_audio(source: Path, generated: Path, final: Path, source_meta: dict[str, Any]) -> None:
    generated_meta = probe_video(generated)
    same_geometry = (
        int(generated_meta["width"]) == int(source_meta["width"])
        and int(generated_meta["height"]) == int(source_meta["height"])
    )
    fps_delta = abs(float(generated_meta["fps"]) - float(source_meta["fps"]))
    same_fps = fps_delta <= 0.01

    if same_geometry and same_fps:
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(generated),
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0?",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-shortest",
            "-movflags",
            "+faststart",
            str(final),
        ]
    else:
        fps = max(float(source_meta["fps"]), 1.0)
        width = int(source_meta["width"])
        height = int(source_meta["height"])
        video_filter = f"scale={width}:{height}:flags=lanczos,fps={fps:.6f}"
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(generated),
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0?",
            "-vf",
            video_filter,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-shortest",
            "-movflags",
            "+faststart",
            str(final),
        ]
    subprocess.run(command, check=True, capture_output=True)


def build_preservation_qc(source: dict[str, Any], final: dict[str, Any]) -> dict[str, Any]:
    duration_delta = abs(float(source["duration_seconds"]) - float(final["duration_seconds"]))
    fps_delta = abs(float(source["fps"]) - float(final["fps"]))
    resolution_match = (
        int(source["width"]) == int(final["width"])
        and int(source["height"]) == int(final["height"])
    )
    audio_match = (not bool(source.get("has_audio"))) or bool(final.get("has_audio"))
    checks = {
        "resolution_match": resolution_match,
        "duration_delta_seconds": round(duration_delta, 4),
        "duration_match": duration_delta <= 0.20,
        "fps_delta": round(fps_delta, 4),
        "fps_match": fps_delta <= 0.02,
        "original_audio_present": bool(source.get("has_audio")),
        "final_audio_present": bool(final.get("has_audio")),
        "audio_preserved": audio_match,
    }
    checks["structural_pass"] = all(
        [
            checks["resolution_match"],
            checks["duration_match"],
            checks["fps_match"],
            checks["audio_preserved"],
        ]
    )
    checks["human_review_required"] = True
    checks["human_review_focus"] = [
        "only the primary skater changed",
        "skateboard geometry and contact points stay intact",
        "trick timing and trajectory match the source",
        "background, camera, obstacles, and bystanders are unchanged",
        "granny identity and fixed wardrobe are convincing",
    ]
    return checks


def _finalize_completed_runway_task(db: Session, job: GrannyGrindJob, task_payload: dict[str, Any]) -> None:
    output_url = RunwayAlephClient.output_url(task_payload)
    if not output_url:
        raise ValueError("Runway completed without an output video URL.")

    job.status = "postprocessing"
    db.add(job)
    db.commit()

    with tempfile.TemporaryDirectory(prefix="grannygrinds-finalize-") as tmp:
        temp_dir = Path(tmp)
        generated_path = temp_dir / "runway.mp4"
        source_path = temp_dir / "source.mp4"
        final_path = temp_dir / "final.mp4"

        _download_file(output_url, generated_path)
        _materialize_source(job, source_path)
        source_meta = probe_video(source_path)
        _remux_original_audio(source_path, generated_path, final_path, source_meta)
        final_meta = probe_video(final_path)
        qc = build_preservation_qc(source_meta, final_meta)

        storage = get_storage_provider()
        storage_key = f"grannygrinds/final/{job.id}.mp4"
        stored = storage.save_file(str(final_path), storage_key)

        job.transformed_storage_key = stored["storage_key"]
        job.transformed_public_url = stored["public_url"]
        job.transformed_metadata_json = final_meta
        job.qc_json = qc
        job.status = "needs_review"
        job.last_error = None
        db.add(job)
        db.commit()


def poll_grannygrind_job(db: Session, job_id: str) -> None:
    job = db.get(GrannyGrindJob, job_id)
    if job is None or not job.runway_task_id:
        return
    if job.status not in {"submitted", "generating"}:
        return

    settings = get_settings()
    try:
        runway = RunwayAlephClient()
        payload = runway.get_task(job.runway_task_id)
        normalized = runway.normalize_status(payload)
        stored_response = dict(job.runway_response_json or {})
        poll_count = int(stored_response.get("poll_count") or 0) + 1
        stored_response["poll_count"] = poll_count
        stored_response["latest_task"] = payload
        job.runway_response_json = stored_response

        if normalized == "failed":
            job.status = "failed"
            failure = payload.get("failure") or payload.get("error") or payload.get("status")
            job.last_error = f"Runway generation failed: {failure}"[:4000]
            db.add(job)
            db.commit()
            return

        if normalized == "completed":
            db.add(job)
            db.commit()
            _finalize_completed_runway_task(db, job, payload)
            return

        if poll_count >= settings.grannygrinds_max_poll_attempts:
            job.status = "failed"
            job.last_error = "Runway polling exceeded the configured maximum attempts."
            db.add(job)
            db.commit()
            return

        job.status = "generating"
        db.add(job)
        db.commit()

        from app.workers.jobs import poll_grannygrind_job_task

        poll_grannygrind_job_task.apply_async(
            args=[job.id],
            countdown=settings.grannygrinds_poll_interval_seconds,
        )
    except Exception as exc:
        job.status = "failed"
        job.last_error = str(exc)[:4000]
        db.add(job)
        db.commit()


def approve_grannygrind_job(db: Session, job_id: str, *, notes: str | None = None) -> dict[str, Any]:
    job = db.get(GrannyGrindJob, job_id)
    if job is None:
        raise ValueError("GrannyGrinds job not found.")
    if job.status != "needs_review":
        raise GrannyGrindsConflictError("Only jobs awaiting review can be approved.")
    if not bool((job.qc_json or {}).get("structural_pass")):
        raise GrannyGrindsConflictError("Structural preservation QA failed. Reject or regenerate this clip instead.")

    job.status = "approved"
    job.review_notes = notes
    job.approved_at = _utcnow()
    job.rejected_at = None
    db.add(job)
    db.commit()
    db.refresh(job)

    if get_settings().grannygrinds_autopublish:
        request_instagram_publish(db, job.id, caption=None, share_to_feed=True)
        db.refresh(job)
    return _serialize_job(job)


def reject_grannygrind_job(db: Session, job_id: str, *, notes: str | None = None) -> dict[str, Any]:
    job = db.get(GrannyGrindJob, job_id)
    if job is None:
        raise ValueError("GrannyGrinds job not found.")
    if job.status not in {"needs_review", "approved"}:
        raise GrannyGrindsConflictError("This job is not in a reviewable state.")
    job.status = "rejected"
    job.review_notes = notes
    job.rejected_at = _utcnow()
    db.add(job)
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


def _default_credit_caption(job: GrannyGrindJob) -> str:
    if job.source_credit_text:
        return job.source_credit_text.strip()
    if job.source_creator_handle:
        handle = job.source_creator_handle.strip()
        return f"Original clip: {handle if handle.startswith('@') else '@' + handle}"
    return ""


def request_instagram_publish(
    db: Session,
    job_id: str,
    *,
    caption: str | None,
    share_to_feed: bool,
) -> dict[str, Any]:
    job = db.get(GrannyGrindJob, job_id)
    if job is None:
        raise ValueError("GrannyGrinds job not found.")
    if job.status != "approved":
        raise GrannyGrindsConflictError("Only approved GrannyGrinds clips can be published.")
    if not job.transformed_public_url or not job.transformed_public_url.startswith("https://"):
        raise GrannyGrindsConflictError("Instagram publishing requires a publicly reachable HTTPS final video URL.")

    publisher = InstagramReelsPublisher()
    container = publisher.create_container(
        video_url=job.transformed_public_url,
        caption=caption if caption is not None else _default_credit_caption(job),
        share_to_feed=share_to_feed,
    )
    job.instagram_container_id = str(container["id"])
    job.status = "publishing"
    job.last_error = None
    db.add(job)
    db.commit()

    from app.workers.jobs import poll_grannygrind_instagram_task

    poll_grannygrind_instagram_task.apply_async(
        args=[job.id],
        countdown=get_settings().grannygrinds_instagram_poll_interval_seconds,
    )
    return _serialize_job(job)


def poll_grannygrind_instagram(db: Session, job_id: str) -> None:
    job = db.get(GrannyGrindJob, job_id)
    if job is None or job.status != "publishing" or not job.instagram_container_id:
        return
    settings = get_settings()
    try:
        publisher = InstagramReelsPublisher()
        status_payload = publisher.get_container_status(job.instagram_container_id)
        status_code = str(status_payload.get("status_code") or "").upper()

        if status_code == "FINISHED":
            published = publisher.publish_container(job.instagram_container_id)
            media_id = str(published["id"])
            media = publisher.get_media(media_id)
            job.instagram_media_id = media_id
            job.instagram_permalink = media.get("permalink")
            job.status = "published"
            job.published_at = _utcnow()
            job.last_error = None
            db.add(job)
            db.commit()
            return

        if status_code in {"ERROR", "EXPIRED"}:
            job.status = "approved"
            job.last_error = f"Instagram container failed: {status_payload.get('status') or status_code}"[:4000]
            db.add(job)
            db.commit()
            return

        payload = dict(job.runway_response_json or {})
        instagram_poll_count = int(payload.get("instagram_poll_count") or 0) + 1
        payload["instagram_poll_count"] = instagram_poll_count
        job.runway_response_json = payload
        if instagram_poll_count >= settings.grannygrinds_instagram_max_poll_attempts:
            job.status = "approved"
            job.last_error = "Instagram publishing timed out while waiting for the Reel container."
            db.add(job)
            db.commit()
            return
        db.add(job)
        db.commit()

        from app.workers.jobs import poll_grannygrind_instagram_task

        poll_grannygrind_instagram_task.apply_async(
            args=[job.id],
            countdown=settings.grannygrinds_instagram_poll_interval_seconds,
        )
    except Exception as exc:
        job.status = "approved"
        job.last_error = str(exc)[:4000]
        db.add(job)
        db.commit()
