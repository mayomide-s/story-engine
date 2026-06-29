from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.db.session import SessionLocal
from app.models import IdeaQueueStatus, PipelinePriority
from app.schemas.idea_queue import IdeaQueueCreate
from app.schemas.pipeline_runs import PipelineRunCreate
from app.services.idea_queue_service import create_idea_queue_item
from app.services.pipeline_service import create_pipeline_run, seed_default_account


def main() -> None:
    settings = get_settings()
    if settings.video_provider != "mock" or settings.storage_provider != "local":
        raise SystemExit("Demo seed is only supported for local mock mode. Set VIDEO_PROVIDER=mock and STORAGE_PROVIDER=local.")

    with SessionLocal() as db:
        seed_default_account(db)
        items = [
            IdeaQueueCreate(
                topic="CORS explained like a nightclub bouncer",
                style_preset="neon_club_metaphor",
                target_platform="tiktok",
                priority=PipelinePriority.HIGH,
                status=IdeaQueueStatus.READY,
                notes="Use a strict but funny metaphor.",
                planned_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
            ),
            IdeaQueueCreate(
                topic="Why async bugs feel like invisible office coworkers",
                style_preset="office_comedy",
                target_platform="instagram",
                priority=PipelinePriority.NORMAL,
                status=IdeaQueueStatus.DRAFT,
                notes="Keep it beginner-friendly.",
                planned_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=2),
            ),
            IdeaQueueCreate(
                topic="A whiteboard character explains HTTP caching",
                style_preset="whiteboard_character",
                target_platform="youtube",
                priority=PipelinePriority.NORMAL,
                status=IdeaQueueStatus.READY,
                notes="Good test case for explainer format.",
                planned_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=3),
            ),
        ]
        for item in items:
            create_idea_queue_item(db, item)

        create_pipeline_run(
            db,
            PipelineRunCreate(
                topic="CORS",
                auto_mode=False,
                style_preset="clean_3d_cartoon",
                target_platforms=["instagram", "tiktok", "youtube"],
                caption_tone="playful explainer",
                duration_preference_seconds=18,
                audience_level="beginner",
                content_format="coding metaphor",
                priority=PipelinePriority.NORMAL,
            ),
        )

    print("Demo data created for local mock mode.")


if __name__ == "__main__":
    main()
