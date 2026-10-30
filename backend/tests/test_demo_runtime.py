import os
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


@pytest.mark.parametrize("allow_demo, isolated", [(True, True), (True, False), (False, True)])
async def test_browser_configuration_is_available_in_the_local_entry_point(
    monkeypatch, allow_demo, isolated,
):
    monkeypatch.setattr(settings, "allow_demo_mode", allow_demo)
    monkeypatch.setattr(settings, "demo_isolated_sessions", isolated)
    monkeypatch.setattr(settings, "demo_mode_secret", "browser-demo-secret")
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        config = await client.get("/config.js")
    assert config.status_code == 200, config.text
    assert config.headers["cache-control"] == "no-store"
    assert config.headers["content-type"].startswith("application/javascript")
    expected = '"browser-demo-secret"' if allow_demo and isolated else '""'
    assert config.text == f"window.__MUEFS_DEMO_SECRET__={expected};"


def test_hosted_asset_responses(tmp_path):
    code = r'''
import asyncio
import mimetypes
import os
from pathlib import Path
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, create_engine
from app.demo.schema import prepare_demo_schema

async def exercise():
    directory = Path(os.environ["DEMO_DATA_DIR"])
    directory.mkdir()
    setup = create_engine(URL.create("sqlite", database=str(directory / "template.db")))
    prepare_demo_schema(setup)
    setup.dispose()
    static = Path(os.environ["DEMO_STATIC_DIR"])
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>Current demo</html>")
    (static / "assets" / "app-12345678.js").write_text("console.log('current bundle')")
    (static / "assets" / "public-sans-12345678.woff2").write_bytes(b"wOF2")
    mimetypes.init()
    mimetypes.types_map.pop(".woff2", None)
    from app.demo.server import app as hosted
    from app.demo import session_db

    async with AsyncClient(transport=ASGITransport(hosted), base_url="http://test") as client:
        for path in ["/config.js", "/assets/app-12345678.js", "/assets/old-deploy.js"]:
            response = await client.get(path)
            assert "set-cookie" not in response.headers, (path, response.headers)
        assert not session_db._last_access, session_db._last_access
        for path in ["/", "/index.html", "/filings/new", "/cases/example"]:
            response = await client.get(path)
            assert response.status_code == 200, (path, response.text)
            assert response.headers["cache-control"] == "no-store", path
            assert "Current demo" in response.text
        assert not session_db._last_access, session_db._last_access
        bundle = await client.get("/assets/app-12345678.js")
        assert bundle.status_code == 200
        assert bundle.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert "javascript" in bundle.headers["content-type"]
        font = await client.get("/assets/public-sans-12345678.woff2")
        assert font.status_code == 200
        assert font.headers["content-type"] == "font/woff2"
        assert font.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert "set-cookie" not in font.headers
        for path in ["/assets/old-deploy.js", "/api/v1/no-such-route"]:
            missing = await client.get(path)
            assert missing.status_code == 404, (path, missing.text)
            assert "Current demo" not in missing.text

asyncio.run(exercise())
'''
    _run_hosted(code, tmp_path)


