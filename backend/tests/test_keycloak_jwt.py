"""Access-token validation against a realm key set, without stubbing the decoder."""

import base64
import hashlib
import hmac
import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from app.config import settings
from app.utils import keycloak_jwt
from app.utils.keycloak_jwt import (
    IdentityProviderUnavailableError,
    JWTError,
    decode_keycloak_access_token,
)

ISSUER = "https://identity.example.gov/realms/muefs"
ORIGINAL_FETCH = keycloak_jwt._fetch_jwks
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(public_key, kid):
    algorithm = RSAAlgorithm if isinstance(public_key, rsa.RSAPublicKey) else ECAlgorithm
    return {**json.loads(algorithm.to_jwk(public_key)), "kid": kid}


@pytest.fixture
def realm(monkeypatch):
    monkeypatch.setattr(settings, "keycloak_url", "https://identity.example.gov")
    monkeypatch.setattr(settings, "keycloak_realm", "muefs")
    monkeypatch.setattr(settings, "keycloak_client_id", "muefs-api")
    monkeypatch.setattr(settings, "jwt_audiences", "")
    monkeypatch.setattr(settings, "jwt_verify_audience", True)
    key_sets = [{"keys": [_jwk(PRIVATE_KEY.public_key(), "k1")]}]
    fetches = []

    async def fetch(*, refresh=False):
        fetches.append(refresh)
        return key_sets[-1]

    monkeypatch.setattr(keycloak_jwt, "_fetch_jwks", fetch)
    return key_sets, fetches


def _claims(**changes):
    claims = {"sub": "subject-1", "iss": ISSUER, "aud": "muefs-api", "exp": time.time() + 300}
    claims.update(changes)
    return {key: value for key, value in claims.items() if value is not None}


def _token(claims=None, key=PRIVATE_KEY, kid="k1"):
    return jwt.encode(claims or _claims(), key, algorithm="RS256", headers={"kid": kid})


def _unsigned(header, claims):
    def part(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    return f"{part(header)}.{part(claims)}"


async def test_a_realm_signed_token_for_this_api_is_accepted(realm):
    assert (await decode_keycloak_access_token(_token()))["sub"] == "subject-1"


@pytest.mark.parametrize("changes, reason", [
    ({"aud": "account"}, "Audience"),  # Keycloak's generic audience is not this API.
    ({"aud": "another-app"}, "Audience"),
    ({"iss": "https://identity.example.gov/realms/other"}, "issuer"),
    ({"exp": -60}, "expired"),
    ({"exp": None}, '"exp"'),
    ({"sub": None}, "sub"),
], ids=["account-audience", "other-audience", "issuer", "expired", "no-expiry", "no-subject"])
async def test_tokens_outside_this_realm_and_api_are_rejected(realm, changes, reason):
    # Build the claims now: an expiry fixed at collection time could lapse before this runs
    # and turn every case into an "expired" rejection.
    if changes.get("exp") is not None:
        changes = {**changes, "exp": time.time() + changes["exp"]}
    with pytest.raises(JWTError, match=reason):
        await decode_keycloak_access_token(_token(_claims(**changes)))


async def test_listed_extra_audiences_are_accepted(realm, monkeypatch):
    monkeypatch.setattr(settings, "jwt_audiences", "account")
    assert await decode_keycloak_access_token(_token(_claims(aud="account")))


async def test_tokens_not_signed_by_the_realm_key_are_rejected(realm):
    with pytest.raises(JWTError):
        await decode_keycloak_access_token(_token(key=OTHER_KEY))
    public_pem = PRIVATE_KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    # Algorithm confusion: an HMAC signature keyed with the published public key.
    signing_input = _unsigned({"alg": "HS256", "kid": "k1", "typ": "JWT"}, _claims())
    signature = base64.urlsafe_b64encode(
        hmac.new(public_pem, signing_input.encode(), hashlib.sha256).digest(),
    ).rstrip(b"=").decode()
    for token in (
        f"{signing_input}.{signature}",
        _unsigned({"alg": "none", "kid": "k1"}, _claims()) + ".",
    ):
        with pytest.raises(JWTError):
            await decode_keycloak_access_token(token)


async def test_rotated_keys_are_refetched_once_before_rejecting(realm, monkeypatch):
    # Use the real key cache, with the realm's key endpoint stubbed.
    monkeypatch.setattr(keycloak_jwt, "_fetch_jwks", ORIGINAL_FETCH)
    rotated = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    published = {"keys": [_jwk(rotated.public_key(), "k2")]}
    requests = []

    async def serve(self, url, **kwargs):
        requests.append(url)
        return httpx.Response(200, json=published, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", serve)
    # The cached set predates the rotation and is past the refresh interval.
    old = {"keys": [_jwk(PRIVATE_KEY.public_key(), "k1")]}
    monkeypatch.setattr(keycloak_jwt, "_jwks_cache", (time.time() - 60, old))
    assert await decode_keycloak_access_token(_token(key=rotated, kid="k2"))
    assert len(requests) == 1
    # A kid that exists nowhere is rejected without another fetch: refreshes are bounded.
    with pytest.raises(JWTError, match="No JWKS key"):
        await decode_keycloak_access_token(_token(kid="unknown"))
    assert len(requests) == 1


async def test_a_non_rsa_realm_key_rejects_the_token_instead_of_failing(realm):
    key_sets, _ = realm
    elliptic = ec.generate_private_key(ec.SECP256R1()).public_key()
    key_sets.append({"keys": [_jwk(elliptic, "k1")]})
    with pytest.raises(JWTError, match="not an RSA key"):
        await decode_keycloak_access_token(_token())


async def test_unreachable_key_set_reports_the_provider_unavailable(monkeypatch):
    monkeypatch.setattr(keycloak_jwt, "_jwks_cache", None)

    async def refused(self, url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "get", refused)
    with pytest.raises(IdentityProviderUnavailableError):
        await keycloak_jwt._fetch_jwks()


async def test_keys_may_come_from_an_internal_address_but_the_issuer_stays_public(
    realm, monkeypatch,
):
    monkeypatch.setattr(keycloak_jwt, "_fetch_jwks", ORIGINAL_FETCH)
    monkeypatch.setattr(keycloak_jwt, "_jwks_cache", None)
    monkeypatch.setattr(settings, "keycloak_internal_url", "http://keycloak:8080")
    requested = []

    async def serve(self, url, **kwargs):
        requested.append(url)
        keys = {"keys": [_jwk(PRIVATE_KEY.public_key(), "k1")]}
        return httpx.Response(200, json=keys, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", serve)
    assert (await decode_keycloak_access_token(_token()))["sub"] == "subject-1"
    assert requested == ["http://keycloak:8080/realms/muefs/protocol/openid-connect/certs"]
    internal_issuer = _token(_claims(iss="http://keycloak:8080/realms/muefs"))
    with pytest.raises(JWTError):
        await decode_keycloak_access_token(internal_issuer)
