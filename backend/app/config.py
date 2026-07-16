from functools import lru_cache
from urllib.parse import urlparse
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
    session_cookie_name: str = Field(default="story_engine_session", alias="SESSION_COOKIE_NAME")
    session_cookie_domain: str = Field(default="", alias="SESSION_COOKIE_DOMAIN")
    session_cookie_max_age_seconds: int = Field(default=60 * 60 * 12, alias="SESSION_COOKIE_MAX_AGE_SECONDS")
    session_cookie_samesite: Literal["lax", "strict", "none"] = Field(default="lax", alias="SESSION_COOKIE_SAMESITE")
    session_cookie_secure_override: bool | None = Field(default=None, alias="SESSION_COOKIE_SECURE")
    csrf_header_name: str = Field(default="X-CSRF-Token", alias="CSRF_HEADER_NAME")
    social_token_encryption_key: str = Field(default="", alias="SOCIAL_TOKEN_ENCRYPTION_KEY")
    cors_allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ALLOWED_ORIGINS",
    )
    allowed_hosts: str = Field(default="localhost,127.0.0.1,testserver", alias="ALLOWED_HOSTS")
    trust_proxy_headers: bool = Field(default=False, alias="TRUST_PROXY_HEADERS")
    trusted_proxy_cidrs: str = Field(default="127.0.0.1/32,::1/128", alias="TRUSTED_PROXY_CIDRS")
    require_schema_up_to_date: bool = Field(default=True, alias="REQUIRE_SCHEMA_UP_TO_DATE")
    login_rate_limit_attempts: int = Field(default=5, alias="LOGIN_RATE_LIMIT_ATTEMPTS")
    login_rate_limit_window_seconds: int = Field(default=300, alias="LOGIN_RATE_LIMIT_WINDOW_SECONDS")
    sensitive_rate_limit_attempts: int = Field(default=10, alias="SENSITIVE_RATE_LIMIT_ATTEMPTS")
    sensitive_rate_limit_window_seconds: int = Field(default=300, alias="SENSITIVE_RATE_LIMIT_WINDOW_SECONDS")
    publication_rate_limit_attempts: int = Field(default=10, alias="PUBLICATION_RATE_LIMIT_ATTEMPTS")
    publication_rate_limit_window_seconds: int = Field(default=300, alias="PUBLICATION_RATE_LIMIT_WINDOW_SECONDS")
    compliance_write_rate_limit_attempts: int = Field(default=20, alias="COMPLIANCE_WRITE_RATE_LIMIT_ATTEMPTS")
    compliance_write_rate_limit_window_seconds: int = Field(default=600, alias="COMPLIANCE_WRITE_RATE_LIMIT_WINDOW_SECONDS")

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
    narration_enabled: bool = Field(default=False, alias="NARRATION_ENABLED")
    narration_writer_provider: Literal["mock", "openai"] = Field(default="mock", alias="NARRATION_WRITER_PROVIDER")
    narration_writer_model: str = Field(default="gpt-4.1-mini", alias="NARRATION_WRITER_MODEL")
    narration_writer_prompt_version: str = Field(default="v1", alias="NARRATION_WRITER_PROMPT_VERSION")
    narration_speech_provider: Literal["mock", "openai"] = Field(default="mock", alias="NARRATION_SPEECH_PROVIDER")
    narration_speech_model: str = Field(default="gpt-4o-mini-tts", alias="NARRATION_SPEECH_MODEL")
    narration_voice: str = Field(default="alloy", alias="NARRATION_VOICE")
    narration_version: str = Field(default="v1", alias="NARRATION_VERSION")
    narration_caption_version: str = Field(default="v1", alias="NARRATION_CAPTION_VERSION")
    narration_render_version: str = Field(default="v1", alias="NARRATION_RENDER_VERSION")
    narration_timeout_seconds: int = Field(default=90, alias="NARRATION_TIMEOUT_SECONDS")
    narration_max_words: int = Field(default=20, alias="NARRATION_MAX_WORDS")
    narration_max_atempo_adjustment_percent: int = Field(default=10, alias="NARRATION_MAX_ATEMPO_ADJUSTMENT_PERCENT")
    google_oauth_client_id: str = Field(default="", alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: str = Field(default="", alias="GOOGLE_OAUTH_CLIENT_SECRET")
    google_oauth_redirect_uri: str = Field(default="", alias="GOOGLE_OAUTH_REDIRECT_URI")
    google_oauth_frontend_success_url: str = Field(default="", alias="GOOGLE_OAUTH_FRONTEND_SUCCESS_URL")
    google_oauth_frontend_error_url: str = Field(default="", alias="GOOGLE_OAUTH_FRONTEND_ERROR_URL")
    youtube_default_category_id: str = Field(default="27", alias="YOUTUBE_DEFAULT_CATEGORY_ID")
    youtube_upload_chunk_size_bytes: int = Field(default=8 * 1024 * 1024, alias="YOUTUBE_UPLOAD_CHUNK_SIZE_BYTES")
    youtube_token_refresh_leeway_seconds: int = Field(default=300, alias="YOUTUBE_TOKEN_REFRESH_LEEWAY_SECONDS")
    youtube_claim_timeout_seconds: int = Field(default=300, alias="YOUTUBE_CLAIM_TIMEOUT_SECONDS")
    youtube_max_retry_attempts: int = Field(default=5, alias="YOUTUBE_MAX_RETRY_ATTEMPTS")
    youtube_poll_interval_seconds: int = Field(default=30, alias="YOUTUBE_POLL_INTERVAL_SECONDS")
    youtube_max_poll_attempts: int = Field(default=20, alias="YOUTUBE_MAX_POLL_ATTEMPTS")

    video_provider: Literal["mock", "runway"] = Field(default="mock", alias="VIDEO_PROVIDER")
    storage_provider: Literal["local", "r2"] = Field(default="local", alias="STORAGE_PROVIDER")
    local_storage_path: str = Field(default="./storage", alias="LOCAL_STORAGE_PATH")

    default_poll_interval_seconds: int = 15
    default_max_poll_attempts: int = 20
    default_provider_timeout_minutes: int = 30

    def active_mode_label(self) -> str:
        return f"{self.video_provider}/{self.storage_provider}"

    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    def allowed_hosts_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    def trusted_proxy_cidrs_list(self) -> list[str]:
        return [cidr.strip() for cidr in self.trusted_proxy_cidrs.split(",") if cidr.strip()]

    def auth_status_label(self) -> str:
        return "enabled" if self.auth_enabled else "disabled"

    def session_secret_value(self) -> str:
        return self.app_session_secret or self.app_access_password

    def is_development_like_environment(self) -> bool:
        return self.environment.lower() in {"development", "dev", "local", "test", "testing"}

    def session_cookie_secure(self) -> bool:
        if self.session_cookie_secure_override is not None:
            return self.session_cookie_secure_override
        return not self.is_development_like_environment()

    def session_cookie_domain_value(self) -> str | None:
        value = self.session_cookie_domain.strip()
        return value or None

    def _parsed_database_url(self):
        return urlparse(self.database_url)

    def _parsed_redis_url(self):
        return urlparse(self.redis_url)

    def _is_local_http_allowed(self, parsed) -> bool:
        return (
            parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1"}
            and self.is_development_like_environment()
        )

    def _validate_redirect_url(self, value: str, setting_name: str) -> str | None:
        if not value:
            return f"{setting_name} is required."
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return f"{setting_name} must be an absolute HTTP(S) URL."
        if parsed.scheme == "https":
            return None
        if self._is_local_http_allowed(parsed):
            return None
        return f"{setting_name} must use HTTPS outside local development."

    def social_publishing_missing_configuration(self) -> list[str]:
        required = {
            "SOCIAL_TOKEN_ENCRYPTION_KEY": self.social_token_encryption_key,
            "GOOGLE_OAUTH_CLIENT_ID": self.google_oauth_client_id,
            "GOOGLE_OAUTH_CLIENT_SECRET": self.google_oauth_client_secret,
            "GOOGLE_OAUTH_REDIRECT_URI": self.google_oauth_redirect_uri,
            "GOOGLE_OAUTH_FRONTEND_SUCCESS_URL": self.google_oauth_frontend_success_url,
            "GOOGLE_OAUTH_FRONTEND_ERROR_URL": self.google_oauth_frontend_error_url,
        }
        return [name for name, value in required.items() if not value]

    def social_publishing_configuration_errors(self) -> list[str]:
        errors: list[str] = []
        missing = self.social_publishing_missing_configuration()
        if missing:
            errors.append(f"Missing publishing settings: {', '.join(missing)}")
        if self.google_oauth_redirect_uri:
            redirect_error = self._validate_redirect_url(
                self.google_oauth_redirect_uri,
                "GOOGLE_OAUTH_REDIRECT_URI",
            )
            if redirect_error:
                errors.append(redirect_error)
        if self.google_oauth_frontend_success_url:
            success_error = self._validate_redirect_url(
                self.google_oauth_frontend_success_url,
                "GOOGLE_OAUTH_FRONTEND_SUCCESS_URL",
            )
            if success_error:
                errors.append(success_error)
        if self.google_oauth_frontend_error_url:
            error_error = self._validate_redirect_url(
                self.google_oauth_frontend_error_url,
                "GOOGLE_OAUTH_FRONTEND_ERROR_URL",
            )
            if error_error:
                errors.append(error_error)
        return errors

    def social_publishing_ready(self) -> bool:
        return not self.social_publishing_configuration_errors()

    def social_publishing_status_summary(self) -> dict[str, object]:
        return {
            "configured": self.social_publishing_ready(),
            "errors": self.social_publishing_configuration_errors(),
            "google_oauth_redirect_uri_configured": bool(self.google_oauth_redirect_uri),
            "google_oauth_frontend_success_url_configured": bool(self.google_oauth_frontend_success_url),
            "google_oauth_frontend_error_url_configured": bool(self.google_oauth_frontend_error_url),
            "social_token_encryption_configured": bool(self.social_token_encryption_key),
        }

    def missing_configuration(self) -> dict[str, list[str]]:
        required = {
            "base": ["DATABASE_URL", "REDIS_URL", "VIDEO_PROVIDER", "STORAGE_PROVIDER"],
            "auth": [],
            "storage": [],
            "video": [],
            "semantic_critic": [],
            "narration": [],
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
        if self.narration_enabled and (
            self.narration_writer_provider == "openai" or self.narration_speech_provider == "openai"
        ):
            required["narration"] = ["OPENAI_API_KEY"]

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
        if missing.get("narration"):
            errors.append(
                f"Missing required narration settings for {mode_label}: {', '.join(missing['narration'])}"
            )
        cors_origins = self.cors_allowed_origins_list()
        if any(origin == "*" for origin in cors_origins):
            errors.append("CORS_ALLOWED_ORIGINS cannot contain '*' when credentials are enabled.")
        if self.is_development_like_environment():
            if not self.allowed_hosts_list():
                errors.append("ALLOWED_HOSTS must include localhost-compatible hosts in development.")
        else:
            if not self.allowed_hosts_list():
                errors.append("ALLOWED_HOSTS must be configured outside local development.")
            if "*" in self.allowed_hosts_list():
                errors.append("ALLOWED_HOSTS cannot contain '*' outside local development.")
            parsed_database_url = self._parsed_database_url()
            if parsed_database_url.scheme == "sqlite":
                errors.append("DATABASE_URL cannot use SQLite outside local development.")
            if parsed_database_url.scheme not in {"postgresql", "postgresql+psycopg"}:
                errors.append("DATABASE_URL must use PostgreSQL outside local development.")
            parsed_redis_url = self._parsed_redis_url()
            if parsed_redis_url.scheme != "rediss":
                errors.append("REDIS_URL must use rediss:// outside local development.")
            if not self.session_cookie_secure():
                errors.append("SESSION_COOKIE_SECURE must be enabled outside local development.")
            for origin in cors_origins:
                parsed = urlparse(origin)
                if parsed.scheme != "https":
                    errors.append("CORS_ALLOWED_ORIGINS must use HTTPS outside local development.")
            if self.trust_proxy_headers and not self.trusted_proxy_cidrs_list():
                errors.append("TRUSTED_PROXY_CIDRS must be configured when TRUST_PROXY_HEADERS is enabled.")
            if self.storage_provider == "r2" and self.r2_public_base_url:
                parsed_r2_url = urlparse(self.r2_public_base_url)
                if parsed_r2_url.scheme != "https" or not parsed_r2_url.netloc:
                    errors.append("R2_PUBLIC_BASE_URL must be an absolute HTTPS URL outside local development.")
        return errors

    def validate_configuration(self) -> None:
        errors = self.configuration_errors()
        if errors:
            raise RuntimeError("Configuration validation failed. " + " ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()
