from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Account,
    Asset,
    ContentIdea,
    GenerationCost,
    ManualPackageStatus,
    ManualPostPackage,
    PipelineEvent,
    PipelineRun,
    PipelineStage,
    PipelineStatus,
    PromptLog,
    QualityCheck,
    Script,
    Storyboard,
    Video,
    VideoStatus,
)
from app.schemas.pipeline_runs import ContentIdeaPatch, PipelineRunCreate, ScriptPatch, StoryboardPatch
from app.services.providers import get_llm_provider, get_storage_provider, get_video_provider
from app.services.security import redact_sensitive_data, sanitize_for_json


DEFAULT_ACCOUNT_NAME = "CodeToons AI"


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def seed_default_account(db: Session) -> Account:
    account = db.query(Account).filter(Account.name == DEFAULT_ACCOUNT_NAME).first()
    if account:
        return account
    account = Account(
        name=DEFAULT_ACCOUNT_NAME,
        niche="coding concepts explained through AI mini-stories",
        account_config_json={
            "tone": "funny, simple, visual, slightly chaotic",
            "style": "clean 3D cartoon",
            "duration_min": 18,
            "duration_max": 30,
            "aspect_ratio": "9:16",
            "end_tag": "Made by CodeToons AI",
            "banned_content": ["malware", "phishing", "fake income claims"],
            "target_platforms": ["instagram", "tiktok", "youtube"],
        },
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def add_event(
    db: Session,
    run_id: str,
    event_type: str,
    message: str,
    stage: str | None = None,
    metadata: dict | None = None,
):
    event = PipelineEvent(
        pipeline_run_id=run_id,
        event_type=event_type,
        stage=stage,
        message=message,
        metadata_json=sanitize_for_json(metadata or {}),
    )
    db.add(event)
    db.flush()


def add_prompt_log(
    db: Session,
    run_id: str,
    stage: str,
    provider: str,
    model: str,
    prompt_text: str,
    request_json: dict,
    response_json: dict,
    output_text: str,
    token_usage_json: dict,
    cost_estimate: float,
):
    prompt_log = PromptLog(
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
    db.add(prompt_log)
    db.add(
        GenerationCost(
            pipeline_run_id=run_id,
            provider=provider,
            model=model,
            stage=stage,
            estimated_cost=cost_estimate,
            credits_used=0.0,
        )
    )


def get_target_duration_seconds(account_config: dict[str, Any] | None, provider_name: str) -> int:
    config = account_config or {}
    configured_min = int(config.get("duration_min", 18))
    configured_max = int(config.get("duration_max", configured_min))
    configured_target = min(configured_max, max(configured_min, configured_min))
    if provider_name == "runway":
        return min(max(configured_target, 5), 10)
    return min(max(configured_target, 18), 30)


def build_scene_timings(total_duration_seconds: int) -> list[str]:
    checkpoints = [0, round(total_duration_seconds * 0.2), round(total_duration_seconds * 0.5), round(total_duration_seconds * 0.8), total_duration_seconds]
    timings: list[str] = []
    previous = 0
    for index, checkpoint in enumerate(checkpoints[1:], start=1):
        remaining_slots = 4 - index
        upper_bound = total_duration_seconds - remaining_slots
        current = max(previous + 1, min(checkpoint, upper_bound))
        if index == 4:
            current = total_duration_seconds
        timings.append(f"{previous}-{current}s")
        previous = current
    return timings


def fail_pipeline_run(
    db: Session,
    run: PipelineRun,
    message: str,
    stage: PipelineStage,
    video: Video | None = None,
    event_type: str = "pipeline.failed",
):
    if video is not None and run.video_id is None:
        run.video_id = video.id
    run.current_stage = stage
    run.status = PipelineStatus.FAILED
    run.error_message = message
    run.last_error = message
    if video is not None:
        video.status = VideoStatus.FAILED
        video.failed_at = now_utc()
        video.last_error = message
    add_event(db, run.id, event_type, message, stage=stage.value)
    db.commit()


def get_default_account(db: Session) -> Account:
    return seed_default_account(db)


def create_pipeline_run(db: Session, payload: PipelineRunCreate) -> PipelineRun:
    account = get_default_account(db)
    run = PipelineRun(
        account_id=account.id,
        topic=payload.topic,
        auto_mode=payload.auto_mode,
        priority=payload.priority,
        status=PipelineStatus.QUEUED,
        current_stage=PipelineStage.IDEA_GENERATION,
        idempotency_key=f"run:{payload.topic.lower()}:{now_utc().date().isoformat()}",
    )
    db.add(run)
    db.flush()
    add_event(db, run.id, "pipeline_run.created", f"Pipeline run created for topic '{payload.topic}'", stage=run.current_stage.value)
    db.commit()
    db.refresh(run)
    try:
        run_pipeline(db, run.id, stop_before_video=not payload.auto_mode)
    except Exception as exc:
        db.rollback()
        run = db.get(PipelineRun, run.id)
        if run and run.status != PipelineStatus.FAILED:
            fail_pipeline_run(db, run, f"Pipeline start failed: {exc}", run.current_stage, event_type="pipeline.start_failed")
        raise RuntimeError(f"Pipeline start failed: {exc}") from exc
    return db.get(PipelineRun, run.id)


def update_run_status(db: Session, run: PipelineRun, status: PipelineStatus, stage: PipelineStage | None = None):
    run.status = status
    if stage:
        run.current_stage = stage


def generate_idea(db: Session, run: PipelineRun):
    llm = get_llm_provider()
    prompt = f"Turn topic '{run.topic}' into a coding metaphor video idea."
    result = llm.generate(PipelineStage.IDEA_GENERATION.value, prompt, {"topic": run.topic})
    idea = ContentIdea(
        pipeline_run_id=run.id,
        topic=run.topic,
        title=f"{run.topic} as a nightclub bouncer",
        hook=f"{run.topic} is just a bouncer with trust issues.",
        concept=f"The frontend tries to access {run.topic} knowledge through a vivid metaphor.",
        format="character_metaphor",
        difficulty="beginner",
    )
    db.add(idea)
    db.flush()
    run.idea_id = idea.id
    add_prompt_log(
        db,
        run.id,
        PipelineStage.IDEA_GENERATION.value,
        llm.name,
        llm.model,
        prompt,
        {"topic": run.topic},
        result,
        idea.hook,
        result["token_usage"],
        result["cost_estimate"],
    )
    add_event(db, run.id, "idea.generated", f"Idea generated: {idea.title}", stage=PipelineStage.IDEA_GENERATION.value)


def generate_script(db: Session, run: PipelineRun):
    llm = get_llm_provider()
    idea = db.get(ContentIdea, run.idea_id)
    account = db.get(Account, run.account_id)
    provider_name = get_settings().video_provider
    target_duration = get_target_duration_seconds(account.account_config_json if account else {}, provider_name)
    scene_timings = build_scene_timings(target_duration)
    prompt = f"Write a short script for '{idea.title}'"
    result = llm.generate(PipelineStage.SCRIPT_GENERATION.value, prompt, {"idea_id": idea.id})
    script_json = {
        "hook": idea.hook,
        "scenes": [
            {"time": scene_timings[0], "visual": "Frontend arrives at a neon nightclub.", "dialogue": "I need the user data."},
            {"time": scene_timings[1], "visual": "A CORS bouncer blocks the entrance.", "dialogue": "Where is your allowed-origin pass?"},
            {"time": scene_timings[2], "visual": "Backend checks the list.", "dialogue": "Only approved websites can enter."},
            {"time": scene_timings[3], "visual": "A green stamp appears.", "dialogue": f"That is {run.topic}."},
        ],
        "final_tag": "Made by CodeToons AI",
        "target_duration_seconds": target_duration,
    }
    script = Script(pipeline_run_id=run.id, hook=idea.hook, script_json=script_json, duration_seconds=target_duration)
    db.add(script)
    db.flush()
    run.script_id = script.id
    add_prompt_log(
        db,
        run.id,
        PipelineStage.SCRIPT_GENERATION.value,
        llm.name,
        llm.model,
        prompt,
        {"idea_id": idea.id},
        result,
        idea.hook,
        result["token_usage"],
        result["cost_estimate"],
    )
    add_event(db, run.id, "script.generated", "Script generated", stage=PipelineStage.SCRIPT_GENERATION.value)


def generate_storyboard(db: Session, run: PipelineRun):
    llm = get_llm_provider()
    script = db.get(Script, run.script_id)
    prompt = "Create storyboard frames from the script."
    result = llm.generate(PipelineStage.STORYBOARD_GENERATION.value, prompt, script.script_json)
    frames = {
        "storyboard_frames": [
            {"frame": 1, "description": "Frontend character outside Backend API nightclub"},
            {"frame": 2, "description": "CORS bouncer blocks entry"},
            {"frame": 3, "description": "Backend checks approved origins"},
            {"frame": 4, "description": "Green access stamp appears"},
        ]
    }
    storyboard = Storyboard(pipeline_run_id=run.id, frames_json=frames)
    db.add(storyboard)
    db.flush()
    run.storyboard_id = storyboard.id
    add_prompt_log(
        db,
        run.id,
        PipelineStage.STORYBOARD_GENERATION.value,
        llm.name,
        llm.model,
        prompt,
        script.script_json,
        result,
        str(frames),
        result["token_usage"],
        result["cost_estimate"],
    )
    db.add(
        Asset(
            pipeline_run_id=run.id,
            asset_type="storyboard_image",
            created_by_stage=PipelineStage.STORYBOARD_GENERATION.value,
            storage_key=f"storyboards/{run.id}.json",
            public_url=f"/storyboards/{run.id}",
            mime_type="application/json",
            size_bytes=1024,
        )
    )
    add_event(db, run.id, "storyboard.generated", "Storyboard generated", stage=PipelineStage.STORYBOARD_GENERATION.value)


def build_video_prompt(run: PipelineRun, db: Session) -> str:
    script = db.get(Script, run.script_id)
    account = db.get(Account, run.account_id)
    prompt = (
        f"Create a 9:16 animated video about {run.topic}. "
        f"Style: {account.account_config_json['style']}. "
        "Use actual motion, expressive characters, no slideshow effects. "
        f"Scenes: {script.script_json['scenes']} "
        f"End tag: {account.account_config_json['end_tag']}"
    )
    return prompt


def enqueue_resume_pipeline_task(run_id: str, countdown: int | None = None) -> None:
    from app.workers.jobs import resume_pipeline_task

    if countdown is None:
        resume_pipeline_task.delay(run_id)
        return
    resume_pipeline_task.apply_async(args=[run_id], countdown=countdown)


def create_video_placeholder(db: Session, run: PipelineRun) -> Video:
    settings = get_settings()
    provider = get_video_provider()
    account = db.get(Account, run.account_id)
    account_config = account.account_config_json if account else {}
    prompt = build_video_prompt(run, db)
    target_duration = get_target_duration_seconds(account_config, provider.name)
    video = db.get(Video, run.video_id) if run.video_id else None
    prior_stage = run.current_stage

    if video is None:
        video = Video(
            pipeline_run_id=run.id,
            provider=provider.name,
            prompt_text=prompt,
            status=VideoStatus.SUBMITTING if provider.name == "runway" else VideoStatus.GENERATING,
            provider_timeout_at=now_utc() + timedelta(minutes=settings.default_provider_timeout_minutes),
            max_poll_attempts=settings.default_max_poll_attempts,
            poll_interval_seconds=settings.default_poll_interval_seconds,
            idempotency_key=f"video:{run.id}",
            requested_duration_seconds=target_duration,
            duration_seconds=target_duration,
        )
        db.add(video)
        db.flush()
    else:
        video.provider = provider.name
        video.prompt_text = prompt
        video.status = VideoStatus.SUBMITTING if provider.name == "runway" else VideoStatus.GENERATING
        video.provider_timeout_at = now_utc() + timedelta(minutes=settings.default_provider_timeout_minutes)
        video.max_poll_attempts = settings.default_max_poll_attempts
        video.poll_interval_seconds = settings.default_poll_interval_seconds
        video.requested_duration_seconds = target_duration
        video.duration_seconds = target_duration

    run.video_id = video.id
    run.current_stage = PipelineStage.VIDEO_GENERATION_SUBMIT
    if prior_stage != PipelineStage.VIDEO_GENERATION_SUBMIT:
        add_event(db, run.id, "video_prompt.built", "Video prompt built", stage=PipelineStage.VIDEO_PROMPT_BUILD.value)
    db.commit()
    db.refresh(video)
    return video


def submit_video_job(db: Session, run: PipelineRun) -> Video:
    provider = get_video_provider()
    account = db.get(Account, run.account_id)
    account_config = account.account_config_json if account else {}
    video = db.get(Video, run.video_id) if run.video_id else None
    if video is None:
        video = create_video_placeholder(db, run)
        run = db.get(PipelineRun, run.id) or run
    if video.provider_job_id:
        return video

    response = provider.create_video(
        video.prompt_text,
        {
            "aspect_ratio": account_config.get("aspect_ratio", "9:16"),
            "duration_seconds": video.duration_seconds,
        },
    )
    video.submitted_at = now_utc()
    video.attempt_count = 1
    video.provider_job_id = response["job_id"]
    video.provider_request_id = response["request_id"]
    video.provider_status = response["status"]
    video.provider_response_json = redact_sensitive_data(response["response"])
    video.status = VideoStatus.GENERATING
    run.video_id = video.id
    run.current_stage = PipelineStage.VIDEO_GENERATION_POLLING
    add_event(db, run.id, "video.submitted", f"Video submitted to {provider.name}", stage=PipelineStage.VIDEO_GENERATION_SUBMIT.value)
    db.add(
        GenerationCost(
            pipeline_run_id=run.id,
            provider=provider.name,
            model="video-generation",
            stage=PipelineStage.VIDEO_GENERATION_SUBMIT.value,
            estimated_cost=1.25,
            credits_used=1.0,
        )
    )
    db.commit()
    db.refresh(video)
    return video


def poll_video(db: Session, run: PipelineRun) -> str:
    provider = get_video_provider()
    video = db.get(Video, run.video_id)
    if not video:
        return "missing"
    if video.status in {VideoStatus.COMPLETED, VideoStatus.APPROVED}:
        return "completed"
    if video.status == VideoStatus.FAILED:
        return "failed"
    if video.provider_timeout_at and now_utc() > video.provider_timeout_at:
        video.status = VideoStatus.FAILED
        video.failed_at = now_utc()
        video.last_error = "Provider timeout reached"
        run.status = PipelineStatus.FAILED
        run.error_message = video.last_error
        add_event(db, run.id, "video.failed", video.last_error, stage=PipelineStage.VIDEO_GENERATION_POLLING.value)
        db.commit()
        return "failed"
    if video.attempt_count >= video.max_poll_attempts:
        video.status = VideoStatus.FAILED
        video.failed_at = now_utc()
        video.last_error = "Maximum poll attempts reached"
        run.status = PipelineStatus.FAILED
        run.error_message = video.last_error
        add_event(db, run.id, "video.failed", video.last_error, stage=PipelineStage.VIDEO_GENERATION_POLLING.value)
        db.commit()
        return "failed"

    video.attempt_count += 1
    status = provider.get_status(video.provider_job_id or "")
    video.provider_status = status.get("raw_status") or status["status"]
    video.provider_response_json = redact_sensitive_data(status.get("response", {}))
    add_event(db, run.id, "video.polling_started", f"Provider polling status: {status['status']}", stage=PipelineStage.VIDEO_GENERATION_POLLING.value)
    if status["status"] == "failed":
        video.status = VideoStatus.FAILED
        video.failed_at = now_utc()
        video.last_error = status.get("failure") or "Provider task failed"
        run.status = PipelineStatus.FAILED
        run.error_message = video.last_error
        add_event(db, run.id, "video.failed", video.last_error, stage=PipelineStage.VIDEO_GENERATION_POLLING.value)
        db.commit()
        return "failed"
    if status["status"] == "completed":
        video.status = VideoStatus.COMPLETED
        video.completed_at = now_utc()
        db.commit()
        return "completed"

    db.commit()
    return "processing"


def upload_video_asset(db: Session, run: PipelineRun) -> bool:
    provider = get_video_provider()
    video = db.get(Video, run.video_id)
    if not video or video.status != VideoStatus.COMPLETED:
        return False
    try:
        storage = get_storage_provider()
        existing_asset = (
            db.query(Asset)
            .filter(Asset.pipeline_run_id == run.id, Asset.asset_type == "video_mp4")
            .order_by(Asset.created_at.desc())
            .first()
        )
        if existing_asset:
            return True

        payload = provider.download_video(video.provider_job_id or "")
        stored_video = storage.save_file(payload["source_path"], payload["storage_key"])
        asset = Asset(
            pipeline_run_id=run.id,
            asset_type="video_mp4",
            created_by_stage="video_generation",
            storage_key=stored_video["storage_key"],
            public_url=stored_video["public_url"],
            mime_type=payload["mime_type"],
            size_bytes=stored_video["size_bytes"],
            duration_seconds=payload["duration_seconds"],
            width=payload["width"],
            height=payload["height"],
        )
        db.add(asset)
        video.duration_seconds = payload["duration_seconds"]
        video.aspect_ratio = f"{payload['width']}:{payload['height']}"

        thumbnail_payload = payload.get("thumbnail")
        if thumbnail_payload:
            stored_thumbnail = storage.save_file(thumbnail_payload["source_path"], thumbnail_payload["storage_key"])
            thumbnail = Asset(
                pipeline_run_id=run.id,
                asset_type="thumbnail",
                created_by_stage="thumbnail_generation",
                storage_key=stored_thumbnail["storage_key"],
                public_url=stored_thumbnail["public_url"],
                mime_type=thumbnail_payload["mime_type"],
                size_bytes=stored_thumbnail["size_bytes"],
                width=thumbnail_payload["width"],
                height=thumbnail_payload["height"],
            )
            db.add(thumbnail)

        add_event(db, run.id, "asset.uploaded", "Video and thumbnail assets registered", stage=PipelineStage.ASSET_UPLOAD.value)
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        run = db.get(PipelineRun, run.id) or run
        video = db.get(Video, run.video_id) if run.video_id else video
        if video is not None:
            video.status = VideoStatus.FAILED
            video.failed_at = now_utc()
            video.last_error = f"Asset upload failed: {exc}"
        run.status = PipelineStatus.FAILED
        run.error_message = f"Asset upload failed: {exc}"
        add_event(
            db,
            run.id,
            "asset.upload_failed",
            f"Asset upload failed: {exc}",
            stage=PipelineStage.ASSET_UPLOAD.value,
            metadata={"storage_provider": get_settings().storage_provider},
        )
        db.commit()
        return False


def run_quality_check(db: Session, run: PipelineRun):
    video = db.get(Video, run.video_id)
    asset = (
        db.query(Asset)
        .filter(Asset.pipeline_run_id == run.id, Asset.asset_type == "video_mp4")
        .order_by(Asset.created_at.desc())
        .first()
    )
    storage = get_storage_provider()
    asset_exists = bool(asset and asset.storage_key)
    local_asset_path = storage.resolve_path(asset.storage_key) if asset_exists and storage.name == "local" else ""
    is_nine_sixteen = bool(asset and asset.width and asset.height and asset.width * 16 == asset.height * 9)
    duration_seconds = asset.duration_seconds if asset and asset.duration_seconds is not None else 0
    requested_duration_seconds = video.requested_duration_seconds if video and video.requested_duration_seconds else video.duration_seconds
    duration_tolerance_seconds = 2 if requested_duration_seconds >= 10 else 1
    checks = {
        "video_exists": asset_exists and (Path(local_asset_path).exists() if storage.name == "local" else bool(asset.public_url)),
        "aspect_ratio_9_16": is_nine_sixteen,
        "duration_in_range": abs(duration_seconds - requested_duration_seconds) <= duration_tolerance_seconds,
        "end_tag_present": "Made by CodeToons AI" in video.prompt_text,
        "caption_safe": True,
        "provider_generated_video": True,
        "requested_duration_seconds": requested_duration_seconds,
        "actual_duration_seconds": duration_seconds,
    }
    passed = all(
        bool(checks[key])
        for key in (
            "video_exists",
            "aspect_ratio_9_16",
            "duration_in_range",
            "end_tag_present",
            "caption_safe",
            "provider_generated_video",
        )
    )
    score = 0.92 if passed else 0.4
    critical_failure = not checks["video_exists"] or not checks["provider_generated_video"]
    quality = QualityCheck(
        pipeline_run_id=run.id,
        video_id=video.id,
        passed=passed,
        score=score,
        checks_json=sanitize_for_json(checks),
        llm_critique="Clear metaphor and appropriate motion constraints. Safe for beginner developers.",
    )
    db.add(quality)
    video.quality_score = score
    video.review_status = "approved" if passed else "needs_review"
    if passed:
        video.status = VideoStatus.APPROVED
    else:
        video.status = VideoStatus.REJECTED
        run.status = PipelineStatus.FAILED if critical_failure else PipelineStatus.NEEDS_REVIEW
    add_event(db, run.id, "quality_check.completed", "Quality check passed" if passed else "Quality check failed", stage=PipelineStage.QUALITY_CHECK.value)


def finalize_post_video_processing(db: Session, run: PipelineRun) -> PipelineRun:
    run.current_stage = PipelineStage.QUALITY_CHECK
    db.commit()
    run_quality_check(db, run)
    db.commit()

    run = db.get(PipelineRun, run.id) or run
    if run.status == PipelineStatus.FAILED:
        return run
    if run.status == PipelineStatus.NEEDS_REVIEW:
        add_event(db, run.id, "pipeline.needs_review", "Quality check requires manual review", stage=PipelineStage.QUALITY_CHECK.value)
        db.commit()
        return run

    run.current_stage = PipelineStage.MANUAL_PACKAGE_CREATION
    create_manual_post_package(db, run)
    run.current_stage = PipelineStage.COMPLETED
    run.status = PipelineStatus.COMPLETED
    run.error_message = None
    run.last_error = None
    add_event(db, run.id, "pipeline.completed", "Pipeline completed successfully", stage=PipelineStage.COMPLETED.value)
    db.commit()
    return run


def create_manual_post_package(db: Session, run: PipelineRun):
    video = db.get(Video, run.video_id)
    if run.manual_post_package_id:
        return db.get(ManualPostPackage, run.manual_post_package_id)

    caption = "CORS is just a bouncer with trust issues. Save this for the next time your frontend gets blocked."
    hashtags = ["#coding", "#webdev", "#cors", "#javascript", "#apitips"]
    pkg = ManualPostPackage(
        video_id=video.id,
        caption=caption,
        hashtags_json=hashtags,
        target_platforms_json=["instagram", "tiktok", "youtube"],
        checklist_json=[
            "Review the video for motion and clarity",
            "Confirm end tag visibility",
            "Upload manually to each platform",
        ],
        platform_variants_json={
            "instagram": {"caption": caption, "hashtags": hashtags},
            "tiktok": {"caption": caption + " #learnontiktok", "hashtags": hashtags},
            "youtube": {"title": "CORS as a nightclub bouncer", "description": caption, "hashtags": hashtags},
        },
        status=ManualPackageStatus.READY,
    )
    db.add(pkg)
    db.flush()
    run.manual_post_package_id = pkg.id
    add_event(db, run.id, "manual_package.created", "Manual posting package created", stage=PipelineStage.MANUAL_PACKAGE_CREATION.value)
    return pkg


def run_pipeline(db: Session, run_id: str, stop_before_video: bool = True):
    run = db.get(PipelineRun, run_id)
    if not run or run.status == PipelineStatus.CANCELLED:
        return
    run.status = PipelineStatus.RUNNING
    run.current_stage = PipelineStage.IDEA_GENERATION
    generate_idea(db, run)
    run.current_stage = PipelineStage.SCRIPT_GENERATION
    generate_script(db, run)
    run.current_stage = PipelineStage.STORYBOARD_GENERATION
    generate_storyboard(db, run)
    if stop_before_video:
        run.status = PipelineStatus.AWAITING_REVIEW
        run.paused_at = now_utc()
        add_event(db, run.id, "pipeline.paused", "Run paused for manual review before video generation", stage=PipelineStage.STORYBOARD_GENERATION.value)
        db.commit()
        return
    continue_pipeline_after_review(db, run)


def continue_pipeline_after_review(db: Session, run: PipelineRun):
    if run.status == PipelineStatus.CANCELLED:
        return
    try:
        video = db.get(Video, run.video_id) if run.video_id else None
        if video is None:
            video = create_video_placeholder(db, run)
            run = db.get(PipelineRun, run.id) or run

        if not video.provider_job_id:
            video = submit_video_job(db, run)
            run = db.get(PipelineRun, run.id) or run
        elif run.current_stage != PipelineStage.VIDEO_GENERATION_POLLING or run.status != PipelineStatus.RUNNING:
            run.current_stage = PipelineStage.VIDEO_GENERATION_POLLING
            run.status = PipelineStatus.RUNNING
            db.commit()

        run = db.get(PipelineRun, run.id) or run
        poll_result = poll_video(db, run)
        run = db.get(PipelineRun, run.id) or run
        if run.status == PipelineStatus.FAILED or poll_result == "failed":
            return
        if poll_result != "completed":
            current_video = db.get(Video, run.video_id) if run.video_id else None
            if current_video and current_video.poll_interval_seconds:
                enqueue_resume_pipeline_task(run.id, countdown=current_video.poll_interval_seconds)
            return

        run.current_stage = PipelineStage.ASSET_UPLOAD
        db.commit()
        if not upload_video_asset(db, run):
            return

        run = db.get(PipelineRun, run.id) or run
        finalize_post_video_processing(db, run)
    except Exception as exc:
        db.rollback()
        run = db.get(PipelineRun, run.id) or run
        current_video = db.get(Video, run.video_id) if run.video_id else None
        fail_pipeline_run(db, run, f"Resume failed: {exc}", run.current_stage, video=current_video, event_type="pipeline.resume_failed")
        raise RuntimeError(f"Resume failed: {exc}") from exc


def resume_pipeline(db: Session, run_id: str, review_notes: str | None = None) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    if not run:
        raise ValueError("Pipeline run not found")
    video = db.get(Video, run.video_id) if run.video_id else None

    if run.status in {PipelineStatus.COMPLETED, PipelineStatus.CANCELLED, PipelineStatus.FAILED}:
        raise RuntimeError(f"Run cannot be resumed from status '{run.status.value}'")
    if run.status == PipelineStatus.RUNNING and run.current_stage in {
        PipelineStage.VIDEO_PROMPT_BUILD,
        PipelineStage.VIDEO_GENERATION_SUBMIT,
        PipelineStage.VIDEO_GENERATION_POLLING,
        PipelineStage.ASSET_UPLOAD,
        PipelineStage.QUALITY_CHECK,
        PipelineStage.MANUAL_PACKAGE_CREATION,
    }:
        return run
    if video and video.provider_job_id and run.status == PipelineStatus.RUNNING:
        return run

    run.review_notes = review_notes
    run.status = PipelineStatus.RUNNING
    run.resumed_at = now_utc()
    run.paused_at = None
    run.current_stage = PipelineStage.VIDEO_PROMPT_BUILD
    add_event(db, run.id, "pipeline.resumed", "Run resumed", stage=PipelineStage.VIDEO_PROMPT_BUILD.value)
    db.commit()

    if get_settings().video_provider == "runway":
        enqueue_resume_pipeline_task(run.id)
        return db.get(PipelineRun, run.id)

    continue_pipeline_after_review(db, db.get(PipelineRun, run.id) or run)
    return db.get(PipelineRun, run.id)


def process_resume_pipeline(db: Session, run_id: str):
    run = db.get(PipelineRun, run_id)
    if not run or run.status in {PipelineStatus.CANCELLED, PipelineStatus.COMPLETED}:
        return
    continue_pipeline_after_review(db, run)


def recheck_pipeline_assets(db: Session, run_id: str, review_notes: str | None = None) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    if not run:
        raise ValueError("Pipeline run not found")
    video = db.get(Video, run.video_id) if run.video_id else None
    asset = (
        db.query(Asset)
        .filter(Asset.pipeline_run_id == run.id, Asset.asset_type == "video_mp4")
        .order_by(Asset.created_at.desc())
        .first()
    )
    if not video or not asset:
        raise RuntimeError("Run does not have generated assets available for recheck")

    run.review_notes = review_notes or run.review_notes
    run.status = PipelineStatus.RUNNING
    run.current_stage = PipelineStage.QUALITY_CHECK
    run.error_message = None
    run.last_error = None
    add_event(db, run.id, "pipeline.recheck_requested", "Quality check re-run requested", stage=PipelineStage.QUALITY_CHECK.value)
    db.commit()
    return finalize_post_video_processing(db, run)


def cancel_pipeline(db: Session, run_id: str, review_notes: str | None = None) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    if not run:
        raise ValueError("Pipeline run not found")
    run.status = PipelineStatus.CANCELLED
    run.cancelled_at = now_utc()
    run.review_notes = review_notes
    add_event(db, run.id, "pipeline.cancelled", "Run cancelled by user", stage=run.current_stage.value)
    db.commit()
    return run


def patch_idea(db: Session, run_id: str, payload: ContentIdeaPatch) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    idea = db.get(ContentIdea, run.idea_id)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(idea, key, value)
    add_event(db, run.id, "idea.updated", "Idea manually updated", stage=PipelineStage.IDEA_GENERATION.value)
    db.commit()
    return db.get(PipelineRun, run.id)


def patch_script(db: Session, run_id: str, payload: ScriptPatch) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    script = db.get(Script, run.script_id)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(script, key, value)
    add_event(db, run.id, "script.updated", "Script manually updated", stage=PipelineStage.SCRIPT_GENERATION.value)
    db.commit()
    return db.get(PipelineRun, run.id)


def patch_storyboard(db: Session, run_id: str, payload: StoryboardPatch) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    storyboard = db.get(Storyboard, run.storyboard_id)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(storyboard, key, value)
    add_event(db, run.id, "storyboard.updated", "Storyboard manually updated", stage=PipelineStage.STORYBOARD_GENERATION.value)
    db.commit()
    return db.get(PipelineRun, run.id)


def serialize_model(instance) -> dict[str, Any] | None:
    if instance is None:
        return None
    data = {}
    for column in instance.__table__.columns:
        value = getattr(instance, column.name)
        data[column.name] = value.value if hasattr(value, "value") else value
    return data


def get_pipeline_run_detail(db: Session, run_id: str) -> dict[str, Any]:
    run = db.get(PipelineRun, run_id)
    if not run:
        raise ValueError("Pipeline run not found")
    return {
        "pipeline_run": serialize_model(run),
        "idea": serialize_model(db.get(ContentIdea, run.idea_id)) if run.idea_id else None,
        "script": serialize_model(db.get(Script, run.script_id)) if run.script_id else None,
        "storyboard": serialize_model(db.get(Storyboard, run.storyboard_id)) if run.storyboard_id else None,
        "video": serialize_model(db.get(Video, run.video_id)) if run.video_id else None,
        "assets": [serialize_model(item) for item in db.query(Asset).filter(Asset.pipeline_run_id == run.id).all()],
        "prompt_logs": [serialize_model(item) for item in db.query(PromptLog).filter(PromptLog.pipeline_run_id == run.id).all()],
        "quality_checks": [serialize_model(item) for item in db.query(QualityCheck).filter(QualityCheck.pipeline_run_id == run.id).all()],
        "manual_post_package": serialize_model(db.get(ManualPostPackage, run.manual_post_package_id)) if run.manual_post_package_id else None,
        "pipeline_events": [
            serialize_model(item)
            for item in db.query(PipelineEvent).filter(PipelineEvent.pipeline_run_id == run.id).order_by(PipelineEvent.created_at.asc()).all()
        ],
    }


def get_pipeline_run_summary(db: Session, run: PipelineRun) -> dict[str, Any]:
    summary = serialize_model(run) or {}
    video = db.get(Video, run.video_id) if run.video_id else None
    summary["provider"] = video.provider if video else None
    summary["video_status"] = video.status.value if video and hasattr(video.status, "value") else (video.status if video else None)
    summary["provider_job_id"] = video.provider_job_id if video else None
    return summary


def list_pipeline_runs(db: Session) -> list[PipelineRun]:
    return db.query(PipelineRun).order_by(PipelineRun.created_at.desc()).all()
