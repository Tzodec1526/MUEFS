import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event, make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app import database
from app.config import settings
from app.demo.schema import prepare_demo_schema
from app.main import app
from tests.test_filing_concurrency import POSTGRES_URL
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions


@pytest_asyncio.fixture
async def current_database(tmp_path, monkeypatch):
    path = tmp_path / "readiness.db"
    setup = create_engine(f"sqlite:///{path}")
    prepare_demo_schema(setup)
    setup.dispose()
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}", pool_size=1, max_overflow=0, pool_timeout=30,
    )
    monkeypatch.setattr(database, "engine", engine)
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_unmigrated_database_is_not_ready_but_process_is_live(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(database, "engine", engine)
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            live = await client.get("/health")
            ready = await client.get("/ready")
        assert live.status_code == 200
        assert ready.status_code == 503
        assert ready.json() == {
            "status": "not_ready", "service": "muefs-api", "reason": "schema_mismatch",
        }
        assert ready.headers["cache-control"] == "no-store"
    finally:
        await engine.dispose()


async def test_current_schema_is_ready_without_writes(current_database):
    async with current_database.connect() as connection:
        await connection.execute(text("PRAGMA query_only=ON"))
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        for _ in range(2):
            response = await client.get("/ready")
            assert response.status_code == 200, response.text
            assert response.json() == {"status": "ready", "service": "muefs-api"}
            assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("revision", ["d84a19f2c6b0", "unknown-build"])
async def test_an_incompatible_revision_is_not_changed_by_a_probe(current_database, revision):
    async with current_database.begin() as connection:
        await connection.execute(text("UPDATE alembic_version SET version_num=:revision"),
                                 {"revision": revision})
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["reason"] == "schema_mismatch"
    assert response.headers["retry-after"] == "5"
    async with current_database.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == revision


@pytest.mark.parametrize("dialect", ["sqlite", "postgres"])
async def test_connection_failure_is_sanitized_and_does_not_affect_liveness(
    monkeypatch, tmp_path, caplog, dialect,
):
    secret = "private-connection-detail"
    if dialect == "sqlite":
        url = f"sqlite+aiosqlite:///{tmp_path / secret / 'absent.db'}"
    else:
        url = f"postgresql+asyncpg://probe:{secret}@db.internal:5432/absent"
    engine = create_async_engine(url)

    @event.listens_for(engine.sync_engine, "do_connect")
    def refuse(driver_dialect, _record, _args, _params):
        raise driver_dialect.loaded_dbapi.OperationalError(f"could not connect to {url}")

    monkeypatch.setattr(database, "engine", engine)
    caplog.set_level(logging.DEBUG, logger="app.readiness")
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            response = await asyncio.wait_for(client.get("/ready"), timeout=5)
            assert response.status_code == 503
            assert response.json()["reason"] == "database_unavailable"
            assert (await client.get("/health")).status_code == 200
        logged = [record.getMessage() for record in caplog.records
                  if record.name == "app.readiness"]
        assert len(logged) == 1 and "OperationalError" in logged[0]
        assert secret not in response.text
        assert secret not in caplog.text
    finally:
        await engine.dispose()


async def test_pool_wait_is_bounded_and_recovers(current_database):
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        async with current_database.connect():
            check = asyncio.create_task(client.get("/ready"))
            assert (await asyncio.wait_for(client.get("/health"), timeout=1)).status_code == 200
            response = await asyncio.wait_for(check, timeout=5)
            assert response.status_code == 503
            assert response.json()["reason"] == "database_timeout"
        assert (await client.get("/ready")).status_code == 200


@pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")
@pytest.mark.parametrize("postgres_sessions", [True], indirect=True)
async def test_postgres_probe_times_out_on_a_schema_lock_and_recovers(
    postgres_sessions, monkeypatch,
):
    engine = postgres_sessions.kw["bind"]
    monkeypatch.setattr(database, "engine", engine)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        assert (await client.get("/ready")).status_code == 200
        async with engine.begin() as blocker:
            await blocker.execute(text("LOCK TABLE alembic_version IN ACCESS EXCLUSIVE MODE"))
            check = asyncio.create_task(client.get("/ready"))
            assert (await asyncio.wait_for(client.get("/health"), timeout=1)).status_code == 200
            response = await asyncio.wait_for(check, timeout=5)
            assert response.status_code == 503
            assert response.json()["reason"] == "database_timeout"
        assert (await client.get("/ready")).status_code == 200


@pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")
@pytest.mark.parametrize("postgres_sessions", ["d84a19f2c6b0"], indirect=True)
async def test_postgres_readiness_follows_each_committed_schema_revision(
    postgres_sessions, monkeypatch,
):
    from alembic.config import Config

    from alembic import command

    engine = postgres_sessions.kw["bind"]
    monkeypatch.setattr(database, "engine", engine)

    def migrate(connection):
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.set_main_option(
            "script_location", str(Path(__file__).resolve().parents[1] / "alembic"),
        )
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:

        async def probe():
            response = await client.get("/ready")
            return response.status_code, response.json().get("reason")

        assert await probe() == (503, "schema_mismatch")
        async with engine.connect() as connection:
            await connection.run_sync(migrate)
            head = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert await probe() == (200, None)
        async with engine.begin() as connection:
            await connection.execute(text(
                "UPDATE alembic_version SET version_num = 'd84a19f2c6b0'",
            ))
        assert await probe() == (503, "schema_mismatch")
        async with engine.begin() as connection:
            await connection.execute(text("UPDATE alembic_version SET version_num = :head"),
                                     {"head": head})
        assert await probe() == (200, None)


def test_migrations_accept_a_url_encoded_database_address(tmp_path, monkeypatch):
    address = f"sqlite:///{(tmp_path / 'p%40ss.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", address)
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "alembic"),
    )
    command.current(config)
    assert Path(make_url(address).database).exists()


