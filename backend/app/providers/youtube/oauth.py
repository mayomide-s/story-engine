from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.config import Settings, get_settings
from app.services.security import redact_sensitive_data


GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_OAUTH_SCOPES = [
    YOUTUBE_UPLOAD_SCOPE,
    YOUTUBE_READONLY_SCOPE,
]


class YouTubeOAuthError(RuntimeError):
    """Raised when the YouTube OAuth adapter cannot safely continue."""

    error_code = "youtube_oauth_error"


class YouTubeChannelNotFoundError(YouTubeOAuthError):
    error_code = "youtube_channel_not_found"


class MultipleYouTubeChannelsUnsupportedError(YouTubeOAuthError):
    error_code = "multiple_youtube_channels_unsupported"


@dataclass(frozen=True)
class YouTubeAuthorizationRequest:
    authorization_url: str
    state: str


@dataclass(frozen=True)
class YouTubeTokenPayload:
    external_account_id: str
    display_name: str | None
    username: str | None
    access_token: str
    refresh_token: str | None
    token_expiry: datetime | None
    granted_scopes: list[str]
    provider_metadata: dict[str, Any]


def _client_config(settings: Settings) -> dict[str, dict[str, str]]:
    return {
        "web": {
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "auth_uri": GOOGLE_AUTH_URI,
            "token_uri": GOOGLE_TOKEN_URI,
        }
    }


def _build_flow(settings: Settings) -> Flow:
    return Flow.from_client_config(
        _client_config(settings),
        scopes=YOUTUBE_OAUTH_SCOPES,
        redirect_uri=settings.google_oauth_redirect_uri,
    )


def _resolve_channel_identity(credentials: Credentials) -> tuple[str, str | None, str | None, dict[str, Any]]:
    try:
        youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        response = youtube.channels().list(part="id,snippet", mine=True).execute()
    except Exception as exc:
        raise YouTubeOAuthError(
            f"YouTube channel lookup failed: {redact_sensitive_data(str(exc))}"
        ) from exc

    items = response.get("items") if isinstance(response, dict) else None
    if not isinstance(items, list) or len(items) == 0:
        raise YouTubeChannelNotFoundError(
            "YouTube did not return a channel for this authorization."
        )
    if len(items) > 1:
        raise MultipleYouTubeChannelsUnsupportedError(
            "This Google authorization can access multiple YouTube channels. Sprint 1A requires an unambiguous single channel."
        )

    channel = items[0] if isinstance(items[0], dict) else {}
    channel_id = str(channel.get("id") or "").strip()
    if not channel_id:
        raise YouTubeOAuthError("YouTube channel lookup returned an invalid channel identifier.")

    snippet = channel.get("snippet") if isinstance(channel.get("snippet"), dict) else {}
    display_name = str(snippet.get("title") or "").strip() or None
    username = str(snippet.get("customUrl") or "").strip() or None
    provider_metadata: dict[str, Any] = {
        "channel_identity_source": "youtube.channels.list.mine",
    }
    if username:
        provider_metadata["channel_custom_url"] = username
    return channel_id, display_name, username, provider_metadata


def build_authorization_request(
    raw_state: str,
    *,
    force_consent: bool,
    settings: Settings | None = None,
) -> YouTubeAuthorizationRequest:
    active_settings = settings or get_settings()
    flow = _build_flow(active_settings)
    authorization_kwargs = {
        "access_type": "offline",
        "include_granted_scopes": "true",
        "state": raw_state,
    }
    if force_consent:
        authorization_kwargs["prompt"] = "consent"
    authorization_url, returned_state = flow.authorization_url(
        **authorization_kwargs,
    )
    return YouTubeAuthorizationRequest(
        authorization_url=authorization_url,
        state=returned_state,
    )


def exchange_callback_code(
    code: str,
    *,
    settings: Settings | None = None,
) -> YouTubeTokenPayload:
    active_settings = settings or get_settings()
    flow = _build_flow(active_settings)
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise YouTubeOAuthError(f"Google OAuth exchange failed: {redact_sensitive_data(str(exc))}") from exc
    credentials = flow.credentials
    external_account_id, display_name, username, provider_metadata = _resolve_channel_identity(credentials)
    expiry = credentials.expiry.astimezone(UTC) if credentials.expiry else None
    return YouTubeTokenPayload(
        external_account_id=external_account_id,
        display_name=display_name,
        username=username,
        access_token=credentials.token,
        refresh_token=credentials.refresh_token,
        token_expiry=expiry,
        granted_scopes=list(credentials.granted_scopes or YOUTUBE_OAUTH_SCOPES),
        provider_metadata={
            **provider_metadata,
            "scope_decision": "youtube.upload plus youtube.readonly for channel identity resolution",
        },
    )


def refresh_tokens(
    *,
    refresh_token: str,
    granted_scopes: list[str],
    fallback_external_account_id: str,
    fallback_display_name: str | None,
    fallback_username: str | None,
    settings: Settings | None = None,
) -> YouTubeTokenPayload:
    active_settings = settings or get_settings()
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=active_settings.google_oauth_client_id,
        client_secret=active_settings.google_oauth_client_secret,
        scopes=granted_scopes or YOUTUBE_OAUTH_SCOPES,
    )
    try:
        credentials.refresh(Request())
    except Exception as exc:
        raise YouTubeOAuthError(f"Google OAuth refresh failed: {redact_sensitive_data(str(exc))}") from exc
    external_account_id, display_name, username, provider_metadata = _resolve_channel_identity(credentials)
    if external_account_id != fallback_external_account_id:
        raise YouTubeOAuthError(
            "The refreshed YouTube authorization resolved to a different channel. Reconnect is required."
        )
    expiry = credentials.expiry.astimezone(UTC) if credentials.expiry else None
    return YouTubeTokenPayload(
        external_account_id=external_account_id,
        display_name=display_name or fallback_display_name,
        username=username or fallback_username,
        access_token=credentials.token,
        refresh_token=credentials.refresh_token,
        token_expiry=expiry,
        granted_scopes=list(credentials.granted_scopes or granted_scopes or YOUTUBE_OAUTH_SCOPES),
        provider_metadata={
            **provider_metadata,
            "scope_decision": "youtube.upload plus youtube.readonly for channel identity resolution",
            "refreshed_at": datetime.now(UTC).isoformat(),
        },
    )
