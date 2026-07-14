from datetime import datetime

from pydantic import BaseModel


class AccessLoginRequest(BaseModel):
    password: str


class AccessLoginResponse(BaseModel):
    auth_enabled: bool
    authenticated: bool
    account_deleted: bool = False
    csrf_token: str | None = None
    session_expires_at: datetime | None = None


class AccessLogoutResponse(BaseModel):
    auth_enabled: bool
    authenticated: bool
    account_deleted: bool = False
    logged_out: bool
    session_expires_at: datetime | None = None


class AccessStatusResponse(BaseModel):
    auth_enabled: bool
    authenticated: bool
    account_deleted: bool = False
    csrf_token: str | None = None
    session_expires_at: datetime | None = None
    environment: str
