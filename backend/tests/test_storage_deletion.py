"""Storage deletion survives rollbacks, outages and competing cleanup workers."""

import asyncio
import hashlib
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import database
from app.main import app
from app.models.audit import AuditLog
from app.models.document_public_copy import DocumentPublicCopy
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.storage_deletion import StorageDeletion
from app.services import document_service
from app.storage_cleanup import cleanup_next
from tests.test_filing_concurrency import POSTGRES_URL, prepare_filing
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions
from tests.test_filing_history import filing_fixture
from tests.test_s3_storage import s3_storage as s3_storage

requires_postgres = pytest.mark.skipif(
    not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured",
)


@requires_postgres
@pytest.mark.parametrize("postgres_sessions", [True], indirect=True)
async def test_failed_removal_commit_preserves_original_file(
    postgres_sessions, monkeypatch, tmp_path,
):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    fid, filer, _clerk = await prepare_filing(postgres_sessions)
    monkeypatch.setattr(database, "async_session", postgres_sessions)
    async with postgres_sessions.begin() as db:
        doc = (await db.scalars(select(FilingDocument))).one()
        document_id, key = doc.id, doc.file_key
        original = (tmp_path / key).read_bytes()
        await db.execute(text("""
            CREATE FUNCTION reject_document_delete() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Synthetic deferred document deletion failure';
            END;
            $$ LANGUAGE plpgsql;
        """))
        await db.execute(text("""
            CREATE CONSTRAINT TRIGGER reject_document_delete
            AFTER DELETE ON filing_documents DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION reject_document_delete();
        """))
    async with AsyncClient(transport=ASGITransport(app, raise_app_exceptions=False),
                           base_url="http://test") as client:
        response = await client.delete(f"/api/v1/filings/{fid}/documents/{document_id}",
                                        headers={"X-Demo-User-Id": str(filer)})
    assert response.status_code == 500
    async with postgres_sessions() as db:
        assert await db.get(FilingDocument, document_id) is not None
        assert await db.scalar(select(func.count()).select_from(StorageDeletion)) == 0
    assert (tmp_path / key).exists(), "Rollback restored the document but its bytes were erased"
    assert (tmp_path / key).read_bytes() == original


@pytest.mark.parametrize("storage", ["local", pytest.param("s3", marks=pytest.mark.skipif(
    not os.getenv("MUEFS_TEST_S3_ENDPOINT"), reason="MUEFS_TEST_S3_ENDPOINT not configured",
))])
async def test_removal_commits_before_physical_deletion(
    db_session, stored_document, monkeypatch, request, storage,
):
    if storage == "s3":
        request.getfixturevalue("s3_storage")
    fid, filer, _clerk, _other = await filing_fixture(db_session)
    doc = stored_document(fid)
    db_session.add(doc)
    await db_session.commit()
    document_id, key, digest, size = doc.id, doc.file_key, doc.sha256_hash, doc.file_size_bytes
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session", sessions)
    delete = document_service.delete_document

    def unavailable(file_key):
        raise ConnectionError("Synthetic storage outage")

    monkeypatch.setattr(document_service, "delete_document", unavailable)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test",
                           headers={"X-Demo-User-Id": str(filer)}) as client:
        response = await client.delete(f"/api/v1/filings/{fid}/documents/{document_id}")
        assert response.status_code == 204, response.text
        filing = await client.get(f"/api/v1/filings/{fid}")
        assert filing.status_code == 200
        assert filing.json()["documents"] == []
    async with sessions() as db:
        assert await db.get(FilingDocument, document_id) is None
        job = (await db.scalars(select(StorageDeletion))).one()
        assert job.file_key == key
    assert document_service.stored_integrity(key) == (digest, size)
    assert await cleanup_next(sessions) == "retry"
    assert document_service.stored_integrity(key) == (digest, size)
    monkeypatch.setattr(document_service, "delete_document", delete)
    async with sessions.begin() as db:
        job = (await db.scalars(select(StorageDeletion))).one()
        job.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    assert await cleanup_next(sessions) == "deleted"
    assert await cleanup_next(sessions) is None
    with pytest.raises(FileNotFoundError):
        document_service.download_document(key)
    async with sessions() as db:
        actions = (await db.scalars(select(AuditLog.action).order_by(AuditLog.id))).all()
        assert actions == ["remove_document", "purge_draft_document"]


