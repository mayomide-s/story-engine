from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import utcnow


GRANNYGRIND_STATUSES = (
    "queued",
    "ingesting",
    "submitted",
    "generating",
    "postprocessing",
    "needs_review",
    "approved",
    "rejected",
    "publishing",
    "published",
    "failed",
)

GRANNYGRIND_RIGHTS_STATUSES = (
    "unreviewed",
    "credited",
    "permission_confirmed",
)


class GrannyGrindJob(Base):
    __tablename__ = "grannygrind_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','ingesting','submitted','generating','postprocessing','needs_review','approved','rejected','publishing','published','failed')",
            name="ck_grannygrind_jobs_status",
        ),
        CheckConstraint(
            "rights_status IN ('unreviewed','credited','permission_confirmed')",
            name="ck_grannygrind_jobs_rights_status",
        ),
        Index("ix_grannygrind_jobs_status", "status"),
        Index("ix_grannygrind_jobs_created_at", "created_at"),
        Index("ix_grannygrind_jobs_granny_key", "granny_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_post_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_media_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_creator_handle: Mapped[str | None] = mapped_column(String(255))
    source_credit_text: Mapped[str | None] = mapped_column(Text)
    rights_status: Mapped[str] = mapped_column(String(50), nullable=False, default="unreviewed", server_default="unreviewed")

    granny_key: Mapped[str] = mapped_column(String(50), nullable=False)
    granny_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued", server_default="queued")

    source_storage_key: Mapped[str | None] = mapped_column(Text)
    source_public_url: Mapped[str | None] = mapped_column(Text)
    source_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    generation_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    runway_task_id: Mapped[str | None] = mapped_column(String(255))
    runway_response_json: Mapped[dict] = mapped_column(JSON, default=dict)

    transformed_storage_key: Mapped[str | None] = mapped_column(Text)
    transformed_public_url: Mapped[str | None] = mapped_column(Text)
    transformed_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    qc_json: Mapped[dict] = mapped_column(JSON, default=dict)

    review_notes: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime)

    instagram_container_id: Mapped[str | None] = mapped_column(String(255))
    instagram_media_id: Mapped[str | None] = mapped_column(String(255))
    instagram_permalink: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)

    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
