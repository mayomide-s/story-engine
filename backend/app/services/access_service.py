from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Mapping

from fastapi import Header, HTTPException, status

from app.config import Settings, get_settings

ACCESS_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
TOKEN_SCOPE = "private-access"


def _urlsafe_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _urlsafe_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(f"{raw}{padding}")


def _sign_token_payload(payload_segment: str, settings: Settings) -> str:
    secret = settings.session_secret_value().encode("utf-8")
    digest = hmac.new(secret, payload_segment.encode("utf-8"), hashlib.sha256).digest()
    return _urlsafe_encode(digest)


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def issue_access_token(settings: Settings | None = None) -> str:
    active_settings = settings or get_settings()
    issued_at = int(time.time())
    payload = {
        "scope": TOKEN_SCOPE,
        "iat": issued_at,
        "exp": issued_at + ACCESS_TOKEN_TTL_SECONDS,
        "nonce": secrets.token_urlsafe(12),
    }
    payload_segment = _urlsafe_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature_segment = _sign_token_payload(payload_segment, active_settings)
    return f"{payload_segment}.{signature_segment}"


def verify_access_token(token: str, settings: Settings | None = None) -> Mapping[str, object]:
    active_settings = settings or get_settings()
    if not active_settings.auth_enabled:
        return {"scope": TOKEN_SCOPE, "auth_enabled": False}
    try:
        payload_segment, signature_segment = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.") from exc
    expected_signature = _sign_token_payload(payload_segment, active_settings)
    if not hmac.compare_digest(signature_segment, expected_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.")
    try:
        payload = json.loads(_urlsafe_decode(payload_segment))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.") from exc
    if payload.get("scope") != TOKEN_SCOPE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.")
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access session expired.")
    return payload


def require_app_access(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.auth_enabled:
        return
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access required.")
    verify_access_token(token, settings)


def get_auth_status(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    settings = get_settings()
    if not settings.auth_enabled:
        return {"auth_enabled": False, "authenticated": True}
    token = _extract_bearer_token(authorization)
    if not token:
        return {"auth_enabled": True, "authenticated": False}
    try:
        verify_access_token(token, settings)
    except HTTPException:
        return {"auth_enabled": True, "authenticated": False}
    return {"auth_enabled": True, "authenticated": True}


def validate_access_password(password: str, settings: Settings | None = None) -> None:
    active_settings = settings or get_settings()
    if not active_settings.auth_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Private access mode is disabled.")
    if not hmac.compare_digest(password, active_settings.app_access_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access password.")
