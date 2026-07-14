from fastapi import APIRouter, Depends, Request, Response

from app.config import get_settings
from app.schemas.access import AccessLoginRequest, AccessLoginResponse, AccessLogoutResponse, AccessStatusResponse
from app.services.access_service import (
    get_auth_status,
    issue_login_session,
    logout_all_sessions,
    logout_current_session,
    require_app_access,
    require_csrf_protection,
    require_optional_csrf_protection,
    validate_access_password,
)
from app.db.session import get_db
from sqlalchemy.orm import Session
from app.services.rate_limit_service import limit_from_settings

router = APIRouter(prefix="/access", tags=["access"])


@router.get("/status", response_model=AccessStatusResponse)
def access_status(auth_state: dict[str, bool] = Depends(get_auth_status)):
    settings = get_settings()
    return AccessStatusResponse(
        auth_enabled=auth_state["auth_enabled"],
        authenticated=auth_state["authenticated"],
        account_deleted=auth_state.get("account_deleted", False),
        csrf_token=auth_state.get("csrf_token"),
        session_expires_at=auth_state.get("session_expires_at"),
        environment=settings.environment,
    )


@router.post("/login", response_model=AccessLoginResponse)
def access_login(
    request: Request,
    payload: AccessLoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(
        limit_from_settings(
            "access-login",
            attempts_setting="login_rate_limit_attempts",
            window_setting="login_rate_limit_window_seconds",
        )
    ),
):
    settings = get_settings()
    validate_access_password(payload.password, settings)
    return AccessLoginResponse(**issue_login_session(db, request=request, response=response, settings=settings))


@router.post("/logout", response_model=AccessLogoutResponse, dependencies=[Depends(require_optional_csrf_protection)])
def access_logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    return AccessLogoutResponse(**logout_current_session(db, request, response))


@router.post(
    "/logout-all",
    response_model=AccessLogoutResponse,
    dependencies=[Depends(require_app_access), Depends(require_csrf_protection)],
)
def access_logout_all(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    return AccessLogoutResponse(**logout_all_sessions(db, request, response))
