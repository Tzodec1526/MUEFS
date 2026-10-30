import threading
from contextlib import aclosing

import anyio
import pytest
from fastapi import Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import database
from app.models.filing import FilingDocument
from app.models.user import User, UserType
from app.services import document_service, storage_intent
from tests.test_demo_isolation import demo as demo


@pytest.mark.parametrize("provider", ["regular", "demo"])
@pytest.mark.parametrize("outcome", ["commit", "request_error", "commit_error", "cancelled"])
async def test_request_dependency_keeps_storage_and_database_in_sync(
    db_session, tmp_path, monkeypatch, demo, provider, outcome,
):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    if provider == "regular":
        engine = db_session.bind
        monkeypatch.setattr(database, "async_session", async_sessionmaker(
            engine, expire_on_commit=False,
        ))
        dependency = database.get_db()
    else:
        sid = "c" * 32
        sandbox = demo.open_sandbox(sid)
        request = Request({"type": "http", "state": {"demo_database": sandbox}})
        dependency = demo.get_demo_db(request)
        engine = create_async_engine(f"sqlite+aiosqlite:///{demo._session_path(sid)}")

    loop_thread = threading.get_ident()
    deletion_threads = []
    delete = document_service.delete_document

    def observed_delete(file_key):
        deletion_threads.append(threading.get_ident())
        delete(file_key)

    monkeypatch.setattr(document_service, "delete_document", observed_delete)
    key = "filings/1/request-upload.txt"
    path = tmp_path / key
    try:
        async with aclosing(dependency):
            session = await anext(dependency)
            session.add(User(
                email="rollback@example.test", first_name="Test", last_name="Upload",
                user_type=UserType.SELF_REPRESENTED,
            ))
            await session.flush()
            document_service.upload_document(b"uncommitted bytes", key, "text/plain")
            storage_intent.track_upload(session.sync_session, key)

            if outcome == "cancelled":
                with anyio.CancelScope() as scope:
                    scope.cancel()
                    try:
                        await anyio.sleep(0)
                    except BaseException as exc:
                        await dependency.athrow(exc)
                assert scope.cancelled_caught
            elif outcome == "request_error":
                with pytest.raises(RuntimeError, match="request failed"):
                    await dependency.athrow(RuntimeError("request failed"))
            elif outcome == "commit_error":
                async def failed_commit():
                    raise RuntimeError("commit failed")

                monkeypatch.setattr(session, "commit", failed_commit)
                with pytest.raises(RuntimeError, match="commit failed"):
                    await anext(dependency)
            else:
                with pytest.raises(StopAsyncIteration):
                    await anext(dependency)

        assert path.exists() is (outcome == "commit")
        assert not storage_intent.take_pending_uploads(session.sync_session)
        if outcome != "commit":
            assert deletion_threads and all(t != loop_thread for t in deletion_threads)
        async with async_sessionmaker(engine)() as observer:
            saved = await observer.scalar(select(User.id).where(
                User.email == "rollback@example.test",
            ))
            assert bool(saved) is (outcome == "commit")
    finally:
        if provider == "demo":
            await engine.dispose()


@pytest.mark.parametrize("provider", ["regular", "demo"])
async def test_a_commit_applied_before_failing_keeps_the_documents_it_saved(
    db_session, tmp_path, monkeypatch, demo, provider,
):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    if provider == "regular":
        monkeypatch.setattr(database, "async_session", async_sessionmaker(
            db_session.bind, expire_on_commit=False,
        ))
        dependency = database.get_db()
    else:
        sandbox = demo.open_sandbox("d" * 32)
        request = Request({"type": "http", "state": {"demo_database": sandbox}})
        dependency = demo.get_demo_db(request)
    saved, unreferenced = "filings/1/saved.txt", "filings/1/unreferenced.txt"
    async with aclosing(dependency):
        session = await anext(dependency)
        for key in (saved, unreferenced):
            document_service.upload_document(b"bytes", key, "text/plain")
            storage_intent.track_upload(session.sync_session, key)
        session.add(FilingDocument(
            envelope_id=1, document_type_code="COMPLAINT", title="Complaint",
            file_key=saved, file_size_bytes=5, mime_type="text/plain", sha256_hash="0" * 64,
        ))

        async def applied_then_lost():
            await session.flush()
            await (await session.connection()).exec_driver_sql("COMMIT")
            raise ConnectionError("commit acknowledgement lost")

        monkeypatch.setattr(session, "commit", applied_then_lost)
        with pytest.raises(ConnectionError):
            await anext(dependency)
    assert (tmp_path / saved).exists()
    assert not (tmp_path / unreferenced).exists()


@pytest.mark.asyncio
async def test_flush_success_keeps_key_tracked_until_commit(
    db_session: AsyncSession, tmp_path, monkeypatch,
):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    key = "filings/1/still-tracked.txt"
    document_service.upload_document(b"bytes", key, "text/plain")
    storage_intent.track_upload(db_session.sync_session, key)
    db_session.add(User(
        email="flushed@example.test", first_name="Flushed", last_name="Upload",
        user_type=UserType.SELF_REPRESENTED,
    ))
    await db_session.flush()
    assert key in db_session.sync_session.info.get("pending_storage_keys", set())
    async with db_session.begin_nested():
        await db_session.execute(text("SELECT 1"))
    assert key in db_session.sync_session.info.get("pending_storage_keys", set())
    await db_session.commit()
    assert key not in db_session.sync_session.info.get("pending_storage_keys", set())
