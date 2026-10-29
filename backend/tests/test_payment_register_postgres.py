"""Exercise the register's real PostgreSQL snapshots, totals and authority locks."""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.main import app
from app.models.filing import FilingEnvelope
from app.models.user import CourtRole, User, UserCourtRole
from tests.test_external_payment_concurrency import payment_client as payment_client
from tests.test_filing_concurrency import POSTGRES_URL, prepare_filing
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions
from tests.test_payment_register import PERIOD, activity

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest.mark.parametrize("postgres_sessions", [False, True], indirect=True)
async def test_postgres_totals_and_pages_include_a_reversal_committed_between_reads(
    postgres_sessions, payment_client,
):
    fid, _, clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        court_id = (await db.get(FilingEnvelope, fid)).court_id
        db.add(UserCourtRole(user_id=clerk, court_id=court_id, role=CourtRole.ADMIN))
        db.add_all(activity(fid, clerk, amount=100_000_000) for _ in range(52))
    params = {"court_id": court_id, **PERIOD}
    headers = {"X-Test-User": str(clerk)}
    response = await payment_client.get("/api/v1/clerk/payment-register",
                                        params=params, headers=headers)
    assert response.status_code == 200, response.text
    before = response.json()
    assert before["total"] == 52 and len(before["entries"]) == 50
    assert before["totals"] == {"credits_cents": 5_200_000_000, "reversals_cents": 0}
    assert all(row["amount_cents"] == 100_000_000 for row in before["entries"])
    # Each read is a fresh snapshot: the next page counts a reversal committed in between.
    async with postgres_sessions.begin() as writer:
        writer.add(activity(fid, clerk, amount=-500))
    response = await payment_client.get("/api/v1/clerk/payment-register",
                                        params={**params, "page": 2}, headers=headers)
    assert response.status_code == 200, response.text
    after = response.json()
    assert after["total"] == 53 and len(after["entries"]) == 3
    assert after["totals"] == {"credits_cents": 5_200_000_000, "reversals_cents": 500}
    empty_page = (await payment_client.get("/api/v1/clerk/payment-register",
                                           params={**params, "page": 3}, headers=headers)).json()
    assert empty_page["entries"] == [] and empty_page["totals"] == after["totals"]


async def test_register_waits_for_authority_change_and_then_rejects_revoked_admin(
    postgres_sessions, payment_client, monkeypatch,
):
    fid, _, clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        court_id = (await db.get(FilingEnvelope, fid)).court_id
        db.add(UserCourtRole(user_id=clerk, court_id=court_id, role=CourtRole.ADMIN))
        db.add(activity(fid, clerk))
    requested = asyncio.Event()
    request_pid = None

    async def database():
        nonlocal request_pid
        async with postgres_sessions.begin() as db:
            request_pid = await db.scalar(text("SELECT pg_backend_pid()"))
            requested.set()
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, database)
    pending = None
    try:
        async with postgres_sessions.begin() as revoker:
            await revoker.scalar(select(User).where(User.id == clerk).with_for_update())
            pending = asyncio.create_task(payment_client.get("/api/v1/clerk/payment-register",
                params={"court_id": court_id, **PERIOD, "format": "csv"},
                headers={"X-Test-User": str(clerk)}))
            await asyncio.wait_for(requested.wait(), 5)
            async with asyncio.timeout(5), postgres_sessions() as observer:
                while not await observer.scalar(text(
                    "SELECT cardinality(pg_blocking_pids(:pid))",
                ), {"pid": request_pid}):
                    await asyncio.sleep(0.01)
            assert not pending.done()
            await revoker.execute(delete(UserCourtRole).where(
                UserCourtRole.user_id == clerk, UserCourtRole.court_id == court_id,
                UserCourtRole.role == CourtRole.ADMIN,
            ))
        response = await asyncio.wait_for(pending, 5)
        assert response.status_code == 403, response.text
        assert "SYN-REGISTER" not in response.text
    finally:
        if pending and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.parametrize("postgres_sessions", ["b28e53cad9f4"], indirect=True)
async def test_register_index_migration_recovers_failed_build_and_preserves_events(
    postgres_sessions,
):
    from alembic.config import Config

    from alembic import command

    fid, _, clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        db.add_all([activity(fid, clerk), activity(fid, clerk)])
    engine = postgres_sessions.kw["bind"]
    async with engine.connect() as connection:
        connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        with pytest.raises(IntegrityError):
            await connection.execute(text("""CREATE UNIQUE INDEX CONCURRENTLY
                ix_filing_payment_activity ON filing_transactions (occurred_at)"""))
        assert await connection.scalar(text("""SELECT indisvalid FROM pg_index
            WHERE indexrelid = 'ix_filing_payment_activity'::regclass""")) is False

    def migrate(connection, operation, revision):
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.set_main_option("script_location",
                               str(Path(__file__).resolve().parents[1] / "alembic"))
        config.attributes["connection"] = connection
        getattr(command, operation)(config, revision)

    async with engine.connect() as connection:
        for operation, revision in (("upgrade", "head"), ("downgrade", "b28e53cad9f4"),
                                    ("upgrade", "head")):
            await connection.run_sync(migrate, operation, revision)
        assert await connection.scalar(text("""SELECT indisvalid FROM pg_index
            WHERE indexrelid = 'ix_filing_payment_activity'::regclass""")) is True
        definition = await connection.scalar(text(
            "SELECT pg_get_indexdef('ix_filing_payment_activity'::regclass)",
        ))
        assert "(occurred_at, filing_id, id)" in definition
        assert "fee_payment_recorded" in definition and "fee_payment_reversed" in definition
        assert await connection.scalar(text("SELECT count(*) FROM filing_transactions")) == 2
