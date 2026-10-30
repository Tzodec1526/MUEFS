from __future__ import annotations

import json
import time
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import InvalidKeyError
from jwt.exceptions import InvalidTokenError as JWTError

from app.config import settings

_jwks_cache: tuple[float, dict[str, Any]] | None = None
_JWKS_TTL_SEC = 300.0
_JWKS_REFRESH_SEC = 30.0

__all__ = ["IdentityProviderUnavailableError", "JWTError", "decode_keycloak_access_token"]


class IdentityProviderUnavailableError(Exception):
    pass


async def _fetch_jwks(*, refresh: bool = False) -> dict[str, Any]:
    global _jwks_cache
    now = time.time()
    if _jwks_cache is not None:
        age = now - _jwks_cache[0]
        if age < _JWKS_TTL_SEC and not (refresh and age >= _JWKS_REFRESH_SEC):
            return _jwks_cache[1]

    base = (settings.keycloak_internal_url or settings.keycloak_url).rstrip("/")
    url = f"{base}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise IdentityProviderUnavailableError("Could not retrieve the realm signing keys") from exc
    _jwks_cache = (now, data)
    return data


def _signing_key(jwks: dict[str, Any], kid: str) -> dict[str, Any] | None:
    return next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)


async def decode_keycloak_access_token(token: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise JWTError(f"Invalid token header: {exc}") from exc

    kid = header.get("kid")
    if not kid:
        raise JWTError("Token missing kid")

    key_dict = _signing_key(await _fetch_jwks(), kid)
    if key_dict is None:
        key_dict = _signing_key(await _fetch_jwks(refresh=True), kid)
    if key_dict is None:
        raise JWTError(f"No JWKS key for kid={kid}")

    try:
        rsa_key = RSAAlgorithm.from_jwk(json.dumps(key_dict))
    except InvalidKeyError as exc:
        raise JWTError("Token signing key is not an RSA key") from exc
    public_key = rsa_key.public_key() if isinstance(rsa_key, RSAPrivateKey) else rsa_key

    issuer = f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"
    decode_kwargs: dict[str, Any] = {
        "algorithms": ["RS256"],
        "issuer": issuer,
        "options": {
            "verify_aud": settings.jwt_audience_verify_enabled,
            "require": ["exp"],
        },
    }
    if settings.jwt_audience_verify_enabled:
        decode_kwargs["audience"] = settings.jwt_audiences_list

    try:
        claims = jwt.decode(token, public_key, **decode_kwargs)
    except JWTError as exc:
        raise JWTError(str(exc)) from exc

    if not claims.get("sub"):
        raise JWTError("Token missing sub")

    return claims
