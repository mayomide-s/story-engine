from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SocialAuthorizeRequest(BaseModel):
    return_path: str | None = None


class SocialAuthorizeResponse(BaseModel):
    platform: Literal["youtube"]
    authorization_url: str
    expires_at: datetime


class SocialConnectionSummaryResponse(BaseModel):
    id: str
    platform: str
    display_name: str | None = None
    username: str | None = None
    external_identity_hint: str
    connection_status: str
    granted_scopes: list[str] = Field(default_factory=list)
    token_expires_at: datetime | None = None
    token_health: str
    is_default: bool
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    last_error_code: str | None = None
    created_at: datetime
    updated_at: datetime


class SocialConnectionListResponse(BaseModel):
    items: list[SocialConnectionSummaryResponse] = Field(default_factory=list)


class SocialConnectionMutationResponse(BaseModel):
    connection: SocialConnectionSummaryResponse


class SocialConnectionPath(BaseModel):
    connection_id: UUID
