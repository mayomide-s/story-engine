from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import PipelinePriority, PipelineStage, PipelineStatus
from app.models.entities import ManualPostingStatus


class PipelineRunCreate(BaseModel):
    topic: str
    auto_mode: bool = False
    style_preset: str | None = None
    target_platforms: list[str] | None = None
    caption_tone: str | None = None
    duration_preference_seconds: int | None = None
    audience_level: str | None = None
    content_format: str | None = None
    priority: PipelinePriority = PipelinePriority.NORMAL


class ContentIdeaPatch(BaseModel):
    title: str | None = None
    hook: str | None = None
    concept: str | None = None
    format: str | None = None
    difficulty: str | None = None


class ScriptPatch(BaseModel):
    hook: str | None = None
    script_json: dict[str, Any] | None = None
    duration_seconds: int | None = None


class StoryboardPatch(BaseModel):
    frames_json: dict[str, Any] | None = None


class ReviewConfigPatch(BaseModel):
    style_preset: str | None = None
    prompt_override: str | None = None
    caption_override: str | None = None
    hashtag_set: list[str] | None = None
    review_sections: dict[str, str] | None = None
    ending_frame_guidance: str | None = None


class ReviewAction(BaseModel):
    review_notes: str | None = None
    confirm_paid_generation: bool = False


class StoryAdherenceRecheckPayload(BaseModel):
    review_notes: str | None = None


class HumanStoryAdherenceReviewPayload(BaseModel):
    decision: Literal["approve", "needs_review", "regenerate"]
    notes: str | None = None


class NarrationDraftCreatePayload(BaseModel):
    confirm_paid_draft: bool = False


class NarrationDraftPatchPayload(BaseModel):
    segments: list[dict[str, Any]]
    full_spoken_text: str | None = None
    estimated_word_count: int | None = None


class NarrationRenderCreatePayload(BaseModel):
    confirm_paid_narration: bool = False
    confirm_unapproved_story: bool = False
    voice: str | None = None


class NarrationSpeechRetryPayload(BaseModel):
    confirm_paid_narration: bool = False
    confirm_possible_duplicate_charge: bool = False


class NarrationHumanReviewPayload(BaseModel):
    narration_render_id: str
    decision: Literal["approve", "needs_revision", "reject"]
    notes: str | None = None


class FinalAssetSelectionPayload(BaseModel):
    source: Literal["source_video", "narration_render"]
    narration_render_id: str | None = None
    confirm_change_after_posting: bool = False


class PromptActionRequest(BaseModel):
    action: Literal["improve", "shorten"]


class ManualPostingUpdate(BaseModel):
    manual_posting_status: ManualPostingStatus | None = None
    tiktok_post_url: str | None = None
    instagram_post_url: str | None = None
    youtube_post_url: str | None = None


class PipelineRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    topic: str
    auto_mode: bool
    priority: PipelinePriority
    current_stage: PipelineStage
    status: PipelineStatus
    error_message: str | None = None
    review_notes: str | None = None
    created_at: datetime
    updated_at: datetime

class AggregatedPipelineRunResponse(BaseModel):
    pipeline_run: dict[str, Any]
    idea: dict[str, Any] | None = None
    script: dict[str, Any] | None = None
    storyboard: dict[str, Any] | None = None
    video: dict[str, Any] | None = None
    assets: list[dict[str, Any]] = Field(default_factory=list)
    prompt_logs: list[dict[str, Any]] = Field(default_factory=list)
    quality_checks: list[dict[str, Any]] = Field(default_factory=list)
    manual_post_package: dict[str, Any] | None = None
    pipeline_events: list[dict[str, Any]] = Field(default_factory=list)
    prompt_preview: str | None = None
    content_critique: dict[str, Any] | None = None
    story_adherence_review: dict[str, Any] | None = None
    narration_draft: dict[str, Any] | None = None
    latest_narration_render: dict[str, Any] | None = None
    narration_renders: list[dict[str, Any]] = Field(default_factory=list)
    final_asset_selection: dict[str, Any] | None = None
    winner_selection: dict[str, Any] | None = None
    performance_learnings_summary: dict[str, Any] | None = None
    review_sections: dict[str, str] | None = None
    review_preflight: dict[str, Any] | None = None
