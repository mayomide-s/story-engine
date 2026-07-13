from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AccountDefaultsResponse(BaseModel):
    account_name: str
    niche: str
    account_config_json: dict[str, Any]


class AccountDefaultsUpdate(BaseModel):
    default_style_preset: str | None = None
    target_platforms: list[str] | None = None
    default_caption_tone: str | None = None
    default_hashtag_set: list[str] | None = None
    default_duration_seconds: int | None = Field(default=None, ge=5, le=30)
    default_audience_level: str | None = None
    default_content_format: str | None = None
    brand_description: str | None = None
    preferred_cta: str | None = None
    avoid_phrases: list[str] | None = None
    emoji_preference: str | None = None


class AccountDeletionPreviewCategory(BaseModel):
    key: str
    title: str
    count: int
    description: str


class AccountDeletionPreviewResponse(BaseModel):
    account_status: str
    can_delete: bool
    requires_password_confirmation: bool
    requires_recent_authentication: bool
    confirmation_phrase: str
    provider_video_warning: str
    connected_accounts: list[dict[str, str | None]]
    deletion_categories: list[AccountDeletionPreviewCategory]
    anonymised_categories: list[AccountDeletionPreviewCategory]
    temporarily_retained_categories: list[AccountDeletionPreviewCategory]


class AccountDeletionValidateRequest(BaseModel):
    confirmation_phrase: str
    acknowledge_provider_videos_remain_online: bool
    password: str | None = None


class AccountDeletionValidationResponse(BaseModel):
    can_delete: bool
    requires_password_confirmation: bool
    validation_message: str
    preview: AccountDeletionPreviewResponse


class AccountDeletionExecuteRequest(AccountDeletionValidateRequest):
    pass


class AccountDeletionResultResponse(BaseModel):
    deleted: bool
    account_status: str
    message: str
    disconnected_connection_count: int
    deleted_social_connection_count: int
    deleted_pipeline_run_count: int
    deleted_asset_count: int
    deleted_local_file_count: int
    deleted_publication_job_count: int
    deleted_publication_target_count: int
    deleted_platform_post_count: int
    deleted_snapshot_count: int
    deleted_learning_count: int


class RetentionCategoryReportResponse(BaseModel):
    key: str
    title: str
    retention_months: int
    cleanup_action: str
    description: str
    automatically_deleted: bool
    expired_record_count: int


class RetentionReportResponse(BaseModel):
    default_retention_months: int
    generated_at: datetime
    categories: list[RetentionCategoryReportResponse]