@pytest.mark.parametrize("retention", ["document", "filing"])
async def test_removing_received_documents_never_queues_their_storage(
    db_session, api_client, stored_document, retention,
):
    fid, filer, _clerk, _other = await filing_fixture(db_session)
    doc = stored_document(fid)
    db_session.add(doc)
    filing = await db_session.get(FilingEnvelope, fid)
    filing.status = FilingStatus.RETURNED
    if retention == "document":
        doc.retained_at = datetime.now(UTC)
    else:
        filing.submitted_at = datetime.now(UTC)
    await db_session.flush()
    response = await api_client.delete(f"/api/v1/filings/{fid}/documents/{doc.id}",
                                       headers={"X-Demo-User-Id": str(filer)})
    assert response.status_code == 204, response.text
    assert doc.removed_at is not None
    assert await db_session.scalar(select(func.count()).select_from(StorageDeletion)) == 0
    assert document_service.stored_integrity(doc.file_key) == (
        doc.sha256_hash, doc.file_size_bytes,
    )


@pytest.mark.parametrize("reference", ["original", "public_copy"])
async def test_cleanup_preserves_objects_that_are_still_referenced(
    db_session, stored_document, reference,
):
    fid, filer, _clerk, _other = await filing_fixture(db_session)
    original = stored_document(fid)
    db_session.add(original)
    await db_session.flush()
    key = original.file_key
    if reference == "public_copy":
        key = "public-copies/retained.pdf"
        content = b"Synthetic public copy"
        document_service.upload_document(content, key, "application/pdf")
        db_session.add(DocumentPublicCopy(
            document_id=original.id, created_by=filer, title="Public copy", file_key=key,
            file_size_bytes=len(content), page_count=1,
            sha256_hash=hashlib.sha256(content).hexdigest(),
            is_text_searchable=True, pii_warnings=[],
        ))
    db_session.add(StorageDeletion(document_id=999, envelope_id=fid, file_key=key))
    await db_session.commit()
    before = document_service.stored_integrity(key)
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    assert await cleanup_next(sessions) == "retry"
    assert await cleanup_next(sessions) is None  # A blocked key must not spin.
    assert document_service.stored_integrity(key) == before
    async with sessions() as db:
        job = (await db.scalars(select(StorageDeletion))).one()
        assert job.attempt_count == 1
        assert "still referenced" in job.last_error
        assert await db.scalar(select(func.count()).select_from(AuditLog)) == 0


async def test_lost_storage_response_is_retried_without_leaking_error_details(
    db_session, monkeypatch, tmp_path, caplog,
):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    key = "discarded.txt"
    document_service.upload_document(b"Discarded draft", key, "text/plain")
    db_session.add(StorageDeletion(document_id=1, envelope_id=1, file_key=key))
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    delete = document_service.delete_document

    def lose_response(file_key):
        delete(file_key)
        raise ConnectionError("Synthetic secret in storage endpoint")

    monkeypatch.setattr(document_service, "delete_document", lose_response)
    assert await cleanup_next(sessions) == "retry"
    assert not (tmp_path / key).exists()
    async with sessions.begin() as db:
        job = (await db.scalars(select(StorageDeletion))).one()
        assert job.last_error == "Storage deletion failed (ConnectionError)"
        assert "Synthetic secret" not in caplog.text
        job.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    monkeypatch.setattr(document_service, "delete_document", delete)
    assert await cleanup_next(sessions) == "deleted"
    assert await cleanup_next(sessions) is None


