from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import SessionLocal, get_db
from app.models import Account, AppSession
from app.services.pipeline_service import DEFAULT_ACCOUNT_NAME
from app.services.request_security_service import enforce_origin_allowed


ACCESS_SCOPE = "private-access"
CSRF_ERROR_CODE = "csrf_validation_failed"
SESSION_REVOKED_ERROR_CODE = "access_session_revoked"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _sign_value(value: str, *, settings: Settings | None = None, purpose: str) -> str:
    active_settings = _active_settings(settings)
    secret = active_settings.session_secret_value().encode("utf-8")
    digest = hmac.new(secret, f"{purpose}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def _password_fingerprint(settings: Settings | None = None) -> str:
    active_settings = _active_settings(settings)
    return _sign_value(active_settings.app_access_password, settings=active_settings, purpose="access-password")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _account_deleted_or_disabled(account: Account | None) -> bool:
    return account is not None and account.account_status != "active"


def _get_default_account(db: Session) -> Account:
    account = db.query(Account).filter(Account.name == DEFAULT_ACCOUNT_NAME).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Default account not found.")
    return account


def _validate_account_is_active(account: Account) -> None:
    if account.account_status == "deleted":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account has been deleted.")
    if account.account_status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is unavailable.")


def _session_expiry(settings: Settings | None = None) -> datetime:
    active_settings = _active_settings(settings)
    return _utcnow() + timedelta(seconds=active_settings.session_cookie_max_age_seconds)


def _session_metadata_for_request(request: Request, csrf_token: str) -> dict[str, Any]:
    user_agent = request.headers.get("User-Agent", "")
    return {
        "csrf_token": csrf_token,
        "user_agent_sha256": _sha256(user_agent) if user_agent else None,
    }


def set_session_cookie(response: Response, raw_session_token: str, *, expires_at: datetime, settings: Settings | None = None) -> None:
    active_settings = _active_settings(settings)
    if expires_at.tzinfo is None:
        expires_value = expires_at.replace(tzinfo=UTC)
    else:
        expires_value = expires_at.astimezone(UTC)
    response.set_cookie(
        key=active_settings.session_cookie_name,
        value=raw_session_token,
        httponly=True,
        secure=active_settings.session_cookie_secure(),
        samesite=active_settings.session_cookie_samesite,
        max_age=active_settings.session_cookie_max_age_seconds,
        expires=expires_value,
        domain=active_settings.session_cookie_domain_value(),
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings | None = None) -> None:
    active_settings = _active_settings(settings)
    response.delete_cookie(
        key=active_settings.session_cookie_name,
        domain=active_settings.session_cookie_domain_value(),
        path="/",
    )


def _read_session_token(request: Request, settings: Settings | None = None) -> str | None:
    active_settings = _active_settings(settings)
    return request.cookies.get(active_settings.session_cookie_name)


def create_server_session(db: Session, request: Request, settings: Settings | None = None) -> tuple[AppSession, str, str]:
    active_settings = _active_settings(settings)
    account = _get_default_account(db)
    _validate_account_is_active(account)
    raw_session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    session = AppSession(
        account_id=account.id,
        token_hash=_sign_value(raw_session_token, settings=active_settings, purpose="session-token"),
        csrf_token_hash=_sign_value(csrf_token, settings=active_settings, purpose="csrf-token"),
        password_fingerprint=_password_fingerprint(active_settings),
        expires_at=_session_expiry(active_settings),
        last_used_at=_utcnow(),
        session_metadata_json=_session_metadata_for_request(request, csrf_token),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, raw_session_token, csrf_token


def revoke_session(db: Session, session: AppSession, *, reason: str) -> AppSession:
    if session.revoked_at is None:
        session.revoked_at = _utcnow()
        session.revocation_reason = reason
        session.updated_at = _utcnow()
        db.add(session)
    return session


def revoke_all_account_sessions(db: Session, account_id: str, *, reason: str) -> int:
    sessions = (
        db.query(AppSession)
        .filter(AppSession.account_id == account_id, AppSession.revoked_at.is_(None))
        .all()
    )
    for session in sessions:
        revoke_session(db, session, reason=reason)
    return len(sessions)


def _session_csrf_token(session: AppSession) -> str | None:
    value = (session.session_metadata_json or {}).get("csrf_token")
    return value if isinstance(value, str) and value else None


def _mark_session_expired(db: Session, session: AppSession) -> None:
    revoke_session(db, session, reason="expired")
    db.commit()


def _load_session_row(db: Session, raw_session_token: str, *, settings: Settings | None = None) -> AppSession | None:
    active_settings = _active_settings(settings)
    token_hash = _sign_value(raw_session_token, settings=active_settings, purpose="session-token")
    return db.query(AppSession).filter(AppSession.token_hash == token_hash).first()


def load_authenticated_session(
    db: Session,
    request: Request,
    *,
    settings: Settings | None = None,
    allow_missing: bool = False,
) -> AppSession | None:
    active_settings = _active_settings(settings)
    raw_session_token = _read_session_token(request, active_settings)
    if not raw_session_token:
        if allow_missing:
            return None
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access required.")

    session = _load_session_row(db, raw_session_token, settings=active_settings)
    if session is None:
        if allow_missing:
            return None
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access required.")
    if session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": SESSION_REVOKED_ERROR_CODE, "message": "Access session expired."},
        )
    if session.expires_at <= _utcnow():
        _mark_session_expired(db, session)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": SESSION_REVOKED_ERROR_CODE, "message": "Access session expired."},
        )

    account = db.get(Account, session.account_id)
    if account is None or _account_deleted_or_disabled(account):
        revoke_session(db, session, reason="account_disabled" if account is None or account.account_status != "deleted" else "account_deleted")
        db.commit()
        message = "Account has been deleted." if account is not None and account.account_status == "deleted" else "Account is unavailable."
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)

    current_password_fingerprint = _password_fingerprint(active_settings)
    if session.password_fingerprint != current_password_fingerprint:
        revoke_session(db, session, reason="password_changed")
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": SESSION_REVOKED_ERROR_CODE, "message": "Access session expired."},
        )

    session.last_used_at = _utcnow()
    session.updated_at = _utcnow()
    db.add(session)
    request.state.app_session = session
    request.state.authenticated_account_id = account.id
    request.state.authenticated_account_status = account.account_status
    return session


