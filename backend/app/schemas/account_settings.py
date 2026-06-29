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
