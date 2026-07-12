from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models import OAuthState
from app.services.pipeline_service import seed_default_account


OAUTH_STATE_TTL_MINUTES = 10


class OAuthStateError(RuntimeError):
    """Raised when OAuth state creation or validation fails."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _coerce_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _hash_state(raw_state: str) -> str:
    return hashlib.sha256(raw_state.encode("utf-8")).hexdigest()


def validate_return_path(return_path: str | None) -> str | None:
    if return_path is None or not return_path.strip():
        return None
    value = return_path.strip()
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or value.startswith("//") or not value.startswith("/"):
        raise OAuthStateError("Return path must be a safe application-relative path.")
    if "\\" in value:
        raise OAuthStateError("Return path must not contain backslashes.")
    return value


def create_oauth_state(
    db: Session,
    *,
    platform: str,
    return_path: str | None = None,
    account_id: str | None = None,
) -> tuple[str, OAuthState]:
    account = seed_default_account(db) if account_id is None else None
    raw_state = secrets.token_urlsafe(32)
    record = OAuthState(
        account_id=account_id or account.id,
        platform=platform,
        state_hash=_hash_state(raw_state),
        return_path=validate_return_path(return_path),
        expires_at=_utcnow() + timedelta(minutes=OAUTH_STATE_TTL_MINUTES),
        created_at=_utcnow(),
    )
    db.add(record)
    db.flush()
    return raw_state, record


def consume_oauth_state(
    db: Session,
    *,
    raw_state: str,
    platform: str,
) -> OAuthState:
    record = (
        db.query(OAuthState)
        .filter(OAuthState.state_hash == _hash_state(raw_state))
        .first()
    )
    if record is None:
        raise OAuthStateError("OAuth state is invalid.")
    if record.platform != platform:
        raise OAuthStateError("OAuth state does not match the requested platform.")
    if record.consumed_at is not None:
        raise OAuthStateError("OAuth state has already been used.")
    if _coerce_aware(record.expires_at) <= _utcnow():
        raise OAuthStateError("OAuth state has expired.")
    record.consumed_at = _utcnow()
    db.add(record)
    db.flush()
    return record
