from __future__ import annotations

from pathlib import Path

from redis import Redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db.session import engine
from app.services.providers import get_storage_provider, get_video_provider


def _status_payload(status: str, detail: str, **extra) -> dict:
    payload = {"status": status, "detail": detail}
    payload.update(extra)
    return payload


def collect_health_details(settings: Settings) -> dict:
    config_errors = settings.configuration_errors()
    checks = {
        "database": check_database_readiness(),
        "redis": check_redis_readiness(settings),
        "storage": check_storage_readiness(settings),
        "video_provider": check_video_provider_readiness(settings),
        "configuration": _status_payload(
            "ok" if not config_errors else "error",
            "Configuration validated" if not config_errors else " ".join(config_errors),
            errors=config_errors,
            mode=settings.active_mode_label(),
        ),
    }
    degraded = any(check["status"] != "ok" for check in checks.values())
    return {
        "status": "degraded" if degraded else "ok",
        "backend_reachable": True,
        "environment": settings.environment,
        "video_provider": settings.video_provider,
        "storage_provider": settings.storage_provider,
        "runway_mode_enabled": settings.video_provider == "runway",
        "r2_public_base_url_configured": bool(settings.r2_public_base_url) if settings.storage_provider == "r2" else False,
        "checks": checks,
    }


def check_database_readiness() -> dict:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return _status_payload("ok", "Database reachable")
    except SQLAlchemyError as exc:
        return _status_payload("error", f"Database unavailable: {exc}")


def check_redis_readiness(settings: Settings) -> dict:
    try:
        client = Redis.from_url(settings.redis_url)
        client.ping()
        return _status_payload("ok", "Redis reachable")
    except Exception as exc:
        return _status_payload("error", f"Redis unavailable: {exc}")


def check_storage_readiness(settings: Settings) -> dict:
    try:
        if settings.storage_provider == "local":
            Path(settings.local_storage_path).mkdir(parents=True, exist_ok=True)
            return _status_payload("ok", "Local storage path ready")
        provider = get_storage_provider()
        return _status_payload("ok", "R2 storage provider configured", provider=provider.name)
    except Exception as exc:
        return _status_payload("error", f"Storage provider unavailable: {exc}")


def check_video_provider_readiness(settings: Settings) -> dict:
    try:
        provider = get_video_provider()
        sdk_version = getattr(provider, "sdk_version", None)
        detail = f"{provider.name} provider configured"
        if sdk_version:
            detail = f"{detail} (SDK {sdk_version})"
        return _status_payload("ok", detail, provider=provider.name, sdk_version=sdk_version)
    except Exception as exc:
        return _status_payload("error", f"Video provider unavailable: {exc}")
