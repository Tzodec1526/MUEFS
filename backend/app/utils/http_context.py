"""HTTP request metadata for audit and security logging."""

from fastapi import Request

from app.config import settings


def client_ip(request: Request) -> str | None:
    """Client IP, honoring X-Forwarded-For only from trusted proxies."""
    if request.client is None:
        return None
    direct = request.client.host
    if direct not in settings.trusted_proxy_ips_list:
        return direct
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return direct
    # First hop in the chain is the original client.
    return forwarded.split(",")[0].strip() or direct


def client_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")
