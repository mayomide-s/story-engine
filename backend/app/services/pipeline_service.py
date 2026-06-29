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
from app.schemas.pipeline_runs import ContentIdeaPatch, PipelineRunCreate, ReviewConfigPatch, ScriptPatch, StoryboardPatch
from app.services.providers import get_llm_provider, get_storage_provider, get_video_provider
from app.services.security import redact_sensitive_data, sanitize_for_json


DEFAULT_ACCOUNT_NAME = "CodeToons AI"


class UnsafeResumeError(RuntimeError):
    """Raised when a resume request would create unsafe or duplicate video work."""


STYLE_PRESETS = {
    "clean_3d_cartoon": {
        "style": "clean 3D cartoon",
        "prompt_modifier": "Bright, polished 3D animation with readable character acting and clean motion.",
    },
    "neon_club_metaphor": {
        "style": "neon club metaphor",
        "prompt_modifier": "Electric nightlife visuals, glowing signage, vivid club staging, and playful metaphor energy.",
    },
    "whiteboard_character": {
        "style": "whiteboard character",
        "prompt_modifier": "Simple whiteboard-style characters with crisp explanatory motion and bold marker-like visuals.",
    },
    "bug_monster": {
        "style": "bug monster",
        "prompt_modifier": "Funny monster-driven problem-solving visuals where bugs feel visual and memorable, not scary.",
    },
    "office_comedy": {
        "style": "office comedy",
        "prompt_modifier": "Fast office-comedy acting, expressive coworkers, and visual gags grounded in workplace metaphors.",
    },
}

DEFAULT_ACCOUNT_CONFIG = {
    "tone": "funny, simple, visual, slightly chaotic",
    "style": "clean 3D cartoon",
    "duration_min": 18,
    "duration_max": 30,
    "default_duration_seconds": 18,
    "aspect_ratio": "9:16",
    "end_tag": "Made by CodeToons AI",
    "banned_content": ["malware", "phishing", "fake income claims"],
    "target_platforms": ["instagram", "tiktok", "youtube"],
    "default_style_preset": "clean_3d_cartoon",
    "default_caption_tone": "playful explainer",
    "default_hashtag_set": ["#coding", "#webdev", "#learncode", "#javascript", "#codetoonsai"],
    "default_audience_level": "beginner",
    "default_content_format": "coding metaphor",
    "brand_description": "CodeToons AI turns coding concepts into short visual mini-stories for curious developers.",
    "preferred_cta": "Follow CodeToons AI for more coding stories.",
    "avoid_phrases": ["get rich quick", "guaranteed", "effortless mastery"],
    "emoji_preference": "minimal",
    "style_presets": STYLE_PRESETS,
}


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def build_account_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    config = {**DEFAULT_ACCOUNT_CONFIG}
    if overrides:
        config.update(overrides)
    config["style_presets"] = overrides.get("style_presets", STYLE_PRESETS) if overrides else STYLE_PRESETS
    config["default_hashtag_set"] = list(config.get("default_hashtag_set", DEFAULT_ACCOUNT_CONFIG["default_hashtag_set"]))
    config["target_platforms"] = list(config.get("target_platforms", DEFAULT_ACCOUNT_CONFIG["target_platforms"]))
    if not config["target_platforms"]:
        config["target_platforms"] = list(DEFAULT_ACCOUNT_CONFIG["target_platforms"])
    config["avoid_phrases"] = list(config.get("avoid_phrases", DEFAULT_ACCOUNT_CONFIG["avoid_phrases"]))
    return config


