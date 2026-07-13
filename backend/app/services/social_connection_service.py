from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import SocialConnection
from app.providers.youtube.oauth import (
    YOUTUBE_OAUTH_SCOPES,
    YouTubeOAuthError,
    build_authorization_request,
    exchange_callback_code,
    refresh_tokens,
)
from app.schemas.social_connections import SocialConnectionSummaryResponse
from app.services.oauth_state_service import OAuthStateError, consume_oauth_state, create_oauth_state
from app.services.pipeline_service import seed_default_account
from app.services.social_token_crypto import SocialTokenCryptoError, decrypt_secret, encrypt_secret


YOUTUBE_PLATFORM = "youtube"


class SocialConnectionConfigurationError(RuntimeError):
    """Raised when social publishing is not configured safely."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _coerce_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_social_configuration() -> None:
    errors = get_settings().social_publishing_configuration_errors()
    if errors:
        raise SocialConnectionConfigurationError(" ".join(errors))


def _mask_external_identity(value: str) -> str:
    if len(value) <= 8:
        return f"{value[:2]}***"
    return f"{value[:4]}…{value[-4:]}"


def _token_health(connection: SocialConnection) -> str:
    if connection.connection_status == "disconnected":
        return "disconnected"
    if connection.connection_status == "revoked":
        return "revoked"
    if connection.token_expires_at is None:
        return "unknown"
    token_expires_at = _coerce_aware(connection.token_expires_at)
    if token_expires_at <= _utcnow():
        return "expired"
    if token_expires_at <= _utcnow() + timedelta(minutes=10):
        return "expiring_soon"
    if not connection.encrypted_refresh_token:
        return "access_only"
    return "healthy"


def _serialize_connection_summary(connection: SocialConnection) -> dict:
    return SocialConnectionSummaryResponse(
        id=connection.id,
        platform=connection.platform,
        display_name=connection.display_name,
        username=connection.username,
        external_identity_hint=_mask_external_identity(connection.external_account_id),
        connection_status=connection.connection_status,
        granted_scopes=list(connection.granted_scopes_json or []),
        token_expires_at=connection.token_expires_at,
        token_health=_token_health(connection),
        is_default=bool(connection.is_default),
        connected_at=connection.connected_at,
        disconnected_at=connection.disconnected_at,
        last_error_code=connection.last_error_code,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    ).model_dump(mode="json")


def _persist_refreshed_connection(
    db: Session,
    connection: SocialConnection,
    token_payload,
) -> SocialConnection:
    access_ciphertext, cipher_version = encrypt_secret(token_payload.access_token, purpose="access token")
    connection.encrypted_access_token = access_ciphertext
    if token_payload.refresh_token:
        refresh_ciphertext, _ = encrypt_secret(token_payload.refresh_token, purpose="refresh token")
        connection.encrypted_refresh_token = refresh_ciphertext
    connection.token_cipher_version = cipher_version
    connection.token_expires_at = token_payload.token_expiry
    connection.granted_scopes_json = list(token_payload.granted_scopes)
    connection.display_name = token_payload.display_name or connection.display_name
    connection.username = token_payload.username or connection.username
    connection.provider_metadata_json = {
        **dict(connection.provider_metadata_json or {}),
        **dict(token_payload.provider_metadata),
    }
    connection.connection_status = "active"
    connection.last_refresh_at = _utcnow()
    connection.last_error_code = None
    connection.last_error_at = None
    connection.updated_at = _utcnow()
    db.add(connection)
    db.flush()
    return connection


def refresh_youtube_connection_tokens_if_needed(
    db: Session,
    connection: SocialConnection,
    *,
    force: bool = False,
) -> SocialConnection:
    _require_social_configuration()
    if connection.platform != YOUTUBE_PLATFORM:
        raise RuntimeError("Only YouTube connections are supported.")
    if not connection.encrypted_refresh_token:
        raise RuntimeError("This YouTube connection requires reconnect because no refresh token is stored.")

    expires_at = _coerce_aware(connection.token_expires_at) if connection.token_expires_at else None
    refresh_deadline = _utcnow() + timedelta(seconds=get_settings().youtube_token_refresh_leeway_seconds)
    if not force and expires_at and expires_at > refresh_deadline and connection.connection_status == "active":
        return connection

    try:
        refresh_token = decrypt_secret(connection.encrypted_refresh_token, purpose="refresh token")
        token_payload = refresh_tokens(
            refresh_token=refresh_token,
            granted_scopes=list(connection.granted_scopes_json or YOUTUBE_OAUTH_SCOPES),
            fallback_external_account_id=connection.external_account_id,
            fallback_display_name=connection.display_name,
            fallback_username=connection.username,
        )
    except (SocialTokenCryptoError, YouTubeOAuthError) as exc:
        connection.connection_status = "revoked" if getattr(exc, "error_code", "") == "youtube_oauth_error" else "error"
        connection.last_error_code = exc.__class__.__name__
        connection.last_error_at = _utcnow()
        connection.updated_at = _utcnow()
        db.add(connection)
        db.flush()
        raise RuntimeError(str(exc)) from exc

    return _persist_refreshed_connection(db, connection, token_payload)


def _redirect_with_query(base_url: str, **params: str) -> str:
    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value is not None})
    return urlunparse(parsed._replace(query=urlencode(query)))


def list_social_connections(db: Session) -> list[dict]:
    account = seed_default_account(db)
    connections = (
        db.query(SocialConnection)
        .filter(SocialConnection.account_id == account.id)
        .order_by(SocialConnection.platform.asc(), SocialConnection.created_at.desc())
        .all()
    )
    return [_serialize_connection_summary(item) for item in connections]


def begin_youtube_authorization(db: Session, return_path: str | None = None) -> dict:
    _require_social_configuration()
    account = seed_default_account(db)
    existing_default = (
        db.query(SocialConnection)
        .filter(
            SocialConnection.account_id == account.id,
            SocialConnection.platform == YOUTUBE_PLATFORM,
            SocialConnection.is_default.is_(True),
            SocialConnection.connection_status == "active",
        )
        .first()
    )
    raw_state, state_record = create_oauth_state(
        db,
        platform=YOUTUBE_PLATFORM,
        return_path=return_path,
        account_id=account.id,
    )
    authorization_request = build_authorization_request(
        raw_state,
        force_consent=not bool(existing_default and existing_default.encrypted_refresh_token),
    )
    db.commit()
    return {
        "platform": YOUTUBE_PLATFORM,
        "authorization_url": authorization_request.authorization_url,
        "expires_at": state_record.expires_at,
    }


def _clear_default_youtube_connection(db: Session, account_id: str, *, except_connection_id: str | None = None) -> None:
    others = (
        db.query(SocialConnection)
        .filter(
            SocialConnection.account_id == account_id,
            SocialConnection.platform == YOUTUBE_PLATFORM,
            SocialConnection.is_default.is_(True),
        )
        .all()
    )
    for item in others:
        if except_connection_id and item.id == except_connection_id:
            continue
        item.is_default = False
        item.updated_at = _utcnow()
        db.add(item)


def complete_youtube_callback(
    db: Session,
    *,
    state: str | None,
    code: str | None,
    error: str | None,
) -> str:
    _require_social_configuration()
    settings = get_settings()
    if not state:
        return _redirect_with_query(
            settings.google_oauth_frontend_error_url,
            platform=YOUTUBE_PLATFORM,
            error_code="missing_state",
        )

    try:
        oauth_state = consume_oauth_state(db, raw_state=state, platform=YOUTUBE_PLATFORM)
    except OAuthStateError as exc:
        db.rollback()
        return _redirect_with_query(
            settings.google_oauth_frontend_error_url,
            platform=YOUTUBE_PLATFORM,
            error_code="invalid_state",
            detail_code=exc.__class__.__name__.lower(),
        )

    if error:
        db.commit()
        return _redirect_with_query(
            settings.google_oauth_frontend_error_url,
            platform=YOUTUBE_PLATFORM,
            error_code="provider_denied",
            return_path=oauth_state.return_path,
        )
    if not code:
        db.commit()
        return _redirect_with_query(
            settings.google_oauth_frontend_error_url,
            platform=YOUTUBE_PLATFORM,
            error_code="missing_code",
            return_path=oauth_state.return_path,
        )

    try:
        token_payload = exchange_callback_code(code)
    except YouTubeOAuthError as exc:
        db.commit()
        return _redirect_with_query(
            settings.google_oauth_frontend_error_url,
            platform=YOUTUBE_PLATFORM,
            error_code=getattr(exc, "error_code", "oauth_exchange_failed"),
            return_path=oauth_state.return_path,
        )
    except (SocialTokenCryptoError, SocialConnectionConfigurationError):
        db.commit()
        return _redirect_with_query(
            settings.google_oauth_frontend_error_url,
            platform=YOUTUBE_PLATFORM,
            error_code="oauth_exchange_failed",
            return_path=oauth_state.return_path,
        )

    existing = (
        db.query(SocialConnection)
        .filter(
            SocialConnection.account_id == oauth_state.account_id,
            SocialConnection.platform == YOUTUBE_PLATFORM,
            SocialConnection.external_account_id == token_payload.external_account_id,
        )
        .first()
    )
    access_ciphertext, cipher_version = encrypt_secret(token_payload.access_token, purpose="access token")
    refresh_ciphertext = None
    if token_payload.refresh_token:
        refresh_ciphertext, _ = encrypt_secret(token_payload.refresh_token, purpose="refresh token")

    if existing is None:
        connection = SocialConnection(
            account_id=oauth_state.account_id,
            platform=YOUTUBE_PLATFORM,
            external_account_id=token_payload.external_account_id,
            connected_at=_utcnow(),
            created_at=_utcnow(),
        )
    else:
        connection = existing

    _clear_default_youtube_connection(db, oauth_state.account_id, except_connection_id=connection.id)
    connection.display_name = token_payload.display_name
    connection.username = token_payload.username
    connection.encrypted_access_token = access_ciphertext
    if refresh_ciphertext is not None:
        connection.encrypted_refresh_token = refresh_ciphertext
    connection.token_cipher_version = cipher_version
    connection.token_expires_at = token_payload.token_expiry
    connection.granted_scopes_json = list(token_payload.granted_scopes)
    connection.connection_status = "active"
    connection.provider_metadata_json = dict(token_payload.provider_metadata)
    connection.is_default = True
    connection.last_refresh_at = _utcnow()
    connection.last_error_code = None
    connection.last_error_at = None
    connection.connected_at = connection.connected_at or _utcnow()
    connection.disconnected_at = None
    connection.updated_at = _utcnow()
    db.add(connection)
    db.commit()

    return _redirect_with_query(
        settings.google_oauth_frontend_success_url,
        platform=YOUTUBE_PLATFORM,
        status="connected",
        connection_id=connection.id,
        return_path=oauth_state.return_path,
    )


def refresh_social_connection(db: Session, connection_id: str) -> dict:
    _require_social_configuration()
    connection = db.get(SocialConnection, connection_id)
    if connection is None:
        raise ValueError("Social connection not found")
    if connection.connection_status == "disconnected":
        raise RuntimeError("Disconnected social connections cannot be refreshed.")
    if connection.platform != YOUTUBE_PLATFORM:
        raise RuntimeError("Only YouTube connections are supported in Sprint 1A.")
    if not connection.encrypted_refresh_token:
        raise RuntimeError("This connection does not have a stored refresh token.")

    refresh_youtube_connection_tokens_if_needed(db, connection, force=True)
    db.commit()
    return _serialize_connection_summary(connection)


def disconnect_social_connection(db: Session, connection_id: str) -> dict:
    connection = db.get(SocialConnection, connection_id)
    if connection is None:
        raise ValueError("Social connection not found")
    if connection.connection_status == "disconnected":
        return _serialize_connection_summary(connection)
    connection.connection_status = "disconnected"
    connection.encrypted_access_token = None
    connection.encrypted_refresh_token = None
    connection.token_expires_at = None
    connection.is_default = False
    connection.disconnected_at = _utcnow()
    connection.updated_at = _utcnow()
    db.add(connection)
    db.commit()
    return _serialize_connection_summary(connection)
