from fastapi import APIRouter, Depends

from app.config import get_settings
from app.schemas.access import AccessLoginRequest, AccessLoginResponse, AccessStatusResponse
from app.services.access_service import get_auth_status, issue_access_token, validate_access_password

router = APIRouter(prefix="/access", tags=["access"])


@router.get("/status", response_model=AccessStatusResponse)
def access_status(auth_state: dict[str, bool] = Depends(get_auth_status)):
    settings = get_settings()
    return AccessStatusResponse(
        auth_enabled=auth_state["auth_enabled"],
        authenticated=auth_state["authenticated"],
        environment=settings.environment,
    )


@router.post("/login", response_model=AccessLoginResponse)
def access_login(payload: AccessLoginRequest):
    settings = get_settings()
    validate_access_password(payload.password, settings)
    return AccessLoginResponse(auth_enabled=True, token=issue_access_token(settings))
