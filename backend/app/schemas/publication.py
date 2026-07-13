from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


YouTubeVisibility = Literal["private", "unlisted", "public"]


def _normalize_tags(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        trimmed = item.strip()
        if not trimmed:
            continue
        lowered = trimmed.lower()
        if lowered in seen:
            continue
        normalized.append(trimmed)
        seen.add(lowered)
    return normalized


class PublicationJobDraftRequest(BaseModel):
    connection_id: UUID | None = None
    title: str
    caption: str | None = None
    tags: list[str] = Field(default_factory=list)
    category_id: str = "27"
    privacy: YouTubeVisibility
    self_declared_made_for_kids: bool
    contains_synthetic_media: bool

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Title is required.")
        if len(trimmed) > 100:
            raise ValueError("Title must be 100 characters or fewer.")
        return trimmed

    @field_validator("caption")
    @classmethod
    def validate_caption(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if len(trimmed) > 5000:
            raise ValueError("Caption must be 5000 characters or fewer.")
        return trimmed

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        normalized = _normalize_tags(value)
        combined_length = sum(len(item) for item in normalized) + max(0, len(normalized) - 1)
        if combined_length > 500:
            raise ValueError("Tags must total 500 characters or fewer.")
        return normalized

    @field_validator("category_id")
    @classmethod
    def validate_category_id(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Category is required.")
        if not trimmed.isdigit():
            raise ValueError("Category must be a numeric YouTube category identifier.")
        return trimmed


class PublicationTargetResponse(BaseModel):
    id: str
    social_connection_id: str
    channel_display_name: str | None = None
    channel_username: str | None = None
    channel_external_account_id: str | None = None
    platform: str
    visibility: str
    actual_visibility: str | None = None
    title: str
    caption: str | None = None
    tags: list[str] = Field(default_factory=list)
    category_id: str
    self_declared_made_for_kids: bool
    contains_synthetic_media: bool
    options: dict[str, Any] = Field(default_factory=dict)
    state: str
    idempotency_key: str
    provider_video_id: str | None = None
    provider_submission_id: str | None = None
    provider_media_id: str | None = None
    provider_upload_status: str | None = None
    provider_processing_status: str | None = None
    public_post_url: str | None = None
    platform_post_id: str | None = None
    attempt_count: int
    upload_bytes_total: int | None = None
    upload_bytes_sent: int | None = None
    upload_progress_percent: int | None = None
    next_poll_at: datetime | None = None
    processing_last_checked_at: datetime | None = None
    outcome_confirmed_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    reconnect_required: bool = False
    submitted_at: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    platform_post_creation_eligible: bool
    visibility_semantics: str
    available_actions: list[str] = Field(default_factory=list)


class PublicationJobResponse(BaseModel):
    id: str
    pipeline_run_id: str
    manual_post_package_id: str
    final_asset_id: str
    final_asset_selection_revision: int
    final_asset_source: str
    final_asset_sha256: str
    final_asset_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str
    approved_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    targets: list[PublicationTargetResponse] = Field(default_factory=list)
    selected_asset_is_frozen: bool
    selected_asset_has_changed_since_draft: bool
    available_actions: list[str] = Field(default_factory=list)


class PublicationJobMutationResponse(BaseModel):
    job: PublicationJobResponse
