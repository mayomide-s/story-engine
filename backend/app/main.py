from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db.session import SessionLocal
from app.routers.access import router as access_router
from app.routers.asset_library import router as asset_library_router
from app.routers.idea_queue import router as idea_queue_router
from app.routers.performance import router as performance_router
from app.routers.pipeline_runs import router as pipeline_runs_router
from app.routers.publication_jobs import router as publication_jobs_router
from app.routers.settings import router as settings_router
from app.routers.social_connections import router as social_connections_router
from app.services.providers import get_video_provider
from app.services.pipeline_service import seed_default_account
from app.services.system_service import collect_health_details

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime_settings = get_settings()
    runtime_settings.validate_configuration()
    db = SessionLocal()
    try:
        seed_default_account(db)
    finally:
        db.close()
    if runtime_settings.video_provider == "runway":
        try:
            provider = get_video_provider()
            logger.info("Runway provider validation succeeded using %s", getattr(provider, "sdk_version", "unknown"))
        except Exception as exc:
            logger.error("Runway provider validation failed: %s", exc)
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    middleware=[Middleware(SecurityHeadersMiddleware)],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(access_router, prefix=settings.api_prefix)
app.include_router(pipeline_runs_router, prefix=settings.api_prefix)
app.include_router(performance_router, prefix=settings.api_prefix)
app.include_router(idea_queue_router, prefix=settings.api_prefix)
app.include_router(asset_library_router, prefix=settings.api_prefix)
app.include_router(settings_router, prefix=settings.api_prefix)
app.include_router(social_connections_router, prefix=settings.api_prefix)
app.include_router(publication_jobs_router, prefix=settings.api_prefix)
Path(settings.local_storage_path).mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=settings.local_storage_path), name="assets")


@app.get("/health")
def healthcheck():
    return {"status": "ok"}


@app.get("/health/details")
def health_details():
    return collect_health_details(get_settings())
