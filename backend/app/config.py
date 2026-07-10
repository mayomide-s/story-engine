from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    app_name: str = "AI Coding Story Engine"
    environment: str = "development"
    api_prefix: str = "/api"
    auth_enabled: bool = Field(default=False, alias="AUTH_ENABLED")
    app_access_password: str = Field(default="", alias="APP_ACCESS_PASSWORD")
    app_session_secret: str = Field(default="", alias="APP_SESSION_SECRET")
    cors_allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ALLOWED_ORIGINS",
    )

    database_url: str = Field(default="sqlite:///./socipost.db", alias="DATABASE_URL")
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")

    r2_account_id: str = Field(default="", alias="R2_ACCOUNT_ID")
    r2_access_key_id: str = Field(default="", alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str = Field(default="", alias="R2_SECRET_ACCESS_KEY")
    r2_bucket_name: str = Field(default="socipost-assets", alias="R2_BUCKET_NAME")
    r2_public_base_url: str = Field(default="http://localhost:8000/assets", alias="R2_PUBLIC_BASE_URL")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    runway_api_key: str = Field(default="", alias="RUNWAY_API_KEY")
    semantic_critic_enabled: bool = Field(default=False, alias="SEMANTIC_CRITIC_ENABLED")
    semantic_critic_provider: Literal["openai"] = Field(default="openai", alias="SEMANTIC_CRITIC_PROVIDER")
    semantic_critic_model: str = Field(default="gpt-4.1-mini", alias="SEMANTIC_CRITIC_MODEL")
    semantic_critic_version: str = Field(default="v1", alias="SEMANTIC_CRITIC_VERSION")
    semantic_critic_timeout_seconds: int = Field(default=60, alias="SEMANTIC_CRITIC_TIMEOUT_SECONDS")

    video_provider: Literal["mock", "runway"] = Field(default="mock", alias="VIDEO_PROVIDER")
    storage_provider: Literal["local", "r2"] = Field(default="local", alias="STORAGE_PROVIDER")
    local_storage_path: str = "./storage"

    default_poll_interval_seconds: int = 15
    default_max_poll_attempts: int = 20
    default_provider_timeout_minutes: int = 30

    def active_mode_label(self) -> str:
        return f"{self.video_provider}/{self.storage_provider}"

    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    def auth_status_label(self) -> str:
        return "enabled" if self.auth_enabled else "disabled"

    def session_secret_value(self) -> str:
        return self.app_session_secret or self.app_access_password

    def missing_configuration(self) -> dict[str, list[str]]:
        required = {
            "base": ["DATABASE_URL", "REDIS_URL", "VIDEO_PROVIDER", "STORAGE_PROVIDER"],
            "auth": [],
            "storage": [],
            "video": [],
            "semantic_critic": [],
        }
        if self.auth_enabled:
            required["auth"] = ["APP_ACCESS_PASSWORD"]
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
        if self.semantic_critic_enabled and self.semantic_critic_provider == "openai":
            required["semantic_critic"] = ["OPENAI_API_KEY"]

        values = {
            "DATABASE_URL": self.database_url,
            "REDIS_URL": self.redis_url,
            "VIDEO_PROVIDER": self.video_provider,
            "STORAGE_PROVIDER": self.storage_provider,
            "APP_ACCESS_PASSWORD": self.app_access_password,
            "R2_ACCOUNT_ID": self.r2_account_id,
            "R2_ACCESS_KEY_ID": self.r2_access_key_id,
            "R2_SECRET_ACCESS_KEY": self.r2_secret_access_key,
            "R2_BUCKET_NAME": self.r2_bucket_name,
            "R2_PUBLIC_BASE_URL": self.r2_public_base_url,
            "RUNWAY_API_KEY": self.runway_api_key,
            "OPENAI_API_KEY": self.openai_api_key,
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
        if missing.get("auth"):
            errors.append(f"Missing required auth settings for {mode_label}: {', '.join(missing['auth'])}")
        if missing.get("storage"):
            errors.append(f"Missing required storage settings for {mode_label}: {', '.join(missing['storage'])}")
        if missing.get("video"):
            errors.append(f"Missing required video provider settings for {mode_label}: {', '.join(missing['video'])}")
        if missing.get("semantic_critic"):
            errors.append(
                f"Missing required semantic critic settings for {mode_label}: {', '.join(missing['semantic_critic'])}"
            )
        return errors

    def validate_configuration(self) -> None:
        errors = self.configuration_errors()
        if errors:
            raise RuntimeError("Configuration validation failed. " + " ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()
