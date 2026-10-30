import time
from collections import defaultdict
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.config import settings
from app.main import app
from app.middleware import rate_limit
from app.utils import keycloak_jwt
from app.utils.http_context import client_ip


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_oversized_upload_is_refused_before_it_is_read(client, monkeypatch):
    monkeypatch.setattr(settings, "max_file_size_mb", 1)
    url = "/api/v1/filings/1/documents"
    fields = {"title": "Record", "document_type_code": "COMPLAINT"}
    oversized = await client.post(
        url, data=fields, files={"file": ("big.pdf", b"x" * 3 * 1024 * 1024, "application/pdf")},
    )
    assert oversized.status_code == 413, oversized.text
    small = await client.post(url, data=fields, files={"file": ("a.pdf", b"x", "application/pdf")})
    assert small.status_code == 401


async def test_streamed_body_without_a_length_is_cut_off(client):
    async def chunks():
        for _ in range(3):
            yield b" " * (512 * 1024)

    response = await client.post(
        "/api/v1/auth/register", content=chunks(), headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413, response.text


@pytest.mark.parametrize("forwarded, expected", [
    ("6.6.6.6, 203.0.113.9", "203.0.113.9"),
    ("203.0.113.9, 10.0.0.2", "203.0.113.9"),
    ("", "10.0.0.1"),
])
def test_client_ip_is_the_last_untrusted_forwarded_hop(monkeypatch, forwarded, expected):
    monkeypatch.setattr(settings, "trusted_proxy_ips", "10.0.0.1,10.0.0.2")
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    request = Request({"type": "http", "client": ("10.0.0.1", 443), "headers": headers})
    assert client_ip(request) == expected


def test_forwarding_headers_from_untrusted_peers_are_ignored(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_ips", "10.0.0.1")
    request = Request({
        "type": "http", "client": ("198.51.100.7", 443),
        "headers": [(b"x-forwarded-for", b"6.6.6.6")],
    })
    assert client_ip(request) == "198.51.100.7"


def test_trusted_proxies_may_be_listed_as_networks(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_ips", "10.0.0.0/8, fd00::/8")
    for peer, forwarded in (("10.41.7.3", b"6.6.6.6, 203.0.113.9, 10.9.8.7"),
                            ("fd12::1", b"203.0.113.9")):
        request = Request({
            "type": "http", "client": (peer, 443),
            "headers": [(b"x-forwarded-for", forwarded)],
        })
        assert client_ip(request) == "203.0.113.9"


def test_settings_reject_proxy_entries_that_are_not_addresses_or_networks():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError, match="proxy.example"):
        Settings(trusted_proxy_ips="10.0.0.1, proxy.example")


def test_empty_settings_in_the_environment_file_mean_not_set(monkeypatch, tmp_path):
    from app.config import Settings

    env = tmp_path / ".env"
    blank = ["ENABLE_API_DOCS", "STRICT_MIME_DETECTION", "JWT_VERIFY_AUDIENCE",
             "RATE_LIMIT_FAIL_CLOSED", "MAX_FILE_SIZE_MB"]
    env.write_text("".join(f"{name}=" + chr(10) for name in blank))
    loaded = Settings(_env_file=env)
    assert loaded.enable_api_docs is None
    assert loaded.strict_mime_detection is None
    assert loaded.jwt_verify_audience is None
    assert loaded.rate_limit_fail_closed is None
    assert loaded.max_file_size_mb == 100


async def test_rate_limited_responses_stay_readable_and_preflights_are_free(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_backend", "memory")
    monkeypatch.setattr(settings, "rate_limit_default_per_minute", 1)
    monkeypatch.setattr(rate_limit, "_mem_store", defaultdict(list))
    origin = settings.allowed_origins_list[0]
    preflight = await client.options("/api/v1/auth/me", headers={
        "Origin": origin, "Access-Control-Request-Method": "GET",
    })
    assert preflight.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers={"Origin": origin})).status_code == 401
    limited = await client.get("/api/v1/auth/me", headers={"Origin": origin})
    assert limited.status_code == 429
    assert limited.headers["access-control-allow-origin"] == origin
    assert limited.headers["x-content-type-options"] == "nosniff"


def test_a_full_memory_limiter_store_drops_stale_clients_before_the_next_interval(monkeypatch):
    now = time.time()
    stale = {f"default:{n}": [now - 120] for n in range(rate_limit._MEM_MAX_KEYS + 1)}
    monkeypatch.setattr(rate_limit, "_mem_store", defaultdict(list, stale))
    monkeypatch.setattr(rate_limit, "_mem_last_cleanup", now)
    assert rate_limit._memory_check_allow("visitor", "default")
    assert list(rate_limit._mem_store) == ["default:visitor"]


@pytest.mark.parametrize("path", ["/api/v1/auth/me", "/api/v1/cases/1"])
async def test_identity_provider_outage_is_reported_as_unavailable(client, monkeypatch, path):
    async def unavailable(*, refresh=False):
        raise keycloak_jwt.IdentityProviderUnavailableError("realm keys unavailable")

    monkeypatch.setattr(keycloak_jwt, "_fetch_jwks", unavailable)
    token = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0.e30.c2ln"
    response = await client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503, response.text
    assert response.headers["retry-after"] == "30"


TOO_LARGE = str(2**63)


@pytest.mark.parametrize("url, headers", [
    (f"/api/v1/cases/{TOO_LARGE}", {}),
    (f"/api/v1/cases/{TOO_LARGE}/filings", {}),
    (f"/api/v1/cases/search?court_id={TOO_LARGE}", {}),
    (f"/api/v1/courts?page={TOO_LARGE}", {}),
    ("/api/v1/auth/me", {"X-Demo-User-Id": TOO_LARGE}),
])
async def test_ids_no_record_can_have_are_refused_before_the_database(client, url, headers):
    response = await client.get(url, headers=headers)
    assert response.status_code == 422, response.text


class _DriverError(Exception):
    def __init__(self, sqlstate):
        super().__init__(f"SQLSTATE {sqlstate}")
        self.sqlstate = sqlstate


@pytest.mark.parametrize("sqlstate, expected", [
    ("22021", 422),
    ("22003", 422),
    ("40P01", 500),
])
async def test_database_rejections_of_input_are_client_errors(monkeypatch, sqlstate, expected):
    from sqlalchemy.exc import DBAPIError

    from app.services import search_service

    async def rejected(*args, **kwargs):
        raise DBAPIError("SELECT ...", {}, _DriverError(sqlstate))

    monkeypatch.setattr(search_service, "search_cases", rejected)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/cases/search", params={"party_name": "Doe"})
    assert response.status_code == expected, response.text


async def test_dates_at_the_edge_of_the_calendar_are_rejected_not_crashed(monkeypatch):
    from app.api import court_calendars
    from app.database import get_db

    class Courts:
        async def get(self, model, key):
            return object()

    async def database():
        yield Courts()

    async def overflowing(db, court_id, received_at):
        return received_at + timedelta(days=367)

    monkeypatch.setitem(app.dependency_overrides, get_db, database)
    monkeypatch.setattr(court_calendars, "filing_date_for_receipt", overflowing)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/courts/1/filing-date", params={"received_at": "9999-12-31T00:00:00Z"},
        )
    assert response.status_code == 422, response.text
