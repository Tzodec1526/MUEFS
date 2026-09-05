"""Run with MUEFS_TEST_POSTGRES_URL against a disposable PostgreSQL database.

Each test uses a uniquely named schema and drops only that schema on completion.
"""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.case import Case
from app.models.filing import FilingDocument, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.notification import Notification
from app.services import filing_service
from tests.test_filing_history import filing_fixture

POSTGRES_URL = os.getenv("MUEFS_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest_asyncio.fixture
async def postgres_sessions(request):
    schema = f"filing_test_{uuid4().hex}"
    admin = create_async_engine(POSTGRES_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        POSTGRES_URL, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with engine.begin() as conn:
            if getattr(request, "param", False):
                from alembic.config import Config

                from alembic import command

                def migrate(connection):
                    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
                    config.set_main_option(
                        "script_location", str(Path(__file__).resolve().parents[1] / "alembic"),
                    )
                    config.attributes["connection"] = connection
                    command.upgrade(config, "head")

                await conn.run_sync(migrate)
            else:
                await conn.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def prepare_filing(factory):
    async with factory.begin() as db:
        fid, filer, clerk, _other = await filing_fixture(db)
        db.add(
            FilingDocument(
                envelope_id=fid,
                title="Complaint",
                document_type_code="COMPLAINT",
                file_key="test.txt",
                mime_type="text/plain",
                file_size_bytes=1,
                sha256_hash="a" * 64,
            )
        )
    return fid, filer, clerk


async def test_concurrent_review_refreshes_previously_read_status(postgres_sessions):
    fid, _filer, clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        await filing_service.submit_filing(db, fid)
    ready = asyncio.Queue()
    start = asyncio.Event()

    async def review():
        async with postgres_sessions.begin() as db:
            # Both requests have the old status in their identity map before either
            # gets the row lock. The second must refresh it after the first commits.
            before = await filing_service.get_filing(db, fid)
            assert before.status == FilingStatus.SUBMITTED
            await ready.put(True)
            await start.wait()
            result = await filing_service.review_filing(db, fid, clerk, "accept")
            return result is not None

    tasks = [asyncio.create_task(review()) for _ in range(2)]
    await asyncio.wait_for(ready.get(), 10)
    await asyncio.wait_for(ready.get(), 10)
    start.set()
    assert sorted(await asyncio.wait_for(asyncio.gather(*tasks), 15)) == [False, True]
    async with postgres_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Case)) == 1
        assert await db.scalar(select(func.count()).select_from(FilingTransaction)) == 2
        assert await db.scalar(select(func.count()).select_from(Notification)) == 2


async def test_concurrent_submission_retries_create_one_receipt(postgres_sessions):
    from httpx import ASGITransport, AsyncClient

    fid, filer, _clerk = await prepare_filing(postgres_sessions)

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            headers = {"X-Demo-User-Id": str(filer), "Idempotency-Key": str(uuid4())}
            responses = await asyncio.wait_for(
                asyncio.gather(
                    *[
                        client.post(f"/api/v1/filings/{fid}/submit", headers=headers)
                        for _ in range(2)
                    ]
                ),
                15,
            )
            assert [r.status_code for r in responses] == [200, 200]
            assert [r.json()["submission_count"] for r in responses] == [1, 1]
    finally:
        app.dependency_overrides.pop(get_db, None)
    async with postgres_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(FilingTransaction)) == 1
        assert await db.scalar(select(func.count()).select_from(Notification)) == 1


@pytest.mark.parametrize("postgres_sessions", [False, True], indirect=True)
async def test_postgres_transactions_reject_sql_mutation(postgres_sessions):
    from sqlalchemy.exc import DBAPIError

    fid, _filer, _clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        await filing_service.submit_filing(db, fid)
    for statement in (
        "UPDATE filing_transactions SET actor_name = 'Changed'",
        "DELETE FROM filing_transactions",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            async with postgres_sessions.begin() as db:
                await db.execute(text(statement))
    async with postgres_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(FilingTransaction)) == 1