def test_hosted_demo_probes_do_not_allocate_sessions_or_recreate_missing_storage(tmp_path):
    code = r'''
import asyncio
from pathlib import Path
import os
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, create_engine
from app.demo.schema import prepare_demo_schema

directory = Path(os.environ["DEMO_DATA_DIR"])
directory.mkdir()
template = directory / "template.db"
setup = create_engine(URL.create("sqlite", database=str(template)))
prepare_demo_schema(setup)
setup.dispose()
from app.demo import session_db
from app.demo.server import app

async def exercise():
    async with app.router.lifespan_context(app):
        original_files = set(directory.rglob("*.db"))
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            for path in ["/health", "/ready"] * 3:
                result = await client.get(path)
                assert result.status_code == 200, (path, result.text)
                assert "set-cookie" not in result.headers
            assert not session_db._last_access
            assert set(directory.rglob("*.db")) == original_files
            probe = await client.get("/api/v1/courts")
            assert probe.status_code == 401, probe.text
            assert "set-cookie" not in probe.headers
            assert set(directory.rglob("*.db")) == original_files
            assert "set-cookie" in (await client.get("/")).headers
            visitor = await client.get("/api/v1/courts")
            assert visitor.status_code == 200, visitor.text
            assert "set-cookie" in visitor.headers
            assert len(session_db._last_access) == 1
            assert len(set(directory.rglob("*.db")) - original_files) == 1
            await app.state.readiness_engine.dispose()
            template.unlink()
            assert (await client.get("/ready")).status_code == 503
            assert not template.exists()
            assert (await client.get("/health")).status_code == 200
asyncio.run(exercise())
print("Hosted demo probe lifecycle verified")
'''
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "DEMO_DATA_DIR": str(tmp_path / "hosted demo #data"),
             "DATABASE_URL": "sqlite+aiosqlite:///:memory:", "DEMO_ISOLATED_SESSIONS": "true",
             "DEBUG": "true", "ALLOW_DEMO_MODE": "true", "RATE_LIMIT_ENABLED": "false",
             "EMAIL_DELIVERY_ENABLED": "false", "SERVICE_DELIVERY_ENABLED": "false"},
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Hosted demo probe lifecycle verified" in result.stdout