def test_hosted_assets_are_compressed_only_for_clients_that_accept_gzip(tmp_path):
    code = r'''
import asyncio
import gzip
import os
from pathlib import Path
from uuid import uuid4
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session
from app.demo.schema import prepare_demo_schema
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.user import User, UserType

ACCEPTED = ["gzip", "gzip, deflate, br", "br, GZIP;q=0.5", "gzip;q=1.0", "gzip;q=oops"]
REFUSED = ["", "identity", "br", "gzip;q=0", "gzip; q=0.000", "x-gzip-like"]

async def exercise():
    directory = Path(os.environ["DEMO_DATA_DIR"])
    directory.mkdir()
    setup = create_engine(URL.create("sqlite", database=str(directory / "template.db")))
    prepare_demo_schema(setup)
    with Session(setup) as session:
        court = Court(name="Demo Court", county="Wayne", court_type=CourtType.CIRCUIT,
                      is_efiling_enabled=True)
        session.add(court)
        session.flush()
        session.add(CaseType(court_id=court.id, code="C", name="Civil",
                             category=CaseCategory.CIVIL, filing_fee_cents=100))
        session.add(User(email="filer@example.invalid", first_name="Demo", last_name="Filer",
                         user_type=UserType.SELF_REPRESENTED))
        session.commit()
    setup.dispose()
    static = Path(os.environ["DEMO_STATIC_DIR"])
    assets = static / "assets"
    assets.mkdir(parents=True)
    (static / "index.html").write_text("<html>Current demo</html>")
    bundle = b"console.log('current bundle');\n" * 200
    packed = gzip.compress(bundle)
    (assets / "app-12345678.js").write_bytes(bundle)
    (assets / "app-12345678.js.gz").write_bytes(packed)
    (assets / "app-12345678.css").write_bytes(b"body { margin: 0 }\n" * 200)
    (assets / "app-12345678.css.gz").write_bytes(gzip.compress(b"body { margin: 0 }\n" * 200))
    (assets / "public-sans-12345678.woff2").write_bytes(b"wOF2" * 200)
    from app.demo.server import app as hosted

    def assert_not_compressed(response, path):
        assert response.status_code == 200, (path, response.text)
        assert "content-encoding" not in response.headers, (path, response.headers)

    async with AsyncClient(
        transport=ASGITransport(hosted), base_url="http://test",
        headers={"X-Demo-User-Id": "1", "X-Demo-Auth-Secret": "browser-demo-secret"},
    ) as client:
        page = await client.get("/", headers={"Accept-Encoding": "gzip"})
        assert_not_compressed(page, "/")
        policy = page.headers["content-security-policy"]

        identity_tags = set()
        for accept in REFUSED:
            plain = await client.get("/assets/app-12345678.js", headers={"Accept-Encoding": accept})
            assert_not_compressed(plain, accept)
            assert plain.content == bundle
            assert plain.headers["content-length"] == str(len(bundle))
            assert plain.headers["vary"] == "Accept-Encoding"
            assert plain.headers["cache-control"] == "public, max-age=31536000, immutable"
            assert "javascript" in plain.headers["content-type"]
            assert plain.headers["content-security-policy"] == policy
            identity_tags.add(plain.headers["etag"])

        for accept in ACCEPTED:
            sent = await client.get("/assets/app-12345678.js", headers={"Accept-Encoding": accept})
            assert sent.status_code == 200, (accept, sent.text)
            assert sent.headers["content-encoding"] == "gzip", accept
            assert sent.headers["content-length"] == str(len(packed))
            assert sent.content == bundle
            assert sent.headers["vary"] == "Accept-Encoding"
            assert sent.headers["cache-control"] == "public, max-age=31536000, immutable"
            assert "javascript" in sent.headers["content-type"]
            assert sent.headers["content-security-policy"] == policy
            assert sent.headers["etag"] not in identity_tags

        style = await client.get("/assets/app-12345678.css", headers={"Accept-Encoding": "gzip"})
        assert style.headers["content-encoding"] == "gzip"
        assert style.headers["content-type"].startswith("text/css")

        font = await client.get(
            "/assets/public-sans-12345678.woff2", headers={"Accept-Encoding": "gzip"},
        )
        assert_not_compressed(font, "font")
        assert font.content == b"wOF2" * 200
        assert font.headers["content-type"] == "font/woff2"
        assert font.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert "vary" not in font.headers

        for path in ["/assets/old-deploy.js", "/assets/app-12345678.js.gz"]:
            missing = await client.get(path, headers={"Accept-Encoding": "gzip"})
            assert missing.status_code == 404, (path, missing.text)
            assert "content-encoding" not in missing.headers
            assert "Current demo" not in missing.text

        for path in ["/config.js", "/api/v1/courts", "/api/v1/public/stats"]:
            response = await client.get(path, headers={"Accept-Encoding": "gzip"})
            assert_not_compressed(response, path)

        draft = await client.post("/api/v1/filings", json={
            "court_id": 1, "case_type_id": 1, "filing_type": "initial", "case_title": "Upload",
        }, headers={"Idempotency-Key": str(uuid4())})
        assert draft.status_code == 201, draft.text
        document = b"sandbox bytes\n" * 500
        uploaded = await client.post(
            f"/api/v1/filings/{draft.json()['id']}/documents",
            headers={"Idempotency-Key": str(uuid4())},
            data={"title": "Record", "document_type_code": "COMPLAINT"},
            files={"file": ("record.txt", document, "text/plain")},
        )
        assert uploaded.status_code == 200, uploaded.text
        downloaded = await client.get(
            f"/api/v1/documents/{uploaded.json()['id']}/download",
            headers={"Accept-Encoding": "gzip"},
        )
        assert_not_compressed(downloaded, "download")
        assert downloaded.content == document

asyncio.run(exercise())
'''
    _run_hosted(code, tmp_path)


def _run_hosted(code, tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "DEMO_DATA_DIR": str(tmp_path / "data"),
             "DEMO_STATIC_DIR": str(tmp_path / "static"),
             "DATABASE_URL": "sqlite+aiosqlite:///:memory:", "DEMO_ISOLATED_SESSIONS": "true",
             "DEBUG": "true", "ALLOW_DEMO_MODE": "true", "RATE_LIMIT_ENABLED": "false",
             "DEMO_MODE_SECRET": "browser-demo-secret"},
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
