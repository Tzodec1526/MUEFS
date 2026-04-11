"""Redis-backed (or in-memory) rate limiting with stricter tiers for search and documents."""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import settings

logger = logging.getLogger(__name__)

_mem_store: dict[str, list[float]] = defaultdict(list)
_mem_last_cleanup = 0.0
_MEM_CLEANUP_INTERVAL = 300.0
_MEM_MAX_KEYS = 10000

_redis_client = None


def _path_bucket(path: str) -> str:
    if path.rstrip("/").endswith("/cases/search"):
        return "search"
    if "/documents/" in path and path.endswith("/download"):
        return "document"
    if "/documents/" in path and path.endswith("/verify"):
        return "document"
    return "default"


def _limit_for_bucket(bucket: str) -> int:
    if bucket == "search":
        return settings.rate_limit_search_per_minute
    if bucket == "document":
        return settings.rate_limit_document_per_minute
    return settings.rate_limit_default_per_minute


async def _redis_check_allow(client_ip: str, bucket: str) -> bool:
    import redis.asyncio as aioredis

    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    window = int(time.time() // 60)
    key = f"muefs:rl:{bucket}:{client_ip}:{window}"
    limit = _limit_for_bucket(bucket)
    try:
        n = await _redis_client.incr(key)
        if n == 1:
            await _redis_client.expire(key, 120)
        return n <= limit
    except Exception as exc:
        logger.warning("Redis rate limit failed; allowing request: %s", exc)
        return True


def _memory_check_allow(client_ip: str, bucket: str) -> bool:
    global _mem_last_cleanup
    now = time.time()
    window_sec = 60.0
    limit = _limit_for_bucket(bucket)
    key = f"{bucket}:{client_ip}"

    if now - _mem_last_cleanup > _MEM_CLEANUP_INTERVAL:
        stale = [k for k, ts in _mem_store.items() if not ts or now - ts[-1] > window_sec]
        for k in stale[:_MEM_MAX_KEYS]:
            del _mem_store[k]
        _mem_last_cleanup = now

    _mem_store[key] = [t for t in _mem_store[key] if now - t < window_sec]
    if len(_mem_store[key]) >= limit:
        return False
    _mem_store[key].append(now)
    return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        bucket = _path_bucket(path)

        if settings.rate_limit_backend == "redis":
            allowed = await _redis_check_allow(client_ip, bucket)
        else:
            allowed = _memory_check_allow(client_ip, bucket)

        if not allowed:
            return Response(
                content='{"detail":"Rate limit exceeded. Try again later."}',
                status_code=429,
                media_type="application/json",
            )
        return await call_next(request)


async def close_rate_limit_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
