from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request, status
from redis import Redis
from redis.exceptions import RedisError

from app.config import get_settings


RATE_LIMIT_ERROR_CODE = "rate_limit_exceeded"

_local_lock = threading.Lock()
_local_windows: dict[str, deque[float]] = defaultdict(deque)


class RateLimitExceededError(HTTPException):
    def __init__(self, retry_after_seconds: int):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": RATE_LIMIT_ERROR_CODE,
                "message": "Too many requests. Please wait before trying again.",
                "retry_after_seconds": retry_after_seconds,
            },
            headers={"Retry-After": str(retry_after_seconds)},
        )


def _hash_identifier(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redis_client() -> Redis | None:
    settings = get_settings()
    if settings.is_development_like_environment() or os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    if not settings.redis_url:
        return None
    try:
        client = Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return client
    except RedisError:
        return None


def _apply_local_window(key: str, *, limit: int, window_seconds: int) -> int:
    now = time.time()
    cutoff = now - window_seconds
    with _local_lock:
        bucket = _local_windows[key]
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(bucket[0] + window_seconds - now))
            raise RateLimitExceededError(retry_after)
        bucket.append(now)
        return max(0, limit - len(bucket))


def _apply_redis_window(client: Redis, key: str, *, limit: int, window_seconds: int) -> int:
    now = int(time.time())
    window_start = now - window_seconds
    pipeline = client.pipeline()
    pipeline.zremrangebyscore(key, 0, window_start)
    pipeline.zcard(key)
    pipeline.zadd(key, {f"{now}:{time.time_ns()}": now})
    pipeline.expire(key, window_seconds)
    _removed, count_before, _added, _expire = pipeline.execute()
    count_before = int(count_before or 0)
    if count_before >= limit:
        raise RateLimitExceededError(window_seconds)
    return max(0, limit - (count_before + 1))


def enforce_rate_limit(key: str, *, limit: int, window_seconds: int) -> None:
    client = _redis_client()
    if client is not None:
        try:
            _apply_redis_window(client, key, limit=limit, window_seconds=window_seconds)
            return
        except RedisError:
            pass
    _apply_local_window(key, limit=limit, window_seconds=window_seconds)


def _client_identity(request: Request) -> str:
    forwarded_ip = getattr(request.state, "client_ip", None)
    if isinstance(forwarded_ip, str) and forwarded_ip:
        return forwarded_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _account_identity(request: Request) -> str | None:
    account_id = getattr(request.state, "authenticated_account_id", None)
    if isinstance(account_id, str) and account_id:
        return account_id
    return None


def limit_dependency(
    scope: str,
    *,
    limit: int,
    window_seconds: int,
    include_account: bool = False,
) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        parts = [scope, _client_identity(request)]
        if include_account:
            account_id = _account_identity(request)
            if account_id:
                parts.append(account_id)
        key = f"rate-limit:{scope}:{_hash_identifier('|'.join(parts))}"
        enforce_rate_limit(key, limit=limit, window_seconds=window_seconds)

    return dependency


def limit_from_settings(
    scope: str,
    *,
    attempts_setting: str,
    window_setting: str,
    include_account: bool = False,
) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        settings = get_settings()
        limit = int(getattr(settings, attempts_setting))
        window_seconds = int(getattr(settings, window_setting))
        return limit_dependency(
            scope,
            limit=limit,
            window_seconds=window_seconds,
            include_account=include_account,
        )(request)

    return dependency


def reset_local_rate_limits() -> None:
    with _local_lock:
        _local_windows.clear()
