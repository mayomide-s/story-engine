from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI Coding Story Engine"
    environment: str = "development"
    api_prefix: str = "/api"

    database_url: str = Field(default="sqlite:///./socipost.db", alias="DATABASE_URL")
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")

    r2_account_id: str = Field(default="", alias="R2_ACCOUNT_ID")
    r2_access_key_id: str = Field(default="", alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str = Field(default="", alias="R2_SECRET_ACCESS_KEY")
    r2_bucket_name: str = Field(default="socipost-assets", alias="R2_BUCKET_NAME")
    r2_public_base_url: str = Field(default="http://localhost:8000/assets", alias="R2_PUBLIC_BASE_URL")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    runway_api_key: str = Field(default="", alias="RUNWAY_API_KEY")

    video_provider: Literal["mock", "runway"] = Field(default="mock", alias="VIDEO_PROVIDER")
    storage_provider: Literal["local", "r2"] = Field(default="local", alias="STORAGE_PROVIDER")
    local_storage_path: str = "./storage"

    default_poll_interval_seconds: int = 15
    default_max_poll_attempts: int = 20
    default_provider_timeout_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
