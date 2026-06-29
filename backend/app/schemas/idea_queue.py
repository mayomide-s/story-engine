from typing import Any
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import IdeaQueueStatus, PipelinePriority


class IdeaQueueCreate(BaseModel):
    topic: str
    style_preset: str | None = None
    target_platform: str | None = None
    caption_tone: str | None = None
    duration_preference_seconds: int | None = None
    audience_level: str | None = None
    content_format: str | None = None
    priority: PipelinePriority = PipelinePriority.NORMAL
    status: IdeaQueueStatus = IdeaQueueStatus.DRAFT
    notes: str | None = None
    planned_date: datetime | None = None


class IdeaQueuePatch(BaseModel):
    topic: str | None = None
    style_preset: str | None = None
    target_platform: str | None = None
    caption_tone: str | None = None
    duration_preference_seconds: int | None = None
    audience_level: str | None = None
    content_format: str | None = None
    priority: PipelinePriority | None = None
    status: IdeaQueueStatus | None = None
    notes: str | None = None
    planned_date: datetime | None = None


class IdeaQueueItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    topic: str
    style_preset: str
    input_config_json: dict[str, Any]
    target_platform: str
    priority: PipelinePriority
    status: IdeaQueueStatus
    notes: str | None = None
    planned_date: datetime | None = None
    pipeline_run_id: str | None = None
    idea_score: dict[str, float | str] | None = None
    created_at: datetime
    updated_at: datetime


class IdeaQueueBatchUpdate(BaseModel):
    item_ids: list[str]
    status: IdeaQueueStatus | None = None
    target_platform: str | None = None
    style_preset: str | None = None
    priority: PipelinePriority | None = None
    planned_date: datetime | None = None
    archive_selected: bool = False


class IdeaQueueScoreRequest(BaseModel):
    item_ids: list[str]


class IdeaScoreResponse(BaseModel):
    item_id: str
    hook_strength: float
    beginner_clarity: float
    visual_potential: float
    platform_fit: float
    estimated_production_value: float
    overall_score: float
    provider: str
    model: str
