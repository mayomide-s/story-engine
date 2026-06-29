from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db.session import SessionLocal
from app.routers.pipeline_runs import router as pipeline_runs_router
from app.services.providers import get_video_provider
from app.services.pipeline_service import seed_default_account

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        seed_default_account(db)
    finally:
        db.close()
    if settings.video_provider == "runway":
        try:
            provider = get_video_provider()
            logger.info("Runway provider validation succeeded using %s", getattr(provider, "sdk_version", "unknown"))
        except Exception as exc:
            logger.error("Runway provider validation failed: %s", exc)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(pipeline_runs_router, prefix=settings.api_prefix)
Path(settings.local_storage_path).mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=settings.local_storage_path), name="assets")


@app.get("/health")
def healthcheck():
    return {"status": "ok"}
