from __future__ import annotations

from dataclasses import dataclass
from typing import Any


TRANSIENT_HTTP_STATUSES = {500, 502, 503, 504}


@dataclass
class PublicationProviderError(RuntimeError):
    code: str
    safe_message: str
    retryable: bool
    reconnect_required: bool = False
    outcome_uncertain: bool = False
    permanent: bool = False

    def __str__(self) -> str:
        return self.safe_message


def _nested_error_reason(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    error = payload.get("error")
    if not isinstance(error, dict):
        return None, None
    errors = error.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            return (
                str(first.get("reason")) if first.get("reason") else None,
                str(first.get("message")) if first.get("message") else None,
            )
    return None, str(error.get("message")) if error.get("message") else None


def classify_youtube_http_error(
    *,
    status_code: int | None,
    payload: dict[str, Any] | None,
    fallback_message: str,
    during_status_poll: bool = False,
    has_provider_video_id: bool = False,
    has_session_uri: bool = False,
) -> PublicationProviderError:
    safe_reason, safe_message = _nested_error_reason(payload or {})
    message = safe_message or fallback_message

    if status_code in {401, 403} and safe_reason in {"authError", "oauth2InvalidToken", "invalidCredentials"}:
        return PublicationProviderError(
            code="youtube_credentials_invalid",
            safe_message="The YouTube connection credentials are no longer valid. Reconnect is required.",
            retryable=False,
            reconnect_required=True,
            permanent=True,
        )
    if status_code == 403 and safe_reason in {"insufficientPermissions", "forbidden"}:
        return PublicationProviderError(
            code="youtube_scope_missing",
            safe_message="The active YouTube connection is missing required upload permissions.",
            retryable=False,
            reconnect_required=True,
            permanent=True,
        )
    if status_code == 403 and safe_reason in {"quotaExceeded", "uploadLimitExceeded"}:
        return PublicationProviderError(
            code=safe_reason,
            safe_message="YouTube rejected the request because the project quota or upload limit has been exceeded.",
            retryable=False,
            permanent=True,
        )
    if status_code == 400 and safe_reason in {"invalidTitle", "invalidDescription", "invalidTags", "invalidCategoryId"}:
        return PublicationProviderError(
            code=safe_reason,
            safe_message=message,
            retryable=False,
            permanent=True,
        )
    if status_code == 400 and safe_reason in {"invalidPrivacyStatus", "invalidMetadata", "mediaBodyRequired"}:
        return PublicationProviderError(
            code=safe_reason or "invalid_metadata",
            safe_message=message,
            retryable=False,
            permanent=True,
        )
    if during_status_poll and status_code == 404:
        return PublicationProviderError(
            code="youtube_video_not_found",
            safe_message="YouTube has not exposed the uploaded video state yet.",
            retryable=True,
            outcome_uncertain=has_provider_video_id or has_session_uri,
        )
    if status_code in TRANSIENT_HTTP_STATUSES:
        return PublicationProviderError(
            code="youtube_transient_error",
            safe_message="YouTube returned a temporary server error.",
            retryable=True,
            outcome_uncertain=has_provider_video_id or has_session_uri,
        )
    return PublicationProviderError(
        code=safe_reason or "youtube_unknown_error",
        safe_message=message,
        retryable=bool(status_code and status_code >= 500),
        outcome_uncertain=has_provider_video_id or has_session_uri,
        permanent=bool(status_code and status_code < 500 and status_code != 404),
    )


def classify_youtube_transport_error(
    *,
    message: str,
    has_provider_video_id: bool = False,
    has_session_uri: bool = False,
) -> PublicationProviderError:
    lowered = message.lower()
    if "timeout" in lowered:
        return PublicationProviderError(
            code="youtube_timeout",
            safe_message="The YouTube request timed out before completion.",
            retryable=True,
            outcome_uncertain=has_provider_video_id or has_session_uri,
        )
    return PublicationProviderError(
        code="youtube_network_error",
        safe_message="The YouTube request failed before completion because of a network or transport error.",
        retryable=True,
        outcome_uncertain=has_provider_video_id or has_session_uri,
    )
