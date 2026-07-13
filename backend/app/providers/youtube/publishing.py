from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PublicationTarget, SocialConnection
from app.providers.youtube.oauth import GOOGLE_TOKEN_URI, YOUTUBE_OAUTH_SCOPES
from app.services.publication_error_service import (
    PublicationProviderError,
    classify_youtube_http_error,
    classify_youtube_transport_error,
)
from app.services.security import redact_sensitive_data
from app.services.social_connection_service import refresh_youtube_connection_tokens_if_needed
from app.services.social_token_crypto import decrypt_secret


YOUTUBE_RESUMABLE_INSERT_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_VIDEO_LIST_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_CANONICAL_URL_TEMPLATE = "https://www.youtube.com/watch?v={video_id}"
YOUTUBE_VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass(frozen=True)
class YouTubeUploadProgress:
    bytes_sent: int
    total_bytes: int
    session_uri: str
    video_id: str | None = None


@dataclass(frozen=True)
class YouTubeVideoState:
    video_id: str
    upload_status: str | None
    privacy_status: str | None
    processing_status: str | None
    failure_reason: str | None
    rejection_reason: str | None
    raw_status: dict[str, Any]
    raw_processing_details: dict[str, Any]


def _authorized_session(credentials: Credentials) -> AuthorizedSession:
    return AuthorizedSession(credentials)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def build_youtube_video_metadata(target: PublicationTarget) -> dict[str, Any]:
    options = dict(target.options_json or {})
    category_id = str(options.get("category_id") or get_settings().youtube_default_category_id)
    if not category_id.isdigit():
        raise PublicationProviderError(
            code="invalidCategoryId",
            safe_message="The YouTube category must be a numeric category identifier.",
            retryable=False,
            permanent=True,
        )

    return {
        "snippet": {
            "title": target.title,
            "description": target.caption or "",
            "tags": list(target.tags_json or []),
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": target.visibility,
            "selfDeclaredMadeForKids": bool(options.get("self_declared_made_for_kids", False)),
            "containsSyntheticMedia": bool(options.get("contains_synthetic_media", True)),
        },
    }


def _build_credentials(connection: SocialConnection) -> Credentials:
    settings = get_settings()
    access_token = None
    if connection.encrypted_access_token:
        access_token = decrypt_secret(connection.encrypted_access_token, purpose="access token")
    refresh_token = None
    if connection.encrypted_refresh_token:
        refresh_token = decrypt_secret(connection.encrypted_refresh_token, purpose="refresh token")
    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        scopes=list(connection.granted_scopes_json or YOUTUBE_OAUTH_SCOPES),
    )


def build_youtube_session(db: Session, connection: SocialConnection) -> tuple[AuthorizedSession, SocialConnection]:
    refreshed = refresh_youtube_connection_tokens_if_needed(db, connection)
    credentials = _build_credentials(refreshed)
    return _authorized_session(credentials), refreshed


def initiate_resumable_upload(
    db: Session,
    connection: SocialConnection,
    *,
    target: PublicationTarget,
    media_path: Path,
    mime_type: str,
) -> str:
    session, _connection = build_youtube_session(db, connection)
    metadata = build_youtube_video_metadata(target)
    try:
        response = session.post(
            YOUTUBE_RESUMABLE_INSERT_URL,
            params={
                "uploadType": "resumable",
                "part": "snippet,status",
                "notifySubscribers": "false",
            },
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": mime_type,
                "X-Upload-Content-Length": str(media_path.stat().st_size),
            },
            data=json.dumps(metadata),
            timeout=120,
        )
    except Exception as exc:
        raise classify_youtube_transport_error(
            message=redact_sensitive_data(str(exc)),
            has_session_uri=False,
            has_provider_video_id=False,
        ) from exc

    if response.status_code not in {200, 201}:
        payload = _safe_json(response)
        raise classify_youtube_http_error(
            status_code=response.status_code,
            payload=payload,
            fallback_message="YouTube rejected the resumable upload initialization.",
        )

    session_uri = response.headers.get("Location") or response.headers.get("location")
    if not session_uri:
        raise PublicationProviderError(
            code="youtube_missing_resumable_location",
            safe_message="YouTube did not return a resumable upload session.",
            retryable=True,
            outcome_uncertain=False,
        )
    return session_uri


def query_resumable_progress(
    db: Session,
    connection: SocialConnection,
    *,
    session_uri: str,
    total_bytes: int,
) -> int:
    session, _connection = build_youtube_session(db, connection)
    try:
        response = session.put(
            session_uri,
            headers={
                "Content-Length": "0",
                "Content-Range": f"bytes */{total_bytes}",
            },
            timeout=120,
        )
    except Exception as exc:
        raise classify_youtube_transport_error(
            message=redact_sensitive_data(str(exc)),
            has_session_uri=True,
        ) from exc

    if response.status_code == 308:
        uploaded_range = response.headers.get("Range") or response.headers.get("range")
        if not uploaded_range:
            return 0
        match = re.match(r"bytes=0-(\d+)", uploaded_range)
        return int(match.group(1)) + 1 if match else 0
    if response.status_code in {200, 201}:
        return total_bytes

    payload = _safe_json(response)
    raise classify_youtube_http_error(
        status_code=response.status_code,
        payload=payload,
        fallback_message="YouTube resumable upload progress could not be queried.",
        has_session_uri=True,
    )