def issue_login_session(
    db: Session,
    request: Request,
    response: Response,
    settings: Settings | None = None,
) -> dict[str, Any]:
    active_settings = _active_settings(settings)
    session, raw_session_token, csrf_token = create_server_session(db, request, active_settings)
    set_session_cookie(response, raw_session_token, expires_at=session.expires_at, settings=active_settings)
    return {
        "auth_enabled": True,
        "authenticated": True,
        "account_deleted": False,
        "csrf_token": csrf_token,
        "session_expires_at": session.expires_at,
    }


def logout_current_session(
    db: Session,
    request: Request,
    response: Response,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    active_settings = _active_settings(settings)
    session = None
    raw_session_token = _read_session_token(request, active_settings)
    if raw_session_token:
        session = _load_session_row(db, raw_session_token, settings=active_settings)
    if session is not None:
        revoke_session(db, session, reason="logout")
        db.commit()
    clear_session_cookie(response, active_settings)
    return {
        "auth_enabled": active_settings.auth_enabled,
        "authenticated": False,
        "account_deleted": False,
        "logged_out": True,
        "session_expires_at": None,
    }


def logout_all_sessions(
    db: Session,
    request: Request,
    response: Response,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    active_settings = _active_settings(settings)
    session = load_authenticated_session(db, request, settings=active_settings)
    revoke_all_account_sessions(db, session.account_id, reason="logout_all")
    db.commit()
    clear_session_cookie(response, active_settings)
    return {
        "auth_enabled": active_settings.auth_enabled,
        "authenticated": False,
        "account_deleted": False,
        "logged_out": True,
        "session_expires_at": None,
    }


def require_app_access(
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    settings = get_settings()
    account = _get_default_account(db)
    _validate_account_is_active(account)
    if not settings.auth_enabled:
        request.state.authenticated_account_id = account.id
        request.state.authenticated_account_status = account.account_status
        return
    load_authenticated_session(db, request, settings=settings)
    db.commit()


def require_csrf_protection(
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    settings = get_settings()
    if not settings.auth_enabled:
        return
    session = getattr(request.state, "app_session", None)
    if not isinstance(session, AppSession):
        session = load_authenticated_session(db, request, settings=settings)
    enforce_origin_allowed(request)
    provided = request.headers.get(settings.csrf_header_name)
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": CSRF_ERROR_CODE, "message": "A valid CSRF token is required."},
        )
    expected_hash = _sign_value(provided, settings=settings, purpose="csrf-token")
    if not hmac.compare_digest(session.csrf_token_hash, expected_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": CSRF_ERROR_CODE, "message": "A valid CSRF token is required."},
        )


def require_optional_csrf_protection(
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    settings = get_settings()
    if not settings.auth_enabled:
        return
    raw_session_token = _read_session_token(request, settings)
    if not raw_session_token:
        return
    session = _load_session_row(db, raw_session_token, settings=settings)
    if session is None or session.revoked_at is not None or session.expires_at <= _utcnow():
        return
    enforce_origin_allowed(request)
    provided = request.headers.get(settings.csrf_header_name)
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": CSRF_ERROR_CODE, "message": "A valid CSRF token is required."},
        )
    expected_hash = _sign_value(provided, settings=settings, purpose="csrf-token")
    if not hmac.compare_digest(session.csrf_token_hash, expected_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": CSRF_ERROR_CODE, "message": "A valid CSRF token is required."},
        )


def get_auth_status(
    request: Request,
    db: Session = Depends(get_db),
) -> Mapping[str, object]:
    settings = get_settings()
    account = _get_default_account(db)
    if account.account_status == "deleted":
        return {
            "auth_enabled": settings.auth_enabled,
            "authenticated": False,
            "account_deleted": True,
            "csrf_token": None,
            "session_expires_at": None,
        }
    if account.account_status != "active":
        return {
            "auth_enabled": settings.auth_enabled,
            "authenticated": False,
            "account_deleted": False,
            "csrf_token": None,
            "session_expires_at": None,
        }
    if not settings.auth_enabled:
        return {
            "auth_enabled": False,
            "authenticated": True,
            "account_deleted": False,
            "csrf_token": None,
            "session_expires_at": None,
        }
    try:
        session = load_authenticated_session(db, request, settings=settings, allow_missing=True)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            return {
                "auth_enabled": True,
                "authenticated": False,
                "account_deleted": True,
                "csrf_token": None,
                "session_expires_at": None,
            }
        return {
            "auth_enabled": True,
            "authenticated": False,
            "account_deleted": False,
            "csrf_token": None,
            "session_expires_at": None,
        }
    if session is None:
        return {
            "auth_enabled": True,
            "authenticated": False,
            "account_deleted": False,
            "csrf_token": None,
            "session_expires_at": None,
        }
    db.commit()
    return {
        "auth_enabled": True,
        "authenticated": True,
        "account_deleted": False,
        "csrf_token": _session_csrf_token(session),
        "session_expires_at": session.expires_at,
    }


def validate_access_password(password: str, settings: Settings | None = None) -> None:
    active_settings = settings or get_settings()
    with SessionLocal() as db:
        account = _get_default_account(db)
        _validate_account_is_active(account)
    if not active_settings.auth_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Private access mode is disabled.")
    if not hmac.compare_digest(password, active_settings.app_access_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access password.")
