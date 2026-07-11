from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ALLOWED_PLATFORMS = {"tiktok", "instagram", "youtube", "other"}
ALLOWED_LEARNING_TYPES = {"worked", "did_not_work", "next_test", "observation"}


def _normalize_url(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Post URL may not be blank.")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Post URL must use http or https.")
    if not parsed.hostname:
        raise ValueError("Post URL must include a hostname.")
    if parsed.username or parsed.password:
        raise ValueError("Post URL may not include embedded credentials.")
    return normalized


def _normalize_custom_platform_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 80:
        raise ValueError("Custom platform name must be 80 characters or fewer.")
    return normalized


def _normalize_learning_text(value: str | None, *, required: bool, field_label: str) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field_label} is required.")
        return None
    normalized = value.strip()
    if not normalized:
        if required:
            raise ValueError(f"{field_label} is required.")
        return None
    if len(normalized) > 2000:
        raise ValueError(f"{field_label} must be 2000 characters or fewer.")
    return normalized


class PlatformPostCreatePayload(BaseModel):
    platform: str
    post_url: str
    posted_at: datetime
    custom_platform_name: str | None = None
    notes: str | None = None

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_PLATFORMS:
            raise ValueError("Platform must be tiktok, instagram, youtube, or other.")
        return normalized

    @field_validator("post_url")
    @classmethod
    def validate_post_url(cls, value: str) -> str:
        return _normalize_url(value)

    @field_validator("custom_platform_name")
    @classmethod
    def validate_custom_platform_name(cls, value: str | None) -> str | None:
        return _normalize_custom_platform_name(value)

    @model_validator(mode="after")
    def validate_other_platform_rules(self) -> "PlatformPostCreatePayload":
        if self.platform == "other" and not self.custom_platform_name:
            raise ValueError("custom_platform_name is required when platform is other.")
        if self.platform != "other" and self.custom_platform_name is not None:
            raise ValueError("custom_platform_name must be null unless platform is other.")
        if self.posted_at.tzinfo is None or self.posted_at.utcoffset() is None:
            raise ValueError("posted_at must include a timezone offset.")
        return self


class PlatformPostUpdatePayload(BaseModel):
    platform: str | None = None
    post_url: str | None = None
    posted_at: datetime | None = None
    custom_platform_name: str | None = None
    notes: str | None = None

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in ALLOWED_PLATFORMS:
            raise ValueError("Platform must be tiktok, instagram, youtube, or other.")
        return normalized

    @field_validator("post_url")
    @classmethod
    def validate_post_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_url(value)

    @field_validator("custom_platform_name")
    @classmethod
    def validate_custom_platform_name(cls, value: str | None) -> str | None:
        return _normalize_custom_platform_name(value)

    @model_validator(mode="after")
    def validate_other_platform_rules(self) -> "PlatformPostUpdatePayload":
        platform = self.platform
        custom_name = self.custom_platform_name
        if platform == "other" and not custom_name:
            raise ValueError("custom_platform_name is required when platform is other.")
        if platform in {"tiktok", "instagram", "youtube"} and custom_name is not None:
            raise ValueError("custom_platform_name must be null unless platform is other.")
        if self.posted_at is not None and (self.posted_at.tzinfo is None or self.posted_at.utcoffset() is None):
            raise ValueError("posted_at must include a timezone offset.")
        return self


