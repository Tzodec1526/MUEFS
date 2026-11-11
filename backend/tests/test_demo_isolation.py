import asyncio
import os
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.main import app
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingEnvelope
from app.models.user import User, UserType
from app.services import document_service


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_DATA_DIR", str(tmp_path))
    import app.demo.session_db as sdb

    monkeypatch.setattr(sdb, "_last_access", {})
    monkeypatch.setattr(sdb, "_last_sweep", 0.0)
    monkeypatch.setattr(sdb, "_engines", {})
    sdb._sessions_dir().mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{sdb._template_db()}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        court = Court(
            name="Demo Court", county="Wayne", court_type=CourtType.CIRCUIT,
            is_efiling_enabled=True,
        )
        s.add(court)
        s.flush()
        s.add(CaseType(
            court_id=court.id, code="C", name="Civil",
            category=CaseCategory.CIVIL, filing_fee_cents=100,
        ))
        s.add(User(
            email="filer@example.invalid", first_name="Demo", last_name="Filer",
            user_type=UserType.SELF_REPRESENTED,
        ))
        s.commit()
    engine.dispose()
    return sdb


async def test_demo_api_commits_to_the_visitors_copy_of_the_template(demo, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_db, demo.get_demo_db)
    async with _visitor(demo, "a" * 32) as first, _visitor(demo, "b" * 32) as second:
        response = await first.post("/api/v1/filings", json={
            "court_id": 1, "case_type_id": 1, "filing_type": "initial", "case_title": "A's filing",
        }, headers={"Idempotency-Key": str(uuid4())})
        assert response.status_code == 201, response.text
        filing_id = response.json()["id"]
        assert (await first.get("/api/v1/filings")).json()["total"] == 1

        assert (await second.get("/api/v1/courts/1")).json()["name"] == "Demo Court"
        assert (await second.get("/api/v1/filings")).json()["total"] == 0
        assert (await second.get(f"/api/v1/filings/{filing_id}")).status_code == 404

        filing = (await first.get(f"/api/v1/filings/{filing_id}")).json()
        assert filing["case_title"] == "A's filing"
    engine = create_engine(f"sqlite:///{demo._template_db()}")
    with Session(engine) as observer:
        assert observer.scalar(select(func.count()).select_from(FilingEnvelope)) == 0
    engine.dispose()


async def test_a_full_demo_refuses_new_visitors_instead_of_sharing_a_sandbox(demo, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_db, demo.get_demo_db)
    monkeypatch.setattr("app.config.settings.demo_max_sessions", 1)
    async with _visitor(demo, "a" * 32) as first, _visitor(demo, "b" * 32) as second:
        assert (await first.get("/api/v1/filings")).status_code == 200
        refused = await second.get("/api/v1/filings")
    assert refused.status_code == 503, refused.text
    assert refused.json()["detail"] == "The demo is at capacity. Try again in a few minutes."
    assert refused.headers["retry-after"] == "300"
    assert "set-cookie" not in refused.headers
    assert demo.active_session_count() == 1


async def test_an_api_request_without_a_session_cookie_is_refused(demo, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_db, demo.get_demo_db)
    for cookie in (None, "_shared", "not-a-session-id"):
        async with _visitor(demo, cookie) as client:
            refused = await client.get("/api/v1/filings")
        assert refused.status_code == 401, (cookie, refused.text)
        assert "Reload the page" in refused.json()["detail"]
        assert "set-cookie" not in refused.headers
    assert demo.active_session_count() == 0

    class _Req:
        cookies: dict = {}

    assert demo._is_valid_sid(demo.resolve_sid(_Req()))
    assert demo.resolve_sid(_Req(), allocate=False) is None


async def test_the_session_cookie_is_secure_behind_an_https_proxy(demo, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_db, demo.get_demo_db)
    async with _visitor(demo, "c" * 32) as client:
        plain = await client.get("/api/v1/filings")
        proxied = await client.get("/api/v1/filings", headers={"X-Forwarded-Proto": "https"})
    assert "Secure" not in plain.headers["set-cookie"]
    assert proxied.headers["set-cookie"].endswith("; SameSite=Lax; Secure")


