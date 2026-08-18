from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.idea_queue import IdeaQueueItemResponse
from app.schemas.news import (
    NewsDiscoveryRequest,
    NewsDiscoveryResponse,
    NewsPromotionRequest,
)
from app.services.access_service import (
    require_app_access,
    require_csrf_protection,
)
from app.services.news_discovery_service import (
    discover_news_candidates,
    promote_news_candidate,
)


router = APIRouter(
    prefix="/news",
    tags=["news"],
    dependencies=[
        Depends(require_app_access),
        Depends(require_csrf_protection),
    ],
)


@router.post("/discover", response_model=NewsDiscoveryResponse)
def discover_news(payload: NewsDiscoveryRequest):
    return discover_news_candidates(payload)


@router.post("/promote", response_model=IdeaQueueItemResponse)
def promote_news(
    payload: NewsPromotionRequest,
    db: Session = Depends(get_db),
):
    return promote_news_candidate(db, payload)
