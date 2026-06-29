from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from uuid import UUID

try:
    from pydantic import BaseModel
except Exception:  # pragma: no cover
    BaseModel = None  # type: ignore[assignment]


SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "signed_url",
    "signature",
    "secret",
    "secret_key",
    "token",
    "credential",
    "x-amz-credential",
    "x-amz-signature",
    "x-amz-security-token",
}


def sanitize_for_json(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if BaseModel is not None and isinstance(value, BaseModel):
        return sanitize_for_json(value.model_dump(mode="json"))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return sanitize_for_json(value.to_dict())
    if hasattr(value, "dict") and callable(value.dict):
        return sanitize_for_json(value.dict())
    if isinstance(value, Mapping):
        return {str(key): sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return [sanitize_for_json(item) for item in value]
    if hasattr(value, "__dict__"):
        return sanitize_for_json(vars(value))
    return str(value)


def redact_sensitive_data(value):
    value = sanitize_for_json(value)
    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            if any(sensitive in key.lower() for sensitive in SENSITIVE_KEYS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive_data(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, str):
        lowered = value.lower()
        if (
            "token" in lowered
            or "key" in lowered
            or "x-amz-signature=" in lowered
            or "x-amz-credential=" in lowered
            or "signature=" in lowered
            or "credentials" in lowered
        ):
            return "[REDACTED]"
        return value
    return value