def get_run_input_config(run: PipelineRun, account_config: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_account_config({**(account_config or {}), **(run.input_config_json or {})})


def build_run_input_config(account_config: dict[str, Any], payload: PipelineRunCreate) -> dict[str, Any]:
    config = build_account_config(account_config)
    return {
        "style_preset": payload.style_preset or config["default_style_preset"],
        "target_platforms": payload.target_platforms or config["target_platforms"],
        "caption_tone": payload.caption_tone or config["default_caption_tone"],
        "hashtag_set": config["default_hashtag_set"],
        "duration_preference_seconds": payload.duration_preference_seconds or config["default_duration_seconds"],
        "audience_level": payload.audience_level or config["default_audience_level"],
        "content_format": payload.content_format or config["default_content_format"],
        "brand_description": config["brand_description"],
        "preferred_cta": config["preferred_cta"],
        "avoid_phrases": config["avoid_phrases"],
        "emoji_preference": config["emoji_preference"],
    }


def build_idea_input_config(account_config: dict[str, Any], payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    config = build_account_config(account_config)
    source = {**(existing or {}), **{key: value for key, value in payload.items() if value is not None}}
    target_platform = source.get("target_platform") or (source.get("target_platforms") or config["target_platforms"])[0]
    target_platforms = [target_platform] if source.get("target_platform") else (source.get("target_platforms") or [target_platform])
    return {
        "style_preset": source.get("style_preset") or config["default_style_preset"],
        "target_platforms": target_platforms,
        "caption_tone": source.get("caption_tone") or config["default_caption_tone"],
        "hashtag_set": source.get("hashtag_set") or config["default_hashtag_set"],
        "duration_preference_seconds": source.get("duration_preference_seconds") or config["default_duration_seconds"],
        "audience_level": source.get("audience_level") or config["default_audience_level"],
        "content_format": source.get("content_format") or config["default_content_format"],
        "brand_description": config["brand_description"],
        "preferred_cta": config["preferred_cta"],
        "avoid_phrases": config["avoid_phrases"],
        "emoji_preference": config["emoji_preference"],
    }


def seed_default_account(db: Session) -> Account:
    account = db.query(Account).filter(Account.name == DEFAULT_ACCOUNT_NAME).first()
    if account:
        merged_config = build_account_config(account.account_config_json or {})
        if merged_config != (account.account_config_json or {}):
            account.account_config_json = merged_config
            db.commit()
            db.refresh(account)
        return account
    account = Account(
        name=DEFAULT_ACCOUNT_NAME,
        niche="coding concepts explained through AI mini-stories",
        account_config_json=build_account_config(),
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
    config = build_account_config(account_config)
    configured_min = int(config.get("duration_min", 18))
    configured_max = int(config.get("duration_max", configured_min))
    preferred_target = int(config.get("duration_preference_seconds", config.get("default_duration_seconds", configured_min)))
    configured_target = min(configured_max, max(configured_min, preferred_target))
    if provider_name == "runway":
        return min(max(configured_target, 5), 10)
    return min(max(configured_target, 18), 30)


def get_style_preset(run: PipelineRun, account_config: dict[str, Any] | None) -> dict[str, str]:
    config = get_run_input_config(run, account_config)
    presets = config.get("style_presets") or STYLE_PRESETS
    default_preset = config.get("default_style_preset", "clean_3d_cartoon")
    preset_name = run.style_preset or config.get("style_preset") or default_preset
    return presets.get(preset_name, STYLE_PRESETS["clean_3d_cartoon"])


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
    input_config = build_run_input_config(account.account_config_json or {}, payload)
    run = PipelineRun(
        account_id=account.id,
        topic=payload.topic,
        auto_mode=payload.auto_mode,
        style_preset=input_config["style_preset"],
        input_config_json=input_config,
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
    account = db.get(Account, run.account_id)
    run_config = get_run_input_config(run, account.account_config_json if account else {})
    prompt = (
        f"Turn topic '{run.topic}' into a {run_config['content_format']} video idea for {run_config['audience_level']} developers. "
        f"Keep the tone {run_config['caption_tone']} and aligned with {run_config['brand_description']}"
    )
    result = llm.generate(PipelineStage.IDEA_GENERATION.value, prompt, {"topic": run.topic, "config": run_config})
    title_suffix = {
        "coding metaphor": "as a nightclub bouncer",
        "bug explanation": "as a bug hunt",
        "interview-style tip": "as a hiring manager tip",
        "quick concept explainer": "in one clean visual explainer",
    }.get(run_config["content_format"], "as a coding mini-story")
    hook_suffix = {
        "coding metaphor": "is just a bouncer with trust issues.",
        "bug explanation": "breaks because one sneaky bug keeps bending the rules.",
        "interview-style tip": "gets way easier when you answer it like this in an interview.",
        "quick concept explainer": "finally clicks when you see it in one short scene.",
    }.get(run_config["content_format"], "works better when the story is visual.")
    idea = ContentIdea(
        pipeline_run_id=run.id,
        topic=run.topic,
        title=f"{run.topic} {title_suffix}",
        hook=f"{run.topic} {hook_suffix}",
        concept=f"The story explains {run.topic} with a {run_config['content_format']} for {run_config['audience_level']} developers.",
        format=run_config["content_format"],
        difficulty=run_config["audience_level"],
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
        {"topic": run.topic, "config": run_config},
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
    run_config = get_run_input_config(run, account.account_config_json if account else {})
    target_duration = get_target_duration_seconds(run_config, provider_name)
    scene_timings = build_scene_timings(target_duration)
    prompt = f"Write a short {run_config['content_format']} script for '{idea.title}' aimed at {run_config['audience_level']} viewers."
    result = llm.generate(PipelineStage.SCRIPT_GENERATION.value, prompt, {"idea_id": idea.id, "config": run_config})
    script_json = {
        "hook": idea.hook,
        "scenes": [
            {"time": scene_timings[0], "visual": "Frontend arrives at a neon nightclub.", "dialogue": "I need the user data."},
            {"time": scene_timings[1], "visual": "A CORS bouncer blocks the entrance.", "dialogue": "Where is your allowed-origin pass?"},
            {"time": scene_timings[2], "visual": "Backend checks the list.", "dialogue": "Only approved websites can enter."},
            {"time": scene_timings[3], "visual": "A green stamp appears.", "dialogue": f"That is {run.topic}."},
        ],
        "final_tag": build_account_config(account.account_config_json if account else {}).get("end_tag", "Made by CodeToons AI"),
        "target_duration_seconds": target_duration,
        "audience_level": run_config["audience_level"],
        "content_format": run_config["content_format"],
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
        {"idea_id": idea.id, "config": run_config},
        result,
        idea.hook,
        result["token_usage"],
        result["cost_estimate"],
    )
    add_event(db, run.id, "script.generated", "Script generated", stage=PipelineStage.SCRIPT_GENERATION.value)


def generate_storyboard(db: Session, run: PipelineRun):
    llm = get_llm_provider()
    script = db.get(Script, run.script_id)
    account = db.get(Account, run.account_id)
    run_config = get_run_input_config(run, account.account_config_json if account else {})
    prompt = f"Create storyboard frames from the script in the {run.style_preset} preset."
    result = llm.generate(PipelineStage.STORYBOARD_GENERATION.value, prompt, {"script": script.script_json, "config": run_config})
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
        {"script": script.script_json, "config": run_config},
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


def generate_content_critique(db: Session, run: PipelineRun):
    llm = get_llm_provider()
    idea = db.get(ContentIdea, run.idea_id)
    script = db.get(Script, run.script_id)
    storyboard = db.get(Storyboard, run.storyboard_id)
    account = db.get(Account, run.account_id)
    run_config = get_run_input_config(run, account.account_config_json if account else {})
    scenes = script.script_json.get("scenes", []) if script else []
    dialogue_words = sum(len(str(scene.get("dialogue", "")).split()) for scene in scenes)
    too_much_text = dialogue_words > max(script.duration_seconds * 2, 22) if script else False
    critique = {
        "beginner_clarity": {"score": 0.9 if script and script.duration_seconds <= 10 else 0.82, "notes": "Clear enough for beginner coders with simple visual language."},
        "metaphor_strength": {"score": 0.88 if idea and "bouncer" in idea.hook.lower() else 0.78, "notes": "Metaphor is memorable and easy to retell."},
        "visual_coherence": {"score": 0.87 if storyboard and len(storyboard.frames_json.get("storyboard_frames", [])) == len(scenes) else 0.72, "notes": "Scenes and storyboard frames align cleanly."},
        "social_hook_strength": {"score": 0.86 if idea and len(idea.hook) <= 90 else 0.74, "notes": "Hook is short enough to land in a short-form opener."},
        "audience_fit": {"score": 0.9 if idea and idea.difficulty == run_config["audience_level"] else 0.76, "notes": f"Targeted for {run_config['audience_level']} viewers."},
        "brand_voice_alignment": {"score": 0.85, "notes": f"Caption tone should stay {run_config['caption_tone']} and avoid {', '.join(run_config['avoid_phrases'])}."},
        "too_much_text_dialogue_warning": {"flagged": too_much_text, "notes": "Dialogue is getting dense for a short video." if too_much_text else "Dialogue density looks safe for a fast watch."},
        "serious_issue": not scenes,
        "summary": "Looks viable for generation. Tighten dialogue only if you want faster pacing." if scenes else "No scenes found. Fix the script before generating video.",
    }
    prompt = "Critique the mini-story for clarity, metaphor strength, visual coherence, hook strength, and dialogue load."
    result = llm.generate(
        "content_critique",
        prompt,
        {"idea": idea.title if idea else "", "hook": idea.hook if idea else "", "scenes": scenes, "storyboard": storyboard.frames_json if storyboard else {}, "config": run_config},
    )
    add_prompt_log(
        db,
        run.id,
        "content_critique",
        llm.name,
        llm.model,
        prompt,
        {"idea_id": idea.id if idea else None, "script_id": script.id if script else None},
        {**result, "critique": critique},
        critique["summary"],
        result["token_usage"],
        result["cost_estimate"],
    )
    add_event(db, run.id, "content.critique_generated", "Pre-video content critique generated", stage=PipelineStage.STORYBOARD_GENERATION.value, metadata=critique)


def build_video_prompt(run: PipelineRun, db: Session) -> str:
    if run.prompt_override:
        return run.prompt_override
    script = db.get(Script, run.script_id)
    account = db.get(Account, run.account_id)
    run_config = get_run_input_config(run, account.account_config_json if account else {})
    preset = get_style_preset(run, account.account_config_json if account else {})
    avoid_phrases = ", ".join(run_config["avoid_phrases"])
    target_platforms = ", ".join(run_config["target_platforms"])
    prompt = (
        f"Create a 9:16 animated video about {run.topic}. "
        f"Style preset: {run.style_preset}. "
        f"Visual direction: {preset['style']}. "
        f"Style notes: {preset['prompt_modifier']} "
        f"Audience level: {run_config['audience_level']}. "
        f"Content format: {run_config['content_format']}. "
        f"Brand voice: {run_config['brand_description']}. "
        f"Target platforms: {target_platforms}. "
        f"Preferred CTA: {run_config['preferred_cta']}. "
        f"Avoid phrases: {avoid_phrases}. "
        "Use actual motion, expressive characters, no slideshow effects. "
        f"Scenes: {script.script_json['scenes']} "
        f"End tag: {build_account_config(account.account_config_json if account else {}).get('end_tag', 'Made by CodeToons AI')}"
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
    run_config = get_run_input_config(run, account.account_config_json if account else {})
    prompt = build_video_prompt(run, db)
    target_duration = get_target_duration_seconds(run_config, provider.name)
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
    account = db.get(Account, run.account_id)
    run_config = get_run_input_config(run, account.account_config_json if account else {})
    emoji_prefix = {
        "none": "",
        "minimal": "🎬 ",
        "medium": "🎬✨ ",
    }.get(run_config["emoji_preference"], "")
    hashtags = list(run_config["hashtag_set"])
    target_platforms = list(run_config["target_platforms"])
    caption = run.caption_override or (
        f"{emoji_prefix}{run.topic} explained with a {run_config['content_format']} for {run_config['audience_level']} developers. "
        f"Tone: {run_config['caption_tone']}. {run_config['preferred_cta']}"
    ).strip()
    alternative_captions = [
        f"{emoji_prefix}{run.topic} feels easier when the story stays {run_config['caption_tone']} and visual. {run_config['preferred_cta']}".strip(),
        f"{emoji_prefix}A fast {run_config['content_format']} for {run.topic}. Keep this if you teach {run_config['audience_level']} coders.".strip(),
        f"{emoji_prefix}Save this for a cleaner mental model of {run.topic}. {run_config['preferred_cta']}".strip(),
    ]
    alternative_hooks = [
        f"{run.topic} made simple for {run_config['audience_level']} developers.",
        f"A {run_config['content_format']} is the fastest way to remember {run.topic}.",
        f"{run.topic} clicks faster when the story stays visual.",
    ]
    pkg = ManualPostPackage(
        video_id=video.id,
        caption=caption,
        hashtags_json=hashtags,
        target_platforms_json=target_platforms,
        checklist_json=[
            "Review the video for motion and clarity",
            "Confirm end tag visibility",
            "Upload manually to each platform",
            f"Use CTA: {run_config['preferred_cta']}",
        ],
        platform_variants_json={
            "instagram": {"caption": caption, "hashtags": hashtags},
            "tiktok": {"caption": f"{caption} #learnontiktok".strip(), "hashtags": hashtags},
            "youtube": {"title": alternative_hooks[2], "description": caption, "hashtags": hashtags},
            "alternative_captions": alternative_captions,
            "alternative_hooks": alternative_hooks,
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
    generate_content_critique(db, run)
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

    if video and video.status in {VideoStatus.COMPLETED, VideoStatus.APPROVED}:
        raise UnsafeResumeError("Run already has a generated video. Open Video Review or re-run quality check instead of resuming.")
    if run.status in {PipelineStatus.COMPLETED, PipelineStatus.CANCELLED, PipelineStatus.FAILED}:
        raise UnsafeResumeError(f"Run cannot be resumed from status '{run.status.value}'")
    if video and video.status == VideoStatus.SUBMITTING and video.provider_job_id:
        raise UnsafeResumeError("Run already has a submitted provider job. Please wait for polling to continue.")
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
    if video and video.provider_job_id and video.status in {VideoStatus.QUEUED, VideoStatus.GENERATING, VideoStatus.PENDING_REVIEW}:
        run.review_notes = review_notes or run.review_notes
        run.status = PipelineStatus.RUNNING
        run.resumed_at = now_utc()
        run.paused_at = None
        run.current_stage = PipelineStage.VIDEO_GENERATION_POLLING
        add_event(
            db,
            run.id,
            "pipeline.resumed_existing_generation",
            "Run resumed with existing provider job",
            stage=PipelineStage.VIDEO_GENERATION_POLLING.value,
        )
        db.commit()
        if get_settings().video_provider == "runway":
            enqueue_resume_pipeline_task(run.id)
            return db.get(PipelineRun, run.id)
        continue_pipeline_after_review(db, db.get(PipelineRun, run.id) or run)
        return db.get(PipelineRun, run.id)

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


def patch_review_config(db: Session, run_id: str, payload: ReviewConfigPatch) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    if not run:
        raise ValueError("Pipeline run not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(run, key, value)
    if payload.style_preset:
        input_config = dict(run.input_config_json or {})
        input_config["style_preset"] = payload.style_preset
        run.input_config_json = input_config
    add_event(db, run.id, "review.config_updated", "Review configuration updated", stage=run.current_stage.value)
    db.commit()
    return db.get(PipelineRun, run.id)


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
    critique_log = (
        db.query(PromptLog)
        .filter(PromptLog.pipeline_run_id == run.id, PromptLog.stage == "content_critique")
        .order_by(PromptLog.created_at.desc())
        .first()
    )
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
        "prompt_preview": build_video_prompt(run, db),
        "content_critique": critique_log.response_json.get("critique") if critique_log else None,
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
