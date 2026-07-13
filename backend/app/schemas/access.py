from pydantic import BaseModel


class AccessLoginRequest(BaseModel):
    password: str


class AccessLoginResponse(BaseModel):
    auth_enabled: bool
    token: str


class AccessStatusResponse(BaseModel):
    auth_enabled: bool
    authenticated: bool
    account_deleted: bool = False
    environment: str
