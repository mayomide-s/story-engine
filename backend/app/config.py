from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

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

    def active_mode_label(self) -> str:
        return f"{self.video_provider}/{self.storage_provider}"

    def missing_configuration(self) -> dict[str, list[str]]:
        required = {
            "base": ["DATABASE_URL", "REDIS_URL", "VIDEO_PROVIDER", "STORAGE_PROVIDER"],
            "storage": [],
            "video": [],
        }
        if self.storage_provider == "r2":
            required["storage"] = [
                "R2_ACCOUNT_ID",
                "R2_ACCESS_KEY_ID",
                "R2_SECRET_ACCESS_KEY",
                "R2_BUCKET_NAME",
                "R2_PUBLIC_BASE_URL",
            ]
        if self.video_provider == "runway":
            required["video"] = ["RUNWAY_API_KEY"]

        values = {
            "DATABASE_URL": self.database_url,
            "REDIS_URL": self.redis_url,
            "VIDEO_PROVIDER": self.video_provider,
            "STORAGE_PROVIDER": self.storage_provider,
            "R2_ACCOUNT_ID": self.r2_account_id,
            "R2_ACCESS_KEY_ID": self.r2_access_key_id,
            "R2_SECRET_ACCESS_KEY": self.r2_secret_access_key,
            "R2_BUCKET_NAME": self.r2_bucket_name,
            "R2_PUBLIC_BASE_URL": self.r2_public_base_url,
            "RUNWAY_API_KEY": self.runway_api_key,
        }

        missing: dict[str, list[str]] = {}
        for section, keys in required.items():
            section_missing = [key for key in keys if not values.get(key)]
            if section_missing:
                missing[section] = section_missing
        return missing

    def configuration_errors(self) -> list[str]:
        errors: list[str] = []
        missing = self.missing_configuration()
        mode_label = self.active_mode_label()
        if missing.get("base"):
            errors.append(f"Missing required base settings for {mode_label}: {', '.join(missing['base'])}")
        if missing.get("storage"):
            errors.append(f"Missing required storage settings for {mode_label}: {', '.join(missing['storage'])}")
        if missing.get("video"):
            errors.append(f"Missing required video provider settings for {mode_label}: {', '.join(missing['video'])}")
        return errors

    def validate_configuration(self) -> None:
        errors = self.configuration_errors()
        if errors:
            raise RuntimeError("Configuration validation failed. " + " ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()
