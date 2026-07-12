from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.social_connections import (
    SocialAuthorizeRequest,
    SocialAuthorizeResponse,
    SocialConnectionListResponse,
    SocialConnectionMutationResponse,
)
from app.services.access_service import require_app_access
from app.services.social_connection_service import (
    SocialConnectionConfigurationError,
    begin_youtube_authorization,
    complete_youtube_callback,
    disconnect_social_connection,
    list_social_connections,
    refresh_social_connection,
)


router = APIRouter(
    prefix="/social-connections",
    tags=["social-connections"],
)


@router.get("", response_model=SocialConnectionListResponse)
def get_social_connections(
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    return SocialConnectionListResponse(items=list_social_connections(db))


@router.post("/youtube/authorize", response_model=SocialAuthorizeResponse)
def authorize_youtube_connection(
    payload: SocialAuthorizeRequest,
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    try:
        return SocialAuthorizeResponse(**begin_youtube_authorization(db, payload.return_path))
    except SocialConnectionConfigurationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/youtube/callback")
def youtube_callback(
    state: str | None = Query(default=None),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        return RedirectResponse(complete_youtube_callback(db, state=state, code=code, error=error), status_code=302)
    except SocialConnectionConfigurationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{connection_id}/refresh", response_model=SocialConnectionMutationResponse)
def refresh_connection(
    connection_id: UUID,
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    try:
        return SocialConnectionMutationResponse(connection=refresh_social_connection(db, str(connection_id)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SocialConnectionConfigurationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{connection_id}", response_model=SocialConnectionMutationResponse)
def disconnect_connection(
    connection_id: UUID,
    _access: None = Depends(require_app_access),
    db: Session = Depends(get_db),
):
    try:
        return SocialConnectionMutationResponse(connection=disconnect_social_connection(db, str(connection_id)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
