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


def get_semantic_critic_provider():
    settings = get_settings()
    if not settings.semantic_critic_enabled:
        return None
    from app.providers.semantic_critic.openai_provider import OpenAISemanticCriticProvider

    return OpenAISemanticCriticProvider()


def get_narration_writer_provider():
    settings = get_settings()
    if not settings.narration_enabled:
        return None
    if settings.narration_writer_provider == "openai":
        from app.providers.narration_writer.openai_provider import OpenAINarrationWriterProvider

        return OpenAINarrationWriterProvider()
    from app.providers.narration_writer.mock_provider import MockNarrationWriterProvider

    return MockNarrationWriterProvider()


def get_speech_provider():
    settings = get_settings()
    if not settings.narration_enabled:
        return None
    if settings.narration_speech_provider == "openai":
        from app.providers.speech.openai_provider import OpenAISpeechProvider

        return OpenAISpeechProvider()
    from app.providers.speech.mock_provider import MockSpeechProvider

    return MockSpeechProvider()
