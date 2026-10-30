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
    # Import the hosted entry point only in this subprocess: it extends the global app.
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
        # Pages that never open a sandbox must not accumulate per-visitor state.
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
