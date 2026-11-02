from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.storage_deletion import StorageDeletion
from tests.test_filing_concurrency import POSTGRES_URL
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions

EASTERN = timezone(timedelta(hours=-4))


async def _round_trip(sessions):
    received = datetime(2026, 9, 4, 14, 0, 0, 123456, tzinfo=EASTERN)
    async with sessions.begin() as db:
        db.add(StorageDeletion(document_id=1, envelope_id=1, file_key="a.txt",
                               next_attempt_at=received))
        db.add(StorageDeletion(document_id=2, envelope_id=1, file_key="b.txt",
                               next_attempt_at=datetime(2026, 9, 4, 18, 30)))
    async with sessions() as db:
        rows = list(await db.scalars(select(StorageDeletion).order_by(StorageDeletion.id)))
        assert [row.next_attempt_at for row in rows] == [
            datetime(2026, 9, 4, 18, 0, 0, 123456, tzinfo=UTC),
            datetime(2026, 9, 4, 18, 30, tzinfo=UTC),
        ]
        assert all(row.next_attempt_at.tzinfo is UTC for row in rows)
        assert all(row.queued_at.tzinfo is UTC for row in rows)
        found = await db.scalar(select(StorageDeletion.file_key).where(
            StorageDeletion.next_attempt_at == received,
        ))
        assert found == "a.txt"
        earlier = await db.scalar(select(StorageDeletion.file_key).where(
            StorageDeletion.next_attempt_at < datetime(2026, 9, 4, 14, 15, tzinfo=EASTERN),
        ))
        assert earlier == "a.txt"


async def test_sqlite_stores_and_reads_timestamps_as_utc(db_session):
    await _round_trip(async_sessionmaker(db_session.bind, expire_on_commit=False))


@pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")
async def test_postgres_stores_and_reads_timestamps_as_utc(postgres_sessions):
    await _round_trip(postgres_sessions)
