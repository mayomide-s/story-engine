from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    false,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class PipelineStage(str, enum.Enum):
    IDEA_GENERATION = "idea_generation"
    SCRIPT_GENERATION = "script_generation"
    STORYBOARD_GENERATION = "storyboard_generation"
    VIDEO_PROMPT_BUILD = "video_prompt_build"
    VIDEO_GENERATION_SUBMIT = "video_generation_submit"
    VIDEO_GENERATION_POLLING = "video_generation_polling"
    ASSET_UPLOAD = "asset_upload"
    QUALITY_CHECK = "quality_check"
    MANUAL_PACKAGE_CREATION = "manual_package_creation"
    COMPLETED = "completed"


class PipelineStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelinePriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class VideoStatus(str, enum.Enum):
    QUEUED = "queued"
    SUBMITTING = "submitting"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ManualPackageStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    ARCHIVED = "archived"


class ManualPostingStatus(str, enum.Enum):
    NOT_POSTED = "not_posted"
    POSTED_TIKTOK = "posted_tiktok"
    POSTED_INSTAGRAM = "posted_instagram"
    POSTED_YOUTUBE = "posted_youtube"
    POSTED_MULTIPLE = "posted_multiple"


class IdeaQueueStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    GENERATED = "generated"
    ARCHIVED = "archived"


class NarrationDraftStatus(str, enum.Enum):
    QUEUED = "queued"
    WRITER_GENERATING = "writer_generating"
    READY = "ready"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class NarrationRenderStatus(str, enum.Enum):
    QUEUED = "queued"
    SPEECH_GENERATING = "speech_generating"
    SPEECH_READY = "speech_ready"
    COMPOSING = "composing"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    REJECTED = "rejected"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class PerformancePlatform(str, enum.Enum):
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    OTHER = "other"


SOCIAL_CONNECTION_STATUSES = (
    "active",
    "expired",
    "revoked",
    "error",
    "disconnected",
)
PUBLICATION_JOB_STATUSES = (
    "draft",
    "ready",
    "approved",
    "active",
    "published",
    "partially_published",
    "failed",
    "cancelled",
)
PUBLICATION_TARGET_STATES = (
    "pending",
    "validating",
    "queued",
    "uploading",
    "processing",
    "uploaded_private",
    "published",
    "retryable_failure",
    "permanent_failure",
    "outcome_uncertain",
    "cancelled",
)
YOUTUBE_PUBLICATION_VISIBILITIES = (
    "private",
    "unlisted",
    "public",
)


