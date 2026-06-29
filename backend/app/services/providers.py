from app.config import get_settings
from app.providers.llm.mock_provider import MockLLMProvider
from app.providers.storage.local_provider import LocalStorageProvider
from app.providers.storage.r2_provider import R2StorageProvider
from app.providers.video.mock_provider import MockVideoProvider
from app.providers.video.runway_provider import RunwayVideoProvider


def get_llm_provider():
    return MockLLMProvider()


def get_video_provider():
    settings = get_settings()
    return RunwayVideoProvider() if settings.video_provider == "runway" else MockVideoProvider()


def get_storage_provider():
    settings = get_settings()
    return R2StorageProvider() if settings.storage_provider == "r2" else LocalStorageProvider()
