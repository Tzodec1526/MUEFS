"""Exercise the real request transaction, including its HTTP response boundary."""

import asyncio
import hashlib
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import database
from app.main import app
from app.models.audit import AuditLog
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.notification import Notification
from app.services import document_service, filing_service
from tests.test_filing_concurrency import POSTGRES_URL, prepare_filing
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest.mark.parametrize("postgres_sessions", [True], indirect=True)
@pytest.mark.parametrize("deferred_failure", [False, True])
async def test_submission_commits_before_http_success(
    postgres_sessions, monkeypatch, tmp_path, deferred_failure,
):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    fid, filer, _clerk = await prepare_filing(postgres_sessions)
    # Keep get_db itself: the usual API fixture replaces it and skips its commit.
    monkeypatch.setattr(database, "async_session", postgres_sessions)
    if deferred_failure:
        async with postgres_sessions.begin() as db:
            await db.execute(text("""
                CREATE FUNCTION reject_filing_commit() RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'Synthetic deferred commit rejection';
                END;
                $$ LANGUAGE plpgsql
            """))
            await db.execute(text("""
                CREATE CONSTRAINT TRIGGER reject_filing_commit
                AFTER INSERT ON filing_transactions
                DEFERRABLE INITIALLY DEFERRED
                FOR EACH ROW EXECUTE FUNCTION reject_filing_commit()
            """))

    async with postgres_sessions() as db:
        reviewed = await filing_service.get_filing(db, fid)
        review = {"expected_submission_token": reviewed.submission_token}

    visible_at_headers = []

    async def observe_response(scope, receive, send):
        async def observe_send(message):
            if message["type"] == "http.response.start":
                async with postgres_sessions() as observer:
                    filing = await observer.get(FilingEnvelope, fid)
                    transactions = await observer.scalar(
                        select(func.count()).select_from(FilingTransaction)
                    )
                    notices = await observer.scalar(select(func.count()).select_from(Notification))
                    visible_at_headers.append(
                        (message["status"], filing.status, transactions, notices)
                    )
            await send(message)

        await app(scope, receive, observe_send)

    async with AsyncClient(
        transport=ASGITransport(observe_response, raise_app_exceptions=False),
        base_url="http://test",
        headers={"X-Demo-User-Id": str(filer), "Idempotency-Key": str(uuid4())},
    ) as client:
        response = await client.post(f"/api/v1/filings/{fid}/submit", json=review)
        if deferred_failure:
            assert response.status_code == 500, response.text
            assert response.json() == {"detail": "Internal server error"}
            assert visible_at_headers == [(500, FilingStatus.DRAFT, 0, 0)]
            async with postgres_sessions.begin() as db:
                filing = await db.get(FilingEnvelope, fid)
                assert filing.submission_count == 0
                await db.execute(text("DROP TRIGGER reject_filing_commit ON filing_transactions"))
            response = await client.post(f"/api/v1/filings/{fid}/submit", json=review)
        assert response.status_code == 200, response.text
        assert visible_at_headers[-1] == (200, FilingStatus.SUBMITTED, 1, 1)
        assert response.json()["submission_count"] == 1
        # The same client key remains safe after both a failed commit and a lost response.
        replay = await client.post(f"/api/v1/filings/{fid}/submit", json=review)
        assert replay.status_code == 200
        assert replay.json()["submission_count"] == 1
        assert visible_at_headers[-1] == (200, FilingStatus.SUBMITTED, 1, 1)


