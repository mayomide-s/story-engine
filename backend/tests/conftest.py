import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient
from fastapi.staticfiles import StaticFiles

db_file = tempfile.NamedTemporaryFile(delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{db_file.name}"
os.environ["AUTH_ENABLED"] = "false"

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

Base.metadata.create_all(bind=engine)


@pytest.fixture
def client():
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolate_provider_environment(monkeypatch):
    """Keep CI/staging environment variables from leaking into unit tests."""
    from app.config import get_settings

    provider_env_keys = [
        "VIDEO_PROVIDER",
        "STORAGE_PROVIDER",
        "LOCAL_STORAGE_PATH",
        "AUTH_ENABLED",
        "APP_ACCESS_PASSWORD",
        "APP_SESSION_SECRET",
        "SOCIAL_TOKEN_ENCRYPTION_KEY",
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REDIRECT_URI",
        "GOOGLE_OAUTH_FRONTEND_SUCCESS_URL",
        "GOOGLE_OAUTH_FRONTEND_ERROR_URL",
        "RUNWAY_API_KEY",
        "OPENAI_API_KEY",
        "SEMANTIC_CRITIC_ENABLED",
        "SEMANTIC_CRITIC_PROVIDER",
        "SEMANTIC_CRITIC_MODEL",
        "SEMANTIC_CRITIC_VERSION",
        "SEMANTIC_CRITIC_TIMEOUT_SECONDS",
        "NARRATION_ENABLED",
        "NARRATION_WRITER_PROVIDER",
        "NARRATION_WRITER_MODEL",
        "NARRATION_WRITER_PROMPT_VERSION",
        "NARRATION_SPEECH_PROVIDER",
        "NARRATION_SPEECH_MODEL",
        "NARRATION_VOICE",
        "NARRATION_VERSION",
        "NARRATION_CAPTION_VERSION",
        "NARRATION_RENDER_VERSION",
        "NARRATION_TIMEOUT_SECONDS",
        "NARRATION_MAX_WORDS",
        "NARRATION_MAX_ATEMPO_ADJUSTMENT_PERCENT",
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
        "R2_PUBLIC_BASE_URL",
    ]

    for key in provider_env_keys:
        monkeypatch.delenv(key, raising=False)

    temp_storage_dir = tempfile.mkdtemp(prefix="story_engine_test_storage_")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("SEMANTIC_CRITIC_ENABLED", "false")
    monkeypatch.setenv("LOCAL_STORAGE_PATH", temp_storage_dir)

    assets_mount = next(
        (route for route in app.routes if getattr(route, "path", None) == "/assets"),
        None,
    )
    original_assets_app = getattr(assets_mount, "app", None)
    if assets_mount is not None:
        assets_mount.app = StaticFiles(directory=temp_storage_dir)

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    if assets_mount is not None and original_assets_app is not None:
        assets_mount.app = original_assets_app
    shutil.rmtree(temp_storage_dir, ignore_errors=True)