def test_parallel_first_requests_publish_one_complete_database(demo, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    started, finish = Event(), Event()
    copyfile = demo.shutil.copyfile
    copies = []
    sid = "e" * 32

    def slow_copy(source, destination):
        copies.append(destination)
        destination.write_bytes(b"incomplete database")
        started.set()
        assert finish.wait(5)
        return copyfile(source, destination)

    monkeypatch.setattr(demo.shutil, "copyfile", slow_copy)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(demo.open_sandbox, sid)
        try:
            assert started.wait(5)
            second = pool.submit(demo.open_sandbox, sid)
            assert not demo._session_path(sid).exists()
        finally:
            finish.set()
        assert first.result(timeout=5) == second.result(timeout=5)
    assert len(copies) == 1
    assert demo._session_path(sid).read_bytes() == demo._template_db().read_bytes()


def test_failed_session_copy_can_be_retried(demo, monkeypatch):
    sid = "f" * 32
    copyfile = demo.shutil.copyfile

    def interrupted_copy(source, destination):
        destination.write_bytes(b"incomplete database")
        raise OSError("disk temporarily unavailable")

    monkeypatch.setattr(demo.shutil, "copyfile", interrupted_copy)
    with pytest.raises(OSError, match="disk temporarily unavailable"):
        demo.open_sandbox(sid)
    assert not demo._session_path(sid).exists()
    assert not list(demo._sessions_dir().glob("*.tmp"))

    monkeypatch.setattr(demo.shutil, "copyfile", copyfile)
    assert demo.open_sandbox(sid).read_bytes() == demo._template_db().read_bytes()


def test_client_chosen_ids_cannot_allocate_sandboxes_beyond_the_cap(demo, monkeypatch):
    monkeypatch.setattr("app.config.settings.demo_max_sessions", 2)
    issued = [demo.open_sandbox(sid) for sid in ("1" * 32, "2" * 32)]
    with pytest.raises(demo.DemoCapacityError):
        demo.open_sandbox("3" * 32)
    assert not demo._session_path("3" * 32).exists()
    assert demo.active_session_count() == 2
    assert [demo.open_sandbox(sid) for sid in ("1" * 32, "2" * 32)] == issued


def test_sweep_keeps_recent_sandboxes_after_restart(demo, monkeypatch):
    recent, idle = demo.open_sandbox("4" * 32), demo.open_sandbox("5" * 32)
    expired = time.time() - demo.settings.demo_session_ttl_minutes * 60 - 1
    os.utime(idle, (expired, expired))
    monkeypatch.setattr(demo, "_last_access", {})
    monkeypatch.setattr(demo, "_last_sweep", 0.0)
    demo._sweep_idle()
    assert recent.exists()
    assert not idle.exists()


def _visitor(demo, sid):
    return AsyncClient(
        transport=ASGITransport(demo.DemoSessionMiddleware(app)), base_url="http://test",
        headers={"X-Demo-User-Id": "1"}, cookies={demo.COOKIE_NAME: sid} if sid else {},
    )


async def _upload(client, filing_id, payload):
    return await client.post(
        f"/api/v1/filings/{filing_id}/documents", headers={"Idempotency-Key": str(uuid4())},
        data={"title": "Record", "document_type_code": "COMPLAINT"},
        files={"file": ("record.txt", payload, "text/plain")},
    )


async def _draft(client):
    response = await client.post("/api/v1/filings", json={
        "court_id": 1, "case_type_id": 1, "filing_type": "initial", "case_title": "Upload",
    }, headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_sandbox_documents_stay_in_and_leave_with_their_sandbox(demo, monkeypatch, tmp_path):
    shared = tmp_path / "shared"
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: shared)
    monkeypatch.setitem(app.dependency_overrides, get_db, demo.get_demo_db)
    sid = "a" * 32
    async with _visitor(demo, sid) as client:
        uploaded = await _upload(client, await _draft(client), b"sandbox bytes")
        assert uploaded.status_code == 200, uploaded.text
        downloaded = await client.get(f"/api/v1/documents/{uploaded.json()['id']}/download")
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == b"sandbox bytes"
    folder = demo._uploads_dir() / sid
    assert [p.read_bytes() for p in folder.rglob("*") if p.is_file()] == [b"sandbox bytes"]
    assert not shared.exists()

    expired = time.time() - demo.settings.demo_session_ttl_minutes * 60 - 1
    os.utime(demo._session_path(sid), (expired, expired))
    monkeypatch.setattr(demo, "_last_access", {})
    monkeypatch.setattr(demo, "_last_sweep", 0.0)
    demo._sweep_idle()
    assert not demo._session_path(sid).exists()
    assert not folder.exists()


async def test_a_full_sandbox_refuses_uploads_with_a_clear_message(demo, monkeypatch, tmp_path):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path / "shared")
    monkeypatch.setitem(app.dependency_overrides, get_db, demo.get_demo_db)
    monkeypatch.setattr(demo.settings, "demo_storage_quota_mb", 1)
    sid = "b" * 32
    async with _visitor(demo, sid) as client:
        filing_id = await _draft(client)
        assert (await _upload(client, filing_id, b"a" * 700_000)).status_code == 200
        refused = await _upload(client, filing_id, b"b" * 700_000)
    assert refused.status_code == 507, refused.text
    assert "used its document storage" in refused.json()["detail"]
    stored = [p for p in (demo._uploads_dir() / sid).rglob("*") if p.is_file()]
    assert [p.stat().st_size for p in stored] == [700_000]


def test_sandboxes_read_shared_samples_but_change_only_their_own_files(demo, monkeypatch, tmp_path):
    shared = tmp_path / "shared"
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: shared)
    document_service.upload_document(b"seeded sample", "demo/sample.pdf", "application/pdf")
    first, second = demo.upload_scope("1" * 32), demo.upload_scope("2" * 32)
    token = document_service.storage_scope.set(first)
    try:
        document_service.upload_document(b"first draft", "filings/1/draft.txt", "text/plain")
        assert document_service.stored_integrity("demo/sample.pdf")[1] == len(b"seeded sample")
        document_service.delete_document("demo/sample.pdf")
    finally:
        document_service.storage_scope.reset(token)
    assert (shared / "demo" / "sample.pdf").read_bytes() == b"seeded sample"
    assert (first.root / "filings" / "1" / "draft.txt").read_bytes() == b"first draft"
    token = document_service.storage_scope.set(second)
    try:
        with pytest.raises(FileNotFoundError):
            document_service.download_document("filings/1/draft.txt")
    finally:
        document_service.storage_scope.reset(token)