@pytest.mark.parametrize("disconnect", [False, True])
async def test_slow_document_transfer_releases_database_connection(
    postgres_sessions, monkeypatch, tmp_path, disconnect,
):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    fid, filer, _clerk = await prepare_filing(postgres_sessions)
    content = b"Synthetic complaint\n" * 65536
    async with postgres_sessions.begin() as db:
        schema = await db.scalar(text("SELECT current_schema()"))
        document = await db.scalar(select(FilingDocument))
        document_id = document.id
        document_service.upload_document(content, document.file_key, document.mime_type)
        document.file_size_bytes = len(content)
        document.sha256_hash = hashlib.sha256(content).hexdigest()
    engine = create_async_engine(
        POSTGRES_URL,
        connect_args={"server_settings": {"search_path": schema}},
        pool_size=1, max_overflow=0, pool_timeout=0.2,
    )
    monkeypatch.setattr(
        database, "async_session", async_sessionmaker(engine, expire_on_commit=False)
    )
    transfer_started, finish_transfer = asyncio.Event(), asyncio.Event()
    streams = []
    real_download = document_service.download_document

    def track_stream(key):
        stream = real_download(key)
        streams.append(stream)
        return stream

    monkeypatch.setattr(document_service, "download_document", track_stream)

    async def slow_connection(scope, receive, send):
        async def slow_send(message):
            if (scope["path"].endswith("/download")
                and message["type"] == "http.response.body" and message.get("body")):
                transfer_started.set()
                await finish_transfer.wait()
            await send(message)

        await app(scope, receive, slow_send)

    try:
        async with AsyncClient(
            transport=ASGITransport(slow_connection, raise_app_exceptions=False),
            base_url="http://test", headers={"X-Demo-User-Id": str(filer)},
        ) as client:
            transfer = asyncio.create_task(client.get(f"/api/v1/documents/{document_id}/download"))
            try:
                await asyncio.wait_for(transfer_started.wait(), timeout=5)
                # A client still reading a file must not monopolize the only DB connection.
                other_request = await client.get(f"/api/v1/filings/{fid}")
                assert other_request.status_code == 200, other_request.text
                assert engine.pool.checkedout() == 0
                async with postgres_sessions() as observer:
                    assert await observer.scalar(select(func.count()).select_from(AuditLog).where(
                        AuditLog.action == "document_download", AuditLog.entity_id == document_id,
                    )) == 1
                assert not transfer.done()
            finally:
                if disconnect:
                    transfer.cancel()
                finish_transfer.set()
                if disconnect:
                    with pytest.raises(asyncio.CancelledError):
                        await asyncio.wait_for(transfer, timeout=5)
                else:
                    downloaded = await asyncio.wait_for(transfer, timeout=5)
                    assert downloaded.status_code == 200
                    assert downloaded.content == content
            assert len(streams) == 1 and streams[0].closed
    finally:
        await engine.dispose()


async def test_download_does_not_open_storage_before_its_audit_commits(
    postgres_sessions, monkeypatch, tmp_path,
):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    await prepare_filing(postgres_sessions)
    monkeypatch.setattr(database, "async_session", postgres_sessions)
    async with postgres_sessions.begin() as db:
        document = await db.scalar(select(FilingDocument))
        document_id = document.id
        filer = await db.scalar(select(FilingEnvelope.filer_id))
        await db.execute(text("""
            CREATE FUNCTION reject_download_audit() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Synthetic audit commit rejection';
            END;
            $$ LANGUAGE plpgsql
        """))
        await db.execute(text("""
            CREATE CONSTRAINT TRIGGER reject_download_audit
            AFTER INSERT ON audit_log
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION reject_download_audit()
        """))
    opened = []
    real_download = document_service.download_document

    def track_open(key):
        stream = real_download(key)
        opened.append(stream)
        return stream

    monkeypatch.setattr(document_service, "download_document", track_open)
    try:
        async with AsyncClient(
            transport=ASGITransport(app, raise_app_exceptions=False),
            base_url="http://test", headers={"X-Demo-User-Id": str(filer)},
        ) as client:
            response = await client.get(f"/api/v1/documents/{document_id}/download")
        assert response.status_code == 500
        assert not opened, "Failed audit commits must not leave an unconsumed storage stream open"
    finally:
        for stream in opened:
            stream.close()
