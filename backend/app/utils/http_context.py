"""HTTP request metadata for audit and security logging."""

from functools import cache
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

from fastapi import Request

from app.config import settings


@cache
def _networks(raw: str) -> tuple[IPv4Network | IPv6Network, ...]:
    return tuple(
        ip_network(entry, strict=False)
        for entry in (part.strip() for part in raw.split(","))
        if entry
    )


def _is_trusted_proxy(address: str) -> bool:
    try:
        ip = ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in _networks(settings.trusted_proxy_ips))


def client_ip(request: Request) -> str | None:
    """Client IP, honoring X-Forwarded-For only from trusted proxies."""
    if request.client is None:
        return None
    address = request.client.host
    if not _is_trusted_proxy(address):
        return address
    # Each proxy appends the peer it received from, so entries left of the last
    # untrusted hop were supplied by the client and cannot identify it.
    hops = ",".join(request.headers.getlist("x-forwarded-for")).split(",")
    for hop in reversed([hop.strip() for hop in hops if hop.strip()]):
        if not _is_trusted_proxy(hop):
            return hop
        address = hop
    return address


def client_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")
