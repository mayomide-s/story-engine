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