def upload_media_chunks(
    db: Session,
    connection: SocialConnection,
    *,
    session_uri: str,
    media_path: Path,
    mime_type: str,
    chunk_size: int,
    bytes_sent: int = 0,
    probe_existing_session: bool = False,
) -> YouTubeUploadProgress:
    session, _connection = build_youtube_session(db, connection)
    total_bytes = media_path.stat().st_size
    start_offset = bytes_sent
    if probe_existing_session or bytes_sent:
        start_offset = query_resumable_progress(
            db,
            connection,
            session_uri=session_uri,
            total_bytes=total_bytes,
        )

    with media_path.open("rb") as handle:
        handle.seek(start_offset)
        while start_offset < total_bytes:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            end_offset = start_offset + len(chunk) - 1
            try:
                response = session.put(
                    session_uri,
                    headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Type": mime_type,
                        "Content-Range": f"bytes {start_offset}-{end_offset}/{total_bytes}",
                    },
                    data=chunk,
                    timeout=300,
                )
            except Exception as exc:
                raise classify_youtube_transport_error(
                    message=redact_sensitive_data(str(exc)),
                    has_session_uri=True,
                ) from exc

            if response.status_code == 308:
                range_header = response.headers.get("Range") or response.headers.get("range")
                if range_header:
                    match = re.match(r"bytes=0-(\d+)", range_header)
                    if match:
                        start_offset = int(match.group(1)) + 1
                        continue
                start_offset = end_offset + 1
                continue

            if response.status_code not in {200, 201}:
                payload = _safe_json(response)
                raise classify_youtube_http_error(
                    status_code=response.status_code,
                    payload=payload,
                    fallback_message="YouTube rejected the resumable upload chunk.",
                    has_session_uri=True,
                )

            payload = _safe_json(response)
            video_id = str(payload.get("id") or "").strip()
            if not validate_youtube_video_id(video_id):
                raise PublicationProviderError(
                    code="youtube_invalid_video_id",
                    safe_message="YouTube returned an invalid video identifier after upload completion.",
                    retryable=False,
                    outcome_uncertain=True,
                )
            return YouTubeUploadProgress(
                bytes_sent=total_bytes,
                total_bytes=total_bytes,
                session_uri=session_uri,
                video_id=video_id,
            )

    return YouTubeUploadProgress(
        bytes_sent=min(start_offset, total_bytes),
        total_bytes=total_bytes,
        session_uri=session_uri,
        video_id=None,
    )


def fetch_youtube_video_state(
    db: Session,
    connection: SocialConnection,
    *,
    video_id: str,
) -> YouTubeVideoState:
    if not validate_youtube_video_id(video_id):
        raise PublicationProviderError(
            code="youtube_invalid_video_id",
            safe_message="The stored YouTube video identifier is invalid.",
            retryable=False,
            permanent=True,
        )
    session, _connection = build_youtube_session(db, connection)
    try:
        response = session.get(
            YOUTUBE_VIDEO_LIST_URL,
            params={
                "part": "status,processingDetails",
                "id": video_id,
            },
            timeout=120,
        )
    except Exception as exc:
        raise classify_youtube_transport_error(
            message=redact_sensitive_data(str(exc)),
            has_provider_video_id=True,
        ) from exc

    if response.status_code != 200:
        payload = _safe_json(response)
        raise classify_youtube_http_error(
            status_code=response.status_code,
            payload=payload,
            fallback_message="YouTube video status could not be retrieved.",
            during_status_poll=True,
            has_provider_video_id=True,
        )

    payload = _safe_json(response)
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise PublicationProviderError(
            code="youtube_video_not_found",
            safe_message="YouTube has not exposed the uploaded video state yet.",
            retryable=True,
            outcome_uncertain=True,
        )
    item = items[0] if isinstance(items[0], dict) else {}
    status = item.get("status") if isinstance(item.get("status"), dict) else {}
    processing = item.get("processingDetails") if isinstance(item.get("processingDetails"), dict) else {}
    return YouTubeVideoState(
        video_id=video_id,
        upload_status=str(status.get("uploadStatus")) if status.get("uploadStatus") is not None else None,
        privacy_status=str(status.get("privacyStatus")) if status.get("privacyStatus") is not None else None,
        processing_status=str(processing.get("processingStatus")) if processing.get("processingStatus") is not None else None,
        failure_reason=str(status.get("failureReason")) if status.get("failureReason") is not None else None,
        rejection_reason=str(status.get("rejectionReason")) if status.get("rejectionReason") is not None else None,
        raw_status=status,
        raw_processing_details=processing,
    )


def validate_youtube_video_id(video_id: str | None) -> bool:
    return bool(video_id and YOUTUBE_VIDEO_ID_PATTERN.fullmatch(video_id))


def canonical_watch_url(video_id: str) -> str:
    if not validate_youtube_video_id(video_id):
        raise ValueError("A valid YouTube video ID is required to build the canonical watch URL.")
    return YOUTUBE_CANONICAL_URL_TEMPLATE.format(video_id=video_id)


def compute_retry_delay(attempt_count: int) -> int:
    base_delay = min(300, 10 * (2 ** max(attempt_count - 1, 0)))
    jitter = random.randint(0, 5)
    return base_delay + jitter


def _safe_json(response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
