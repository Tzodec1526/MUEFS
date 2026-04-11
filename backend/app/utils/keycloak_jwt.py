"""Keycloak / OIDC access token validation (RS256 via realm JWKS).

Compliance note: Court systems should validate issuer, signature, and expiry on
every request; demo mode (ALLOW_DEMO_MODE) must never be enabled in production.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from jose import JWTError, jwk, jwt

from app.config import settings

_jwks_cache: tuple[float, dict[str, Any]] | None = None
_JWKS_TTL_SEC = 300.0


async def _fetch_jwks() -> dict[str, Any]:
    global _jwks_cache
    now = time.time()
    if _jwks_cache is not None and now - _jwks_cache[0] < _JWKS_TTL_SEC:
        return _jwks_cache[1]

    base = settings.keycloak_url.rstrip("/")
    url = f"{base}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
    _jwks_cache = (now, data)
    return data


async def decode_keycloak_access_token(token: str) -> dict[str, Any]:
    """Validate signature, exp, and iss; return claims (includes 'sub')."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise JWTError(f"Invalid token header: {exc}") from exc

    kid = header.get("kid")
    if not kid:
        raise JWTError("Token missing kid")

    jwks = await _fetch_jwks()
    key_dict = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key_dict:
        raise JWTError(f"No JWKS key for kid={kid}")

    rsa_key = jwk.construct(key_dict)

    issuer = f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"
    claims = jwt.decode(
        token,
        rsa_key,
        algorithms=["RS256"],
        issuer=issuer,
        options={
            "verify_aud": False,
            "require_exp": True,
        },
    )

    if not claims.get("sub"):
        raise JWTError("Token missing sub")

    # Realm operators may add optional azp/aud checks via Keycloak mappers;
    # browser flows often use a public frontend client while this API uses a
    # separate confidential client id, so we do not require azp == KEYCLOAK_CLIENT_ID.

    return claims
