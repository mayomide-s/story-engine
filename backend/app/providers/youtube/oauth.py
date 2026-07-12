from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from app.config import Settings, get_settings
from app.services.security import redact_sensitive_data


GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
GOOGLE_OPENID_SCOPE = "openid"
GOOGLE_PROFILE_SCOPE = "profile"
YOUTUBE_OAUTH_SCOPES = [
    YOUTUBE_UPLOAD_SCOPE,
    GOOGLE_OPENID_SCOPE,
    GOOGLE_PROFILE_SCOPE,
]


class YouTubeOAuthError(RuntimeError):
    """Raised when the YouTube OAuth adapter cannot safely continue."""


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


def _resolve_identity_from_id_token(
    id_token: dict[str, Any] | None,
    *,
    require_identity: bool,
) -> tuple[str | None, str | None, str | None]:
    if not isinstance(id_token, dict):
        if require_identity:
            raise YouTubeOAuthError(
                "Google did not return an OpenID identity token. Story Engine requires the minimal OpenID identity scope to track the connected account safely."
            )
        return None, None, None
    subject = str(id_token.get("sub") or "").strip()
    if not subject:
        if require_identity:
            raise YouTubeOAuthError(
                "Google did not return a stable OpenID subject for this connection."
            )
        return None, None, None
    display_name = str(id_token.get("name")).strip() if id_token.get("name") else None
    username = str(id_token.get("given_name")).strip() if id_token.get("given_name") else None
    return f"google-sub:{subject}", display_name, username


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
    external_account_id, display_name, username = _resolve_identity_from_id_token(
        credentials.id_token,
        require_identity=True,
    )
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
            "identity_resolution": "google_openid_subject",
            "scope_decision": "youtube.upload plus minimal Google OpenID profile scopes",
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
    external_account_id, display_name, username = _resolve_identity_from_id_token(
        credentials.id_token,
        require_identity=False,
    )
    expiry = credentials.expiry.astimezone(UTC) if credentials.expiry else None
    return YouTubeTokenPayload(
        external_account_id=external_account_id or fallback_external_account_id,
        display_name=display_name or fallback_display_name,
        username=username or fallback_username,
        access_token=credentials.token,
        refresh_token=credentials.refresh_token,
        token_expiry=expiry,
        granted_scopes=list(credentials.granted_scopes or granted_scopes or YOUTUBE_OAUTH_SCOPES),
        provider_metadata={
            "identity_resolution": "google_openid_subject",
            "scope_decision": "youtube.upload plus minimal Google OpenID profile scopes",
            "refreshed_at": datetime.now(UTC).isoformat(),
        },
    )
