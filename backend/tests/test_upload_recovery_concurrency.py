"""Verify upload retry serialization and its commit boundary on real PostgreSQL."""

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app import database
from app.main import app
from app.models.audit import AuditLog
from app.models.filing import DocumentUploadRequest, FilingDocument, FilingEnvelope
from app.services import document_service, filing_service
from app.storage_cleanup import cleanup_next
from app.utils import malware_scan
from tests.test_filing_concurrency import POSTGRES_URL, prepare_filing
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest.mark.parametrize("postgres_sessions", [True], indirect=True)
@pytest.mark.parametrize("changed_payload", [False, True])
async def test_simultaneous_upload_retries_commit_one_document(
    postgres_sessions, monkeypatch, tmp_path, changed_payload,
):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    fid, filer, _clerk = await prepare_filing(postgres_sessions)
    monkeypatch.setattr(database, "async_session", postgres_sessions)
    scanning, contending, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    scans, attempts = 0, 0
    real_scan, real_get = malware_scan.scan_upload, filing_service.get_filing

    async def slow_scan(content):
        nonlocal scans
        scans += 1
        result = await real_scan(content)
        scanning.set()
        await release.wait()
        return result

    async def get_filing(db, filing_id, **options):
        nonlocal attempts
        if options.get("for_update"):
            attempts += 1
            if attempts == 2:
                contending.set()
        return await real_get(db, filing_id, **options)

    monkeypatch.setattr(malware_scan, "scan_upload", slow_scan)
    monkeypatch.setattr(filing_service, "get_filing", get_filing)
    committed_at_headers = []

    async def observe_response(scope, receive, send):
        async def observe_send(message):
            if message["type"] == "http.response.start" and message["status"] == 200:
                async with postgres_sessions() as db:
                    committed_at_headers.append(await db.scalar(
                        select(func.count()).select_from(DocumentUploadRequest),
                    ))
            await send(message)
        await app(scope, receive, observe_send)

    async with postgres_sessions() as db:
        before = (await db.get(FilingEnvelope, fid)).fee_version
    tasks = []
    headers = {"X-Demo-User-Id": str(filer), "Idempotency-Key": str(uuid4())}
    data = {"title": "Contended upload", "document_type_code": "EXHIBIT"}
    content = b"Synthetic concurrent document"
    try:
        async with AsyncClient(transport=ASGITransport(observe_response),
                               base_url="http://test", headers=headers) as client:
            first = asyncio.create_task(client.post(f"/api/v1/filings/{fid}/documents",
                data=data, files={"file": ("evidence.txt", content, "text/plain")}))
            tasks.append(first)
            await asyncio.wait_for(scanning.wait(), 5)
            second = asyncio.create_task(client.post(f"/api/v1/filings/{fid}/documents",
                data=data, files={"file": ("evidence.txt",
                    b"Different bytes" if changed_payload else content, "text/plain")}))
            tasks.append(second)
            await asyncio.wait_for(contending.wait(), 5)
            assert not second.done()
            release.set()
            responses = await asyncio.wait_for(asyncio.gather(*tasks), 10)
        assert [r.status_code for r in responses] == [200, 409 if changed_payload else 200]
        if not changed_payload:
            assert responses[0].json() == responses[1].json()
        assert scans == 1
        assert committed_at_headers == ([1] if changed_payload else [1, 1])
        async with postgres_sessions() as db:
            assert await db.scalar(select(func.count()).select_from(DocumentUploadRequest)) == 1
            assert await db.scalar(select(func.count()).select_from(FilingDocument)) == 2
            assert await db.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "upload_document",
            )) == 1
            assert (await db.get(FilingEnvelope, fid)).fee_version == before + 1
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("postgres_sessions", ["c72d9fa083b1"], indirect=True)
async def test_upload_request_migration_preserves_legacy_documents_and_retry_keys(
    postgres_sessions, monkeypatch, tmp_path,
):
    from alembic.config import Config

    from alembic import command

    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    fid, filer, _clerk = await prepare_filing(postgres_sessions)
    monkeypatch.setattr(database, "async_session", postgres_sessions)

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
        await connection.run_sync(migrate, "downgrade", "c72d9fa083b1")
        await connection.run_sync(migrate, "upgrade", "head")

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test",
                           headers={"X-Demo-User-Id": str(filer)}) as client:
        key = str(uuid4())
        url = f"/api/v1/filings/{fid}/documents"
        fields = {"title": "Temporary upload", "document_type_code": "EXHIBIT"}
        file = {"file": ("temporary.txt", b"Synthetic temporary document", "text/plain")}
        uploaded = await client.post(url, headers={"Idempotency-Key": key}, data=fields, files=file)
        assert uploaded.status_code == 200, uploaded.text
        removed = await client.delete(f"{url}/{uploaded.json()['id']}")
        assert removed.status_code == 204, removed.text
        retry = await client.post(url, headers={"Idempotency-Key": key}, data=fields, files=file)
        assert retry.status_code == 409, retry.text
    async with postgres_sessions() as db:
        request = await db.get(DocumentUploadRequest, (fid, key))
        assert request.document_id is None  # PostgreSQL preserves the key on document deletion.
        assert (await db.get(FilingDocument, original_id)).sha256_hash == digest
    assert await cleanup_next(postgres_sessions) == "deleted"
    with pytest.raises(RuntimeError, match="Cannot discard retained document upload requests"):
        async with postgres_sessions.begin() as db:
            connection = await db.connection()
            await connection.run_sync(migrate, "downgrade", "c72d9fa083b1")
