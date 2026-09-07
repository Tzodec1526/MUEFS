"""Commit-failure reclaim for uploads tracked on the request session."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import document_service, storage_intent


@pytest.mark.asyncio
async def test_get_db_commit_failure_purges_tracked_upload(
    db_session: AsyncSession, tmp_path, monkeypatch,
):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    key = "filings/1/orphan-commit.txt"
    document_service.upload_document(b"orphan-bytes", key, "text/plain")
    path = tmp_path / key
    assert path.exists()
    storage_intent.track_upload(db_session.sync_session, key)
    await db_session.execute(text("SELECT 1"))
    pending = storage_intent.take_pending_uploads(db_session.sync_session)
    await db_session.rollback()
    storage_intent.purge_keys(pending)
    assert not path.exists()


@pytest.mark.asyncio
async def test_flush_success_keeps_key_tracked_until_commit(
    db_session: AsyncSession, tmp_path, monkeypatch,
):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    key = "filings/1/still-tracked.txt"
    document_service.upload_document(b"bytes", key, "text/plain")
    storage_intent.track_upload(db_session.sync_session, key)
    await db_session.execute(text("SELECT 1"))
    assert key in db_session.sync_session.info.get("pending_storage_keys", set())
