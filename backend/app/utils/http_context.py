"""HTTP request metadata for audit and security logging."""

from fastapi import Request


def client_ip(request: Request) -> str | None:
    # Trusted proxy / X-Forwarded-For should be configured at the edge in production.
    return request.client.host if request.client else None


def client_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")
