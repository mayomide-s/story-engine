from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field


RightsStatus = Literal["unreviewed", "credited", "permission_confirmed"]


class GrannyGrindCreate(BaseModel):
    source_post_url: AnyHttpUrl
    source_media_url: AnyHttpUrl
    source_creator_handle: str | None = Field(default=None, max_length=255)
    source_credit_text: str | None = Field(default=None, max_length=1000)
    rights_status: RightsStatus = "unreviewed"


class GrannyGrindReview(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class GrannyGrindPublishRequest(BaseModel):
    caption: str | None = Field(default=None, max_length=2200)
    share_to_feed: bool = True


class GrannyCharacterResponse(BaseModel):
    key: str
    name: str
    wardrobe: str
    rotation_order: int


class GrannyGrindJobResponse(BaseModel):
    id: str
    source_post_url: str
    source_media_url: str
    source_creator_handle: str | None
    source_credit_text: str | None
    rights_status: str
    granny_key: str
    granny_name: str
    prompt_text: str
    status: str
    source_public_url: str | None
    source_metadata_json: dict
    runway_task_id: str | None
    transformed_public_url: str | None
    transformed_metadata_json: dict
    qc_json: dict
    review_notes: str | None
    instagram_media_id: str | None
    instagram_permalink: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
