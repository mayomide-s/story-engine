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
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

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
from app.services.request_security_service import attach_request_context
from app.services.schema_guard_service import assert_schema_up_to_date
from app.services.system_service import collect_health_details

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        forwarded_proto = getattr(request.state, "forwarded_proto", request.url.scheme)
        if forwarded_proto == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        response.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                "base-uri 'self'; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "img-src 'self' data: blob: https:; "
                "media-src 'self' data: blob: https:; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; "
                "connect-src 'self' https://api.storyengine.soremekun.org http://localhost:8000 http://127.0.0.1:8000 ws: wss:; "
                "font-src 'self' data:"
            ),
        )
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("X-Request-ID", getattr(request.state, "request_id", "unknown"))
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        attach_request_context(request, get_settings())
        return await call_next(request)


class HostValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        allowed_hosts = set(settings.allowed_hosts_list())
        host = request.headers.get("host", "").split(":", 1)[0].lower()
        if host and host not in allowed_hosts:
            return Response("Invalid host header.", status_code=400)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime_settings = get_settings()
    runtime_settings.validate_configuration()
    db = SessionLocal()
    try:
        seed_default_account(db)
        if not runtime_settings.is_development_like_environment() and runtime_settings.require_schema_up_to_date:
            assert_schema_up_to_date(db)
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
    middleware=[
        Middleware(RequestContextMiddleware),
        Middleware(HostValidationMiddleware),
        Middleware(SecurityHeadersMiddleware),
    ],
)
if settings.trust_proxy_headers:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxy_cidrs_list())
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", settings.csrf_header_name],
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