def test_sandbox_uploads_stop_at_the_quota_and_the_disk_reserve(demo, monkeypatch, tmp_path):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path / "shared")
    scope = document_service.LocalStorageScope(
        root=demo._uploads_dir() / ("3" * 32), quota_bytes=10,
    )
    token = document_service.storage_scope.set(scope)
    try:
        document_service.upload_document(b"12345678", "filings/1/a.txt", "text/plain")
        with pytest.raises(document_service.StorageQuotaExceededError, match="used its"):
            document_service.upload_document(b"123", "filings/1/b.txt", "text/plain")
        document_service.delete_document("filings/1/a.txt")
        document_service.upload_document(b"123", "filings/1/b.txt", "text/plain")
        monkeypatch.setattr(
            document_service.shutil, "disk_usage", lambda path: SimpleNamespace(free=1024),
        )
        with pytest.raises(document_service.StorageQuotaExceededError, match="storage is full"):
            document_service.upload_document(b"1", "filings/1/c.txt", "text/plain")
    finally:
        document_service.storage_scope.reset(token)
    assert sorted(p.name for p in scope.root.rglob("*") if p.is_file()) == ["b.txt"]


def test_boot_removes_uploads_that_belong_to_no_current_sandbox(demo, monkeypatch):
    from app.demo import schema

    monkeypatch.setattr(schema, "prepare_demo_schema", lambda engine: None)
    live = "6" * 32
    demo.open_sandbox(live)
    uploads = demo._uploads_dir()
    for sid in (live, "7" * 32, "_shared"):
        (uploads / sid / "filings").mkdir(parents=True)
        (uploads / sid / "filings" / "record.txt").write_bytes(b"record")
    demo.seed_template()
    assert [p.name for p in uploads.iterdir()] == [live]


async def test_removing_a_draft_frees_the_sandbox_quota(demo, monkeypatch, tmp_path):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path / "shared")
    monkeypatch.setitem(app.dependency_overrides, get_db, demo.get_demo_db)
    monkeypatch.setattr(demo.settings, "demo_storage_quota_mb", 1)
    sid = "8" * 32
    async with _visitor(demo, sid) as client:
        filing_id = await _draft(client)
        first = await _upload(client, filing_id, b"a" * 700_000)
        assert first.status_code == 200, first.text
        removed = await client.delete(f"/api/v1/filings/{filing_id}/documents/{first.json()['id']}")
        assert removed.status_code == 204, removed.text
        again = await _upload(client, filing_id, b"b" * 700_000)
        assert again.status_code == 200, again.text
    stored = [p for p in (demo._uploads_dir() / sid).rglob("*") if p.is_file()]
    assert [p.read_bytes()[:1] for p in stored] == [b"b"]


def test_a_sandbox_deleted_after_opening_is_not_recreated_empty(demo):
    sid = "9" * 32
    path = demo.open_sandbox(sid)
    assert demo._last_access[sid]
    path.unlink()

    class _Request:
        state = type("State", (), {"demo_database": path})()

    async def open_session():
        dependency = demo.get_demo_db(_Request())
        session = await anext(dependency)
        try:
            await session.execute(select(Court.id))
        finally:
            await dependency.aclose()

    with pytest.raises(OperationalError):
        asyncio.run(open_session())
    assert not path.exists()
    assert demo.open_sandbox(sid).read_bytes() == demo._template_db().read_bytes()


async def test_a_sandbox_reuses_one_engine_until_it_is_swept(demo, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_db, demo.get_demo_db)
    engines = []
    create = demo.create_async_engine

    def recorded_engine(*args, **kwargs):
        engines.append(create(*args, **kwargs))
        return engines[-1]

    monkeypatch.setattr(demo, "create_async_engine", recorded_engine)
    sid = "9" * 32
    async with _visitor(demo, sid) as client:
        filing_id = await _draft(client)
        for _ in range(3):
            assert (await client.get(f"/api/v1/filings/{filing_id}")).status_code == 200
    assert len(engines) == 1
    expired = time.time() - demo.settings.demo_session_ttl_minutes * 60 - 1
    os.utime(demo._session_path(sid), (expired, expired))
    monkeypatch.setattr(demo, "_last_access", {})
    monkeypatch.setattr(demo, "_last_sweep", 0.0)
    demo._sweep_idle()
    assert not demo._session_path(sid).exists()
    async with _visitor(demo, sid) as client:
        assert (await client.get(f"/api/v1/filings/{filing_id}")).status_code == 404
        assert (await client.get("/api/v1/filings")).json()["total"] == 0
    assert len(engines) == 2