PERFORMANCE_PLATFORM_ENUM = Enum(
    PerformancePlatform,
    values_callable=lambda enum_cls: [item.value for item in enum_cls],
    native_enum=False,
    name="performanceplatform",
)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    niche: Mapped[str] = mapped_column(String(255), nullable=False)
    account_config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    auto_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    style_preset: Mapped[str] = mapped_column(String(100), default="clean_3d_cartoon")
    input_config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    priority: Mapped[PipelinePriority] = mapped_column(Enum(PipelinePriority), default=PipelinePriority.NORMAL)
    current_stage: Mapped[PipelineStage] = mapped_column(Enum(PipelineStage), default=PipelineStage.IDEA_GENERATION)
    status: Mapped[PipelineStatus] = mapped_column(Enum(PipelineStatus), default=PipelineStatus.QUEUED)
    idea_id: Mapped[str | None] = mapped_column(ForeignKey("content_ideas.id"))
    script_id: Mapped[str | None] = mapped_column(ForeignKey("scripts.id"))
    storyboard_id: Mapped[str | None] = mapped_column(ForeignKey("storyboards.id"))
    video_id: Mapped[str | None] = mapped_column(ForeignKey("videos.id"))
    manual_post_package_id: Mapped[str | None] = mapped_column(ForeignKey("manual_post_packages.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    retry_after: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)
    review_notes: Mapped[str | None] = mapped_column(Text)
    prompt_override: Mapped[str | None] = mapped_column(Text)
    caption_override: Mapped[str | None] = mapped_column(Text)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PipelineEvent(Base):
    __tablename__ = "pipeline_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ContentIdea(Base):
    __tablename__ = "content_ideas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False)
    concept: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(100), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(50), default="beginner")
    trend_score: Mapped[int] = mapped_column(Integer, default=75)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False)
    script_json: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=25)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Storyboard(Base):
    __tablename__ = "storyboards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    frames_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_job_id: Mapped[str | None] = mapped_column(String(255))
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    provider_status: Mapped[str | None] = mapped_column(String(100))
    provider_response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    prompt_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[VideoStatus] = mapped_column(Enum(VideoStatus), default=VideoStatus.QUEUED)
    aspect_ratio: Mapped[str] = mapped_column(String(20), default="9:16")
    requested_duration_seconds: Mapped[int] = mapped_column(Integer, default=18)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=25)
    quality_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str | None] = mapped_column(String(50))
    review_notes: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    retry_after: Mapped[datetime | None] = mapped_column(DateTime)
    max_poll_attempts: Mapped[int] = mapped_column(Integer, default=20)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=15)
    provider_timeout_at: Mapped[datetime | None] = mapped_column(DateTime)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ManualPostPackage(Base):
    __tablename__ = "manual_post_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), nullable=False)
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags_json: Mapped[list] = mapped_column(JSON, default=list)
    target_platforms_json: Mapped[list] = mapped_column(JSON, default=list)
    platform_variants_json: Mapped[dict] = mapped_column(JSON, default=dict)
    checklist_json: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[ManualPackageStatus] = mapped_column(Enum(ManualPackageStatus), default=ManualPackageStatus.DRAFT)
    manual_posting_status: Mapped[ManualPostingStatus] = mapped_column(
        Enum(ManualPostingStatus),
        default=ManualPostingStatus.NOT_POSTED,
    )
    final_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    final_asset_source: Mapped[str | None] = mapped_column(String(50))
    final_narration_render_id: Mapped[str | None] = mapped_column(ForeignKey("narration_renders.id"))
    final_asset_selection_revision: Mapped[int] = mapped_column(Integer, default=1)
    final_asset_selected_at: Mapped[datetime | None] = mapped_column(DateTime)
    final_asset_metadata_json: Mapped[dict | None] = mapped_column(JSON)
    winner_platform_post_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "platform_posts.id",
            name="fk_manual_post_packages_winner_platform_post_id_platform_posts",
            ondelete="RESTRICT",
        )
    )
    winner_selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    winner_selection_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tiktok_post_url: Mapped[str | None] = mapped_column(Text)
    instagram_post_url: Mapped[str | None] = mapped_column(Text)
    youtube_post_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_stage: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    public_url: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PromptLog(Base):
    __tablename__ = "prompt_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    request_json: Mapped[dict] = mapped_column(JSON, default=dict)
    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    prompt_text: Mapped[str] = mapped_column(Text, default="")
    output_text: Mapped[str] = mapped_column(Text, default="")
    token_usage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class GenerationCost(Base):
    __tablename__ = "generation_costs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    stage: Mapped[str] = mapped_column(String(100), nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    credits_used: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class QualityCheck(Base):
    __tablename__ = "quality_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    checks_json: Mapped[dict] = mapped_column(JSON, default=dict)
    llm_critique: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class StoryAdherenceReview(Base):
    __tablename__ = "story_adherence_reviews"
    __table_args__ = (UniqueConstraint("video_id", "critic_version", name="uq_story_adherence_video_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), nullable=False)
    critic_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    review_status: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    criteria_json: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[str] = mapped_column(Text, default="")
    sampled_frames_json: Mapped[dict] = mapped_column(JSON, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class StoryAdherenceHumanReview(Base):
    __tablename__ = "story_adherence_human_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False, unique=True)
    story_adherence_review_id: Mapped[str | None] = mapped_column(ForeignKey("story_adherence_reviews.id"))
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class NarrationDraft(Base):
    __tablename__ = "narration_drafts"
    __table_args__ = (
        UniqueConstraint(
            "pipeline_run_id",
            "source_video_id",
            "narration_version",
            name="uq_narration_draft_run_source_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    source_video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), nullable=False)
    narration_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[NarrationDraftStatus] = mapped_column(Enum(NarrationDraftStatus), default=NarrationDraftStatus.QUEUED)
    has_valid_content: Mapped[bool] = mapped_column(Boolean, default=False)
    writer_task_id: Mapped[str | None] = mapped_column(String(255))
    writer_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    writer_completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    failure_stage: Mapped[str | None] = mapped_column(String(50))
    generation_revision: Mapped[int] = mapped_column(Integer, default=1)
    provider_attempt_id: Mapped[str | None] = mapped_column(String(255))
    paid_call_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    paid_call_completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    paid_call_outcome_uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    writer_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    writer_model: Mapped[str] = mapped_column(String(100), nullable=False)
    writer_prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    script_json: Mapped[dict] = mapped_column(JSON, default=dict)
    full_spoken_text: Mapped[str] = mapped_column(Text, default="")
    estimated_word_count: Mapped[int] = mapped_column(Integer, default=0)
    source_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_writer_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts_json: Mapped[list] = mapped_column(JSON, default=list)
    manually_modified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class NarrationRender(Base):
    __tablename__ = "narration_renders"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_narration_render_idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    narration_draft_id: Mapped[str] = mapped_column(ForeignKey("narration_drafts.id"), nullable=False)
    source_video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), nullable=False)
    narration_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[NarrationRenderStatus] = mapped_column(Enum(NarrationRenderStatus), default=NarrationRenderStatus.QUEUED)
    worker_task_id: Mapped[str | None] = mapped_column(String(255))
    speech_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    speech_completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    failure_stage: Mapped[str | None] = mapped_column(String(50))
    provider_attempt_id: Mapped[str | None] = mapped_column(String(255))
    paid_call_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    paid_call_completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    provider_request_dispatched: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_call_outcome_uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    failure_kind: Mapped[str | None] = mapped_column(String(50))
    writer_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    writer_model: Mapped[str] = mapped_column(String(100), nullable=False)
    writer_prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    speech_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    speech_model: Mapped[str] = mapped_column(String(100), nullable=False)
    voice: Mapped[str] = mapped_column(String(100), nullable=False)
    voice_is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    caption_version: Mapped[str] = mapped_column(String(100), nullable=False)
    render_version: Mapped[str] = mapped_column(String(100), nullable=False)
    script_json: Mapped[dict] = mapped_column(JSON, default=dict)
    full_spoken_text: Mapped[str] = mapped_column(Text, default="")
    caption_cues_json: Mapped[list] = mapped_column(JSON, default=list)
    caption_source_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    usable_narration_window_seconds: Mapped[float | None] = mapped_column(Float)
    original_audio_duration_seconds: Mapped[float | None] = mapped_column(Float)
    final_audio_duration_seconds: Mapped[float | None] = mapped_column(Float)
    applied_atempo_factor: Mapped[float | None] = mapped_column(Float)
    narration_duration_seconds: Mapped[float | None] = mapped_column(Float)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    usage_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    speech_attempts_json: Mapped[list] = mapped_column(JSON, default=list)
    estimated_writer_cost: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_speech_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    audio_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    caption_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    rendered_video_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    human_review_status: Mapped[str | None] = mapped_column(String(50))
    human_review_notes: Mapped[str | None] = mapped_column(Text)
    human_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    story_approval_status_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    story_approval_source_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    ai_voice_disclosure: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PlatformPost(Base):
    __tablename__ = "platform_posts"
    __table_args__ = (
        UniqueConstraint("platform", "post_url", name="uq_platform_posts_platform_post_url"),
        CheckConstraint(
            "(platform = 'other' AND custom_platform_name IS NOT NULL AND length(trim(custom_platform_name)) > 0) "
            "OR (platform != 'other' AND custom_platform_name IS NULL)",
            name="ck_platform_posts_custom_platform_name",
        ),
        Index("ix_platform_posts_pipeline_run_id", "pipeline_run_id"),
        Index("ix_platform_posts_manual_post_package_id", "manual_post_package_id"),
        Index("ix_platform_posts_platform", "platform"),
        Index("ix_platform_posts_posted_at", "posted_at"),
        Index("ix_platform_posts_final_asset_id", "final_asset_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    manual_post_package_id: Mapped[str] = mapped_column(ForeignKey("manual_post_packages.id"), nullable=False)
    final_asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)
    final_asset_source: Mapped[str] = mapped_column(String(50), nullable=False)
    platform: Mapped[PerformancePlatform] = mapped_column(PERFORMANCE_PLATFORM_ENUM, nullable=False)
    post_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    custom_platform_name: Mapped[str | None] = mapped_column(String(80))
    final_narration_render_id: Mapped[str | None] = mapped_column(ForeignKey("narration_renders.id"))
    final_asset_selection_revision: Mapped[int | None] = mapped_column(Integer)
    final_asset_metadata_json: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class PerformanceSnapshot(Base):
    __tablename__ = "performance_snapshots"
    __table_args__ = (
        UniqueConstraint("platform_post_id", "captured_at", name="uq_performance_snapshots_post_captured_at"),
        CheckConstraint("views IS NULL OR views >= 0", name="ck_performance_snapshots_views_non_negative"),
        CheckConstraint("likes IS NULL OR likes >= 0", name="ck_performance_snapshots_likes_non_negative"),
        CheckConstraint("comments IS NULL OR comments >= 0", name="ck_performance_snapshots_comments_non_negative"),
        CheckConstraint("shares IS NULL OR shares >= 0", name="ck_performance_snapshots_shares_non_negative"),
        CheckConstraint("saves IS NULL OR saves >= 0", name="ck_performance_snapshots_saves_non_negative"),
        CheckConstraint(
            "average_watch_time_seconds IS NULL OR average_watch_time_seconds >= 0",
            name="ck_performance_snapshots_watch_time_non_negative",
        ),
        CheckConstraint(
            "completion_rate IS NULL OR (completion_rate >= 0 AND completion_rate <= 1)",
            name="ck_performance_snapshots_completion_rate_range",
        ),
        CheckConstraint(
            "followers_gained IS NULL OR followers_gained >= 0",
            name="ck_performance_snapshots_followers_gained_non_negative",
        ),
        Index("ix_performance_snapshots_post_captured_at", "platform_post_id", "captured_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    platform_post_id: Mapped[str] = mapped_column(ForeignKey("platform_posts.id"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    views: Mapped[int | None] = mapped_column(BigInteger)
    likes: Mapped[int | None] = mapped_column(BigInteger)
    comments: Mapped[int | None] = mapped_column(BigInteger)
    shares: Mapped[int | None] = mapped_column(BigInteger)
    saves: Mapped[int | None] = mapped_column(BigInteger)
    average_watch_time_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3))
    completion_rate: Mapped[float | None] = mapped_column(Numeric(6, 5))
    followers_gained: Mapped[int | None] = mapped_column(BigInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PerformanceLearning(Base):
    __tablename__ = "performance_learnings"
    __table_args__ = (
        CheckConstraint(
            "learning_type IN ('worked', 'did_not_work', 'next_test', 'observation')",
            name="ck_performance_learnings_learning_type",
        ),
        Index("ix_performance_learnings_pipeline_run_id", "pipeline_run_id"),
        Index("ix_performance_learnings_platform_post_id", "platform_post_id"),
        Index("ix_performance_learnings_learning_type", "learning_type"),
        Index(
            "ix_performance_learnings_run_archived_updated",
            "pipeline_run_id",
            "is_archived",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(
        ForeignKey(
            "pipeline_runs.id",
            name="fk_performance_learnings_pipeline_run_id_pipeline_runs",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    platform_post_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "platform_posts.id",
            name="fk_performance_learnings_platform_post_id_platform_posts",
            ondelete="RESTRICT",
        )
    )
    learning_type: Mapped[str] = mapped_column(String(50), nullable=False)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class SocialConnection(Base):
    __tablename__ = "social_connections"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "platform",
            "external_account_id",
            name="uq_social_connections_account_platform_external",
        ),
        CheckConstraint(
            f"connection_status IN {SOCIAL_CONNECTION_STATUSES}",
            name="ck_social_connections_connection_status",
        ),
        Index("ix_social_connections_account_platform", "account_id", "platform"),
        Index("ix_social_connections_status", "connection_status"),
        Index("ix_social_connections_platform_default", "platform", "is_default"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255))
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text)
    token_cipher_version: Mapped[str | None] = mapped_column(String(20))
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    granted_scopes_json: Mapped[list] = mapped_column(JSON, default=list)
    connection_status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    provider_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class OAuthState(Base):
    __tablename__ = "oauth_states"
    __table_args__ = (
        UniqueConstraint("state_hash", name="uq_oauth_states_state_hash"),
        Index("ix_oauth_states_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    return_path: Mapped[str | None] = mapped_column(String(1024))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PublicationJob(Base):
    __tablename__ = "publication_jobs"
    __table_args__ = (
        CheckConstraint(
            f"status IN {PUBLICATION_JOB_STATUSES}",
            name="ck_publication_jobs_status",
        ),
        Index("ix_publication_jobs_pipeline_run_id", "pipeline_run_id"),
        Index("ix_publication_jobs_status", "status"),
        Index("ix_publication_jobs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="RESTRICT"), nullable=False)
    manual_post_package_id: Mapped[str] = mapped_column(ForeignKey("manual_post_packages.id", ondelete="RESTRICT"), nullable=False)
    final_asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False)
    final_asset_selection_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    final_asset_source: Mapped[str] = mapped_column(String(50), nullable=False)
    final_asset_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    final_asset_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class PublicationTarget(Base):
    __tablename__ = "publication_targets"
    __table_args__ = (
        UniqueConstraint(
            "publication_job_id",
            "platform",
            "social_connection_id",
            name="uq_publication_targets_job_platform_connection",
        ),
        UniqueConstraint("idempotency_key", name="uq_publication_targets_idempotency_key"),
        CheckConstraint(
            f"state IN {PUBLICATION_TARGET_STATES}",
            name="ck_publication_targets_state",
        ),
        CheckConstraint(
            f"visibility IN {YOUTUBE_PUBLICATION_VISIBILITIES}",
            name="ck_publication_targets_visibility",
        ),
        CheckConstraint(
            f"actual_visibility IS NULL OR actual_visibility IN {YOUTUBE_PUBLICATION_VISIBILITIES}",
            name="ck_publication_targets_actual_visibility",
        ),
        CheckConstraint(
            "upload_bytes_total IS NULL OR upload_bytes_total >= 0",
            name="ck_publication_targets_upload_bytes_total_non_negative",
        ),
        CheckConstraint(
            "upload_bytes_sent IS NULL OR upload_bytes_sent >= 0",
            name="ck_publication_targets_upload_bytes_sent_non_negative",
        ),
        UniqueConstraint("platform_post_id", name="uq_publication_targets_platform_post_id"),
        Index("ix_publication_targets_publication_job_id", "publication_job_id"),
        Index("ix_publication_targets_state", "state"),
        Index("ix_publication_targets_next_poll_at", "next_poll_at"),
        Index("ix_publication_targets_provider_submission_id", "provider_submission_id"),
        Index("ix_publication_targets_provider_media_id", "provider_media_id"),
        Index("ix_publication_targets_platform_post_id", "platform_post_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    publication_job_id: Mapped[str] = mapped_column(ForeignKey("publication_jobs.id", ondelete="RESTRICT"), nullable=False)
    social_connection_id: Mapped[str] = mapped_column(ForeignKey("social_connections.id", ondelete="RESTRICT"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False)
    actual_visibility: Mapped[str | None] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text)
    tags_json: Mapped[list] = mapped_column(JSON, default=list)
    options_json: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_upload_uri_encrypted: Mapped[str | None] = mapped_column(Text)
    provider_submission_id: Mapped[str | None] = mapped_column(String(255))
    provider_media_id: Mapped[str | None] = mapped_column(String(255))
    provider_upload_status: Mapped[str | None] = mapped_column(String(50))
    provider_processing_status: Mapped[str | None] = mapped_column(String(50))
    public_post_url: Mapped[str | None] = mapped_column(Text)
    platform_post_id: Mapped[str | None] = mapped_column(ForeignKey("platform_posts.id", ondelete="RESTRICT"))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    upload_bytes_total: Mapped[int | None] = mapped_column(BigInteger)
    upload_bytes_sent: Mapped[int | None] = mapped_column(BigInteger)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    worker_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_claim_token: Mapped[str | None] = mapped_column(String(64))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class IdeaQueueItem(Base):
    __tablename__ = "idea_queue_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    style_preset: Mapped[str] = mapped_column(String(100), default="clean_3d_cartoon")
    input_config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    target_platform: Mapped[str] = mapped_column(String(50), default="instagram")
    priority: Mapped[PipelinePriority] = mapped_column(Enum(PipelinePriority), default=PipelinePriority.NORMAL)
    status: Mapped[IdeaQueueStatus] = mapped_column(Enum(IdeaQueueStatus), default=IdeaQueueStatus.DRAFT)
    notes: Mapped[str | None] = mapped_column(Text)
    planned_date: Mapped[datetime | None] = mapped_column(DateTime)
    pipeline_run_id: Mapped[str | None] = mapped_column(ForeignKey("pipeline_runs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