@requires_postgres
async def test_cleanup_commit_failure_leaves_a_recoverable_job(postgres_sessions, tmp_path):
    key = "cleanup-commit.txt"
    document_service.upload_document(b"Discarded draft", key, "text/plain")
    async with postgres_sessions.begin() as db:
        db.add(StorageDeletion(document_id=1, envelope_id=1, file_key=key))
        await db.execute(text("""
            CREATE FUNCTION reject_cleanup() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'Synthetic cleanup commit failure'; END;
            $$ LANGUAGE plpgsql;
        """))
        await db.execute(text("""
            CREATE CONSTRAINT TRIGGER reject_cleanup AFTER DELETE ON storage_deletions
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_cleanup();
        """))
    with pytest.raises(DBAPIError, match="Synthetic cleanup commit failure"):
        await cleanup_next(postgres_sessions)
    assert not (tmp_path / key).exists()
    async with postgres_sessions.begin() as db:
        assert await db.scalar(select(func.count()).select_from(StorageDeletion)) == 1
        assert await db.scalar(select(func.count()).select_from(AuditLog)) == 0
        await db.execute(text("DROP TRIGGER reject_cleanup ON storage_deletions"))
    assert await cleanup_next(postgres_sessions) == "deleted"
    assert await cleanup_next(postgres_sessions) is None


@requires_postgres
async def test_workers_skip_an_in_progress_deletion(postgres_sessions, monkeypatch, tmp_path):
    keys = ["worker-first.txt", "worker-second.txt"]
    async with postgres_sessions.begin() as db:
        for document_id, key in enumerate(keys, 1):
            document_service.upload_document(b"Discarded draft", key, "text/plain")
            db.add(StorageDeletion(document_id=document_id, envelope_id=1, file_key=key))
    entered, release = threading.Event(), threading.Event()
    delete = document_service.delete_document
    calls = []

    def pause_first(file_key):
        calls.append(file_key)
        if file_key == keys[0]:
            entered.set()
            assert release.wait(timeout=10), "Test did not release the first deletion"
        delete(file_key)

    monkeypatch.setattr(document_service, "delete_document", pause_first)
    first = asyncio.create_task(cleanup_next(postgres_sessions))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        assert await asyncio.wait_for(cleanup_next(postgres_sessions), timeout=3) == "deleted"
        assert await asyncio.wait_for(cleanup_next(postgres_sessions), timeout=3) is None
        assert (tmp_path / keys[0]).exists()
        assert not (tmp_path / keys[1]).exists()
    finally:
        release.set()
        await first
    assert calls == keys
    assert not (tmp_path / keys[0]).exists()
    async with postgres_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(StorageDeletion)) == 0
        assert await db.scalar(select(func.count()).select_from(AuditLog)) == 2


@requires_postgres
@pytest.mark.parametrize("postgres_sessions", ["d84a19f2c6b0"], indirect=True)
async def test_cleanup_migration_preserves_documents_and_pending_deletions(postgres_sessions):
    from alembic.config import Config

    from alembic import command

    fid, _filer, _clerk = await prepare_filing(postgres_sessions)

    def migrate(connection, operation, revision):
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.set_main_option(
            "script_location", str(Path(__file__).resolve().parents[1] / "alembic"),
        )
        config.attributes["connection"] = connection
        getattr(command, operation)(config, revision)

    async with postgres_sessions.begin() as db:
        original = (await db.scalars(select(FilingDocument))).one()
        original_id, digest = original.id, original.sha256_hash
        connection = await db.connection()
        await connection.run_sync(migrate, "upgrade", "head")
        await connection.run_sync(migrate, "downgrade", "d84a19f2c6b0")
        await connection.run_sync(migrate, "upgrade", "head")
        for table in ["filing_documents", "document_public_copies"]:
            indexes = await connection.run_sync(lambda conn: inspect(conn).get_indexes(table))
            assert any(index["column_names"] == ["file_key"] for index in indexes)
        db.add(StorageDeletion(document_id=999, envelope_id=fid, file_key="discarded.txt"))
    with pytest.raises(RuntimeError, match="Drain pending storage deletions"):
        async with postgres_sessions.begin() as db:
            connection = await db.connection()
            await connection.run_sync(migrate, "downgrade", "d84a19f2c6b0")
    async with postgres_sessions() as db:
        assert (await db.get(FilingDocument, original_id)).sha256_hash == digest
        assert await db.scalar(select(func.count()).select_from(StorageDeletion)) == 1
