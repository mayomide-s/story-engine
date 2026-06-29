from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import PipelinePriority, PipelineStage, PipelineStatus


class PipelineRunCreate(BaseModel):
    topic: str
    auto_mode: bool = False
    style_preset: str = "clean_3d_cartoon"
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


class ReviewAction(BaseModel):
    review_notes: str | None = None


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
