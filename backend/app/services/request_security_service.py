from __future__ import annotations

import ipaddress
from uuid import uuid4

from fastapi import HTTPException, Request, status

from app.config import Settings, get_settings


APPROVED_PUBLIC_API_HEADERS = {
    "Accept",
    "Content-Type",
    "X-CSRF-Token",
}


def _ip_in_trusted_proxy_ranges(ip_value: str, cidrs: list[str]) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip_value)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            if ip_obj in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def attach_request_context(request: Request, settings: Settings | None = None) -> None:
    active_settings = settings or get_settings()
    request.state.request_id = request.headers.get("X-Request-ID") or uuid4().hex
    request.state.client_ip = request.client.host if request.client else "unknown"
    request.state.forwarded_proto = request.url.scheme
    if not active_settings.trust_proxy_headers:
        return
    remote_ip = request.client.host if request.client else ""
    if not _ip_in_trusted_proxy_ranges(remote_ip, active_settings.trusted_proxy_cidrs_list()):
        return
    forwarded_proto = request.headers.get("X-Forwarded-Proto") or request.headers.get("X-Forwarded-Scheme")
    if forwarded_proto in {"http", "https"}:
        request.state.forwarded_proto = forwarded_proto
    cf_ip = request.headers.get("CF-Connecting-IP")
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    candidate_ip = cf_ip or (x_forwarded_for.split(",")[0].strip() if x_forwarded_for else "")
    if candidate_ip:
        request.state.client_ip = candidate_ip


def enforce_origin_allowed(request: Request, *, origin: str | None = None) -> None:
    active_origin = origin or request.headers.get("Origin")
    if not active_origin:
        return
    allowed_origins = get_settings().cors_allowed_origins_list()
    if active_origin not in allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "origin_not_allowed", "message": "This origin is not allowed for authenticated requests."},
        )