class PerformanceSnapshotCreatePayload(BaseModel):
    captured_at: datetime
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    saves: int | None = None
    average_watch_time_seconds: Decimal | None = None
    completion_rate: Decimal | None = None
    followers_gained: int | None = None
    notes: str | None = None

    @field_validator("views", "likes", "comments", "shares", "saves", "followers_gained")
    @classmethod
    def validate_non_negative_int(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("Metrics may not be negative.")
        return value

    @field_validator("average_watch_time_seconds")
    @classmethod
    def validate_non_negative_watch_time(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value < 0:
            raise ValueError("average_watch_time_seconds may not be negative.")
        return value

    @field_validator("completion_rate")
    @classmethod
    def validate_completion_rate(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (value < 0 or value > 1):
            raise ValueError("completion_rate must be between 0 and 1.")
        return value

    @model_validator(mode="after")
    def validate_snapshot(self) -> "PerformanceSnapshotCreatePayload":
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must include a timezone offset.")
        metric_values = [
            self.views,
            self.likes,
            self.comments,
            self.shares,
            self.saves,
            self.average_watch_time_seconds,
            self.completion_rate,
            self.followers_gained,
        ]
        if not any(value is not None for value in metric_values):
            raise ValueError("At least one metric value is required.")
        return self


class PerformanceLearningCreatePayload(BaseModel):
    learning_type: str
    observation: str
    evidence: str | None = None
    next_action: str | None = None
    platform_post_id: UUID | None = None

    @field_validator("learning_type")
    @classmethod
    def validate_learning_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_LEARNING_TYPES:
            raise ValueError("learning_type must be worked, did_not_work, next_test, or observation.")
        return normalized

    @field_validator("observation")
    @classmethod
    def validate_observation(cls, value: str) -> str:
        return _normalize_learning_text(value, required=True, field_label="observation") or ""

    @field_validator("evidence")
    @classmethod
    def validate_evidence(cls, value: str | None) -> str | None:
        return _normalize_learning_text(value, required=False, field_label="evidence")

    @field_validator("next_action")
    @classmethod
    def validate_next_action(cls, value: str | None) -> str | None:
        return _normalize_learning_text(value, required=False, field_label="next_action")


class PerformanceLearningPatchPayload(BaseModel):
    learning_type: str | None = None
    observation: str | None = None
    evidence: str | None = None
    next_action: str | None = None
    platform_post_id: UUID | None = None

    @field_validator("learning_type")
    @classmethod
    def validate_learning_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in ALLOWED_LEARNING_TYPES:
            raise ValueError("learning_type must be worked, did_not_work, next_test, or observation.")
        return normalized

    @field_validator("observation")
    @classmethod
    def validate_observation(cls, value: str | None) -> str | None:
        return _normalize_learning_text(value, required=False, field_label="observation")

    @field_validator("evidence")
    @classmethod
    def validate_evidence(cls, value: str | None) -> str | None:
        return _normalize_learning_text(value, required=False, field_label="evidence")

    @field_validator("next_action")
    @classmethod
    def validate_next_action(cls, value: str | None) -> str | None:
        return _normalize_learning_text(value, required=False, field_label="next_action")

    @model_validator(mode="after")
    def validate_patch_payload(self) -> "PerformanceLearningPatchPayload":
        if "learning_type" in self.model_fields_set and self.learning_type is None:
            raise ValueError("learning_type is required.")
        if "observation" in self.model_fields_set and self.observation is None:
            raise ValueError("observation is required.")
        return self


class PerformanceSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform_post_id: str
    captured_at: datetime
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    saves: int | None = None
    average_watch_time_seconds: Decimal | None = None
    completion_rate: Decimal | None = None
    followers_gained: int | None = None
    notes: str | None = None
    created_at: datetime


class WinnerPostSummary(BaseModel):
    id: str
    platform: str
    custom_platform_name: str | None = None
    post_url: str
    posted_at: datetime
    final_asset_id: str
    final_asset_source: str


class LearningAssociatedPostSummary(BaseModel):
    id: str
    platform: str
    custom_platform_name: str | None = None
    post_url: str
    posted_at: datetime


class WinnerSelectionSummary(BaseModel):
    platform_post_id: str | None = None
    selected_at: datetime | None = None
    selection_revision: int = 0
    post: WinnerPostSummary | None = None


class PerformanceLearningResponse(BaseModel):
    id: str
    pipeline_run_id: str
    learning_type: str
    observation: str
    evidence: str | None = None
    next_action: str | None = None
    platform_post_id: str | None = None
    associated_post: LearningAssociatedPostSummary | None = None
    is_archived: bool
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PerformanceLearningsSummary(BaseModel):
    active_count: int = 0
    items: list[PerformanceLearningResponse] = Field(default_factory=list)


ComparisonMetricName = Literal[
    "views",
    "engagement_rate",
    "like_rate",
    "comment_rate",
    "share_rate",
    "save_rate",
    "completion_rate",
    "follower_conversion_rate",
    "average_watch_time_ratio",
]

ComparisonMetricStatus = Literal["unavailable", "only_available", "leader", "tie"]
ComparisonAgeStatus = Literal["valid", "captured_before_posting", "unavailable"]
ComparisonAgeBucket = Literal["under_24h", "1_3d", "3_7d", "7_30d", "30d_plus"]


class PerformanceComparisonMetricValues(BaseModel):
    views: float | None = None
    engagement_rate: float | None = None
    like_rate: float | None = None
    comment_rate: float | None = None
    share_rate: float | None = None
    save_rate: float | None = None
    completion_rate: float | None = None
    follower_conversion_rate: float | None = None
    average_watch_time_ratio: float | None = None


class PerformanceMetricLeadershipSummary(BaseModel):
    status: ComparisonMetricStatus
    comparable_post_count: int
    leader_post_ids: list[str] = Field(default_factory=list)


class PerformanceComparisonSummary(BaseModel):
    latest_snapshot_ordering: list[str] = Field(default_factory=list)
    mixed_age_warning: bool = False
    mixed_age_warning_text: str | None = None
    has_invalid_capture_age: bool = False
    invalid_capture_age_warning_text: str | None = None
    metrics: dict[ComparisonMetricName, PerformanceMetricLeadershipSummary] = Field(default_factory=dict)


class PlatformPostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pipeline_run_id: str
    manual_post_package_id: str
    final_asset_id: str
    final_asset_source: str
    platform: str
    post_url: str
    posted_at: datetime
    custom_platform_name: str | None = None
    final_narration_render_id: str | None = None
    final_asset_selection_revision: int | None = None
    final_asset_metadata_json: dict[str, Any] | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    final_asset: dict[str, Any] | None = None
    attributed_asset_duration_seconds: float | None = None
    latest_snapshot: PerformanceSnapshotResponse | None = None
    latest_snapshot_age_seconds: int | None = None
    latest_snapshot_age_label: str | None = None
    latest_snapshot_age_bucket: ComparisonAgeBucket | None = None
    latest_snapshot_age_status: ComparisonAgeStatus = "unavailable"
    comparison_metrics: PerformanceComparisonMetricValues = Field(default_factory=PerformanceComparisonMetricValues)
    snapshots: list[PerformanceSnapshotResponse] = Field(default_factory=list)


class RunPerformanceResponse(BaseModel):
    run_id: str
    topic: str
    current_final_asset_selection: dict[str, Any] | None = None
    winner_selection: WinnerSelectionSummary = Field(default_factory=WinnerSelectionSummary)
    comparison: PerformanceComparisonSummary = Field(default_factory=PerformanceComparisonSummary)
    platform_posts: list[PlatformPostResponse] = Field(default_factory=list)
    learnings: list[PerformanceLearningResponse] = Field(default_factory=list)


class PerformanceWinnerSelectionPayload(BaseModel):
    platform_post_id: UUID
