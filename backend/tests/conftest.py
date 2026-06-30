import os
import tempfile

import pytest
from fastapi.testclient import TestClient

db_file = tempfile.NamedTemporaryFile(delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{db_file.name}"

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
        "AUTH_ENABLED",
        "APP_ACCESS_PASSWORD",
        "APP_SESSION_SECRET",
        "RUNWAY_API_KEY",
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
        "R2_PUBLIC_BASE_URL",
    ]

    for key in provider_env_keys:
        monkeypatch.delenv(key, raising=False)

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

