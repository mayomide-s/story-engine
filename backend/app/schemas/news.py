from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

from app.models import PipelinePriority


class NewsSourceInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    feed_url: str = Field(min_length=8, max_length=2048)
    source_quality: float = Field(default=0.75, ge=0.0, le=1.0)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Source name cannot be empty.")
        return cleaned

    @field_validator("feed_url")
    @classmethod
    def validate_feed_url_shape(cls, value: str) -> str:
        cleaned = value.strip()
        parsed = urlsplit(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Feed URL must be an absolute http(s) URL.")
        return cleaned


class NewsDiscoveryRequest(BaseModel):
    sources: list[NewsSourceInput] = Field(min_length=1, max_length=8)
    niche_keywords: list[str] = Field(min_length=1, max_length=30)
    max_age_hours: int = Field(default=36, ge=1, le=168)
    limit: int = Field(default=10, ge=1, le=50)
    min_relevance_score: float = Field(default=0.10, ge=0.0, le=1.0)

    @field_validator("niche_keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = " ".join(value.lower().split())
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            result.append(cleaned)
        if not result:
            raise ValueError("At least one non-empty niche keyword is required.")
        return result


class NewsCandidate(BaseModel):
    candidate_id: str
    title: str
    url: str
    source_name: str
    published_at: datetime | None = None
    summary: str = ""
    source_quality: float
    matched_keywords: list[str] = Field(default_factory=list)
    freshness_score: float
    relevance_score: float
    instagram_potential_score: float
    source_quality_score: float
    overall_score: float


class NewsSourceFailure(BaseModel):
    source_name: str
    feed_url: str
    error: str


class NewsDiscoveryResponse(BaseModel):
    candidates: list[NewsCandidate] = Field(default_factory=list)
    fetched_sources: int = 0
    failed_sources: list[NewsSourceFailure] = Field(default_factory=list)
    raw_entries: int = 0
    deduplicated_entries: int = 0


class NewsPromotionRequest(BaseModel):
    candidate: NewsCandidate
    priority: PipelinePriority = PipelinePriority.NORMAL
    style_preset: str | None = None
