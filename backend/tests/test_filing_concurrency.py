"""Run with MUEFS_TEST_POSTGRES_URL against a disposable PostgreSQL database.

Each test uses a uniquely named schema and drops only that schema on completion.
"""

import asyncio
import hashlib
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
from app.models.payment import Payment
from app.services import document_service, filing_service
from tests.test_email_delivery import smtp_sink as smtp_sink
from tests.test_fee_waivers import decision_pdf
from tests.test_filing_history import filing_fixture

POSTGRES_URL = os.getenv("MUEFS_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest.mark.parametrize("operation", ["waiver", "payment"])
async def test_concurrent_waiver_and_post_denial_payment_commit_once(
    postgres_sessions, tmp_path, monkeypatch, operation,
):
    from datetime import UTC, datetime

    from httpx import ASGITransport, AsyncClient

    from app.services import document_service

    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    fid, filer, clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        filing = await filing_service.submit_filing(db, fid)
        filing.fee_waiver_requested = True
        if operation == "payment":
            filing.fee_waiver_granted = False
            filing.fee_waiver_decided_at = datetime.now(UTC)
            filing.fee_waiver_amount_due_cents = 750

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            if operation == "waiver":
                async def act():
                    return await client.post(f"/api/v1/clerk/filings/{fid}/fee-waiver",
                        headers={"X-Demo-User-Id": str(clerk)},
                        data={"action": "grant_public_assistance"},
                        files={"file": ("signed.pdf", decision_pdf(), "application/pdf")})
            else:
                async def act():
                    return await client.post("/api/v1/payments/process",
                        headers={"X-Demo-User-Id": str(filer)},
                        json={"envelope_id": fid, "payment_method": "credit_card",
                              "amount_cents": 750, "expected_fee_version": filing.fee_version})
            results = await asyncio.wait_for(asyncio.gather(act(), act()), 15)
        expected = [200 if operation == "waiver" else 201, 409]
        assert sorted(r.status_code for r in results) == expected
        async with postgres_sessions() as db:
            assert await db.scalar(select(func.count()).select_from(FilingTransaction)) == 2
            if operation == "waiver":
                assert await db.scalar(select(func.count()).select_from(FilingDocument).where(
                    FilingDocument.document_type_code == "FEE_WAIVER_ORDER",
                )) == 1
            else:
                assert await db.scalar(select(func.count()).select_from(Payment)) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def postgres_sessions(request, stored_document):
    schema = f"filing_test_{uuid4().hex}"
    admin = create_async_engine(POSTGRES_URL)
    async with admin.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public"))
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        POSTGRES_URL, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with engine.connect() as conn:
            if getattr(request, "param", False):
                from alembic.config import Config

                from alembic import command

                def migrate(connection):
                    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
                    config.set_main_option(
                        "script_location", str(Path(__file__).resolve().parents[1] / "alembic"),
                    )
                    config.attributes["connection"] = connection
                    target = request.param if isinstance(request.param, str) else "head"
                    command.upgrade(config, target)

                await conn.run_sync(migrate)
            else:
                async with conn.begin():
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
        content = b"Synthetic complaint"
        file_key = f"postgres-tests/{uuid4()}.txt"
        document_service.upload_document(content, file_key, "text/plain")
        db.add(
            FilingDocument(
                envelope_id=fid,
                title="Complaint",
                document_type_code="COMPLAINT",
                file_key=file_key,
                mime_type="text/plain",
                file_size_bytes=len(content),
                sha256_hash=hashlib.sha256(content).hexdigest(),
                pii_warnings=[],
            )
        )
    return fid, filer, clerk


async def test_submission_refreshes_previously_read_intake_configuration(postgres_sessions):
    from app.models.court import Court
    from app.models.filing import FilingEnvelope

    fid, _filer, _clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        filing = await db.get(FilingEnvelope, fid)
        old_court = await db.get(Court, filing.court_id)
        assert old_court.is_efiling_enabled
        async with postgres_sessions.begin() as operator:
            await operator.execute(text("UPDATE courts SET is_efiling_enabled=false WHERE id=:id"),
                                   {"id": old_court.id})
        with pytest.raises(filing_service.FilingDestinationError, match="not accepting"):
            await filing_service.submit_filing(db, fid)
        assert filing.submitted_at is None
        assert filing.submission_count == 0
        assert await db.scalar(select(func.count()).select_from(FilingTransaction)) == 0


@pytest.mark.parametrize("postgres_sessions", [True], indirect=True)
@pytest.mark.parametrize("configuration", ["court", "case_type"])
async def test_intake_change_waits_for_submission_to_commit(
    postgres_sessions, monkeypatch, configuration,
):
    from httpx import ASGITransport, AsyncClient

    from app.models.filing import FilingEnvelope

    fid, filer, _clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions() as db:
        filing = await db.get(FilingEnvelope, fid)
        court_id, case_type_id = filing.court_id, filing.case_type_id
    reached_storage, release, changing = asyncio.Event(), asyncio.Event(), asyncio.Event()
    verify = filing_service.verify_filing_documents

    async def pause_after_intake(filing):
        await verify(filing)
        reached_storage.set()
        await release.wait()

    monkeypatch.setattr(filing_service, "verify_filing_documents", pause_after_intake)

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    changing_pid = None

    async def close_intake():
        nonlocal changing_pid
        async with postgres_sessions.begin() as db:
            changing_pid = await db.scalar(text("SELECT pg_backend_pid()"))
            changing.set()
            sql, target = (
                ("UPDATE courts SET is_efiling_enabled=false WHERE id=:id", court_id)
                if configuration == "court" else
                ("UPDATE case_types SET is_active=false WHERE id=:id", case_type_id)
            )
            await db.execute(text(sql), {"id": target})

    app.dependency_overrides[get_db] = database
    pending = []
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test",
                               headers={"X-Demo-User-Id": str(filer)}) as client:
            key = {"Idempotency-Key": str(uuid4())}
            submission = asyncio.create_task(
                client.post(f"/api/v1/filings/{fid}/submit", headers=key)
            )
            pending.append(submission)
            await asyncio.wait_for(reached_storage.wait(), 5)
            closure = asyncio.create_task(close_intake())
            pending.append(closure)
            await asyncio.wait_for(changing.wait(), 5)
            async with asyncio.timeout(5), postgres_sessions() as observer:
                while not await observer.scalar(text("SELECT cardinality(pg_blocking_pids(:pid))"),
                                                {"pid": changing_pid}):
                    await asyncio.sleep(0.01)
            assert not closure.done()
            release.set()
            response, _ = await asyncio.wait_for(asyncio.gather(submission, closure), 10)
            assert response.status_code == 200, response.text
            replay = await client.post(f"/api/v1/filings/{fid}/submit", headers=key)
            assert replay.status_code == 200, replay.text
            assert replay.json() == response.json()
            new_draft = await client.post("/api/v1/filings", json={
                "court_id": court_id, "case_type_id": case_type_id,
                "filing_type": "initial", "case_title": "After intake closure",
            }, headers={"Idempotency-Key": str(uuid4())})
            assert new_draft.status_code == 409, new_draft.text
        async with postgres_sessions() as db:
            assert await db.scalar(select(func.count()).select_from(FilingTransaction)) == 1
    finally:
        release.set()
        for task in pending:
            if not task.done():
                task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("postgres_sessions", [True], indirect=True)
@pytest.mark.parametrize("operation", ["request", "assess", "pay"])
async def test_concurrent_fee_actions_record_once(postgres_sessions, operation):
    from httpx import ASGITransport, AsyncClient

    from tests.test_fee_assessments import assessment

    fid, filer, clerk = await prepare_filing(postgres_sessions)

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            if operation == "pay":
                fees = await client.post(f"/api/v1/clerk/filings/{fid}/fees",
                    headers={"X-Demo-User-Id": str(clerk)}, json=assessment(0, 750))
                assert fees.status_code == 201, fees.text
                url = "/api/v1/payments/process"
                actor = filer
                body = {"envelope_id": fid, "amount_cents": 750, "payment_method": "credit_card",
                        "expected_fee_version": fees.json()["version"]}
            elif operation == "assess":
                url = f"/api/v1/clerk/filings/{fid}/fees"
                actor, body = clerk, assessment(0, 750)
            else:
                url = f"/api/v1/filings/{fid}/fee-review"
                actor, body = filer, {"expected_version": 0, "reason": "Review exemption"}
            responses = await asyncio.wait_for(asyncio.gather(*[
                client.post(url, headers={"X-Demo-User-Id": str(actor)}, json=body)
                for _ in range(2)
            ]), 15)
            assert sorted(response.status_code for response in responses) == [201, 409]
        async with postgres_sessions() as db:
            assert await db.scalar(select(func.count()).select_from(FilingTransaction)) == (
                2 if operation == "pay" else 1
            )
            assert await db.scalar(select(func.count()).select_from(Payment)) == (
                operation == "pay"
            )
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("postgres_sessions", [True], indirect=True)
async def test_document_upload_cannot_leave_a_concurrent_assessment_current(postgres_sessions):
    from httpx import ASGITransport, AsyncClient

    from app.services.fee_assessment_service import fee_state
    from tests.test_fee_assessments import assessment

    fid, filer, clerk = await prepare_filing(postgres_sessions)

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            first = await client.post(f"/api/v1/clerk/filings/{fid}/fees",
                headers={"X-Demo-User-Id": str(clerk)}, json=assessment(0, 750))
            assert first.status_code == 201, first.text
            assessed, uploaded = await asyncio.wait_for(asyncio.gather(
                client.post(f"/api/v1/clerk/filings/{fid}/fees",
                    headers={"X-Demo-User-Id": str(clerk)},
                    json=assessment(first.json()["version"], 750)),
                client.post(f"/api/v1/filings/{fid}/documents",
                    headers={"X-Demo-User-Id": str(filer)},
                    data={"title": "Additional evidence", "document_type_code": "EXHIBIT"},
                    files={"file": ("evidence.pdf", decision_pdf(), "application/pdf")}),
            ), 15)
            assert assessed.status_code in (201, 409) and uploaded.status_code == 200
        async with postgres_sessions() as db:
            filing = await filing_service.get_filing(db, fid)
            fees = await fee_state(db, filing, filer)
            assert fees.assessment_stale and fees.total_cents is None and not fees.obligation_met
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_fee_screen_reads_documents_and_balance_from_one_revision(
    postgres_sessions, monkeypatch,
):
    from httpx import ASGITransport, AsyncClient

    from app.api import fee_assessments
    from tests.test_fee_assessments import assessment

    fid, filer, clerk = await prepare_filing(postgres_sessions)
    read_ready, upload_started, finish_read = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_state, original_filing = fee_assessments.fee_state, filing_service.get_filing

    async def hold_fee_read(db, filing, user_id=None):
        if user_id == filer:
            read_ready.set()
            await asyncio.wait_for(finish_read.wait(), 10)
        return await original_state(db, filing, user_id)

    async def observe_upload(db, filing_id, *, for_update=False):
        if for_update:
            upload_started.set()
        return await original_filing(db, filing_id, for_update=for_update)

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            first = await client.post(f"/api/v1/clerk/filings/{fid}/fees",
                headers={"X-Demo-User-Id": str(clerk)}, json=assessment(0, 750))
            assert first.status_code == 201, first.text
            monkeypatch.setattr(fee_assessments, "fee_state", hold_fee_read)
            monkeypatch.setattr(filing_service, "get_filing", observe_upload)
            read = asyncio.create_task(client.get(f"/api/v1/filings/{fid}/fees",
                headers={"X-Demo-User-Id": str(filer)}))
            await asyncio.wait_for(read_ready.wait(), 10)
            upload = asyncio.create_task(client.post(f"/api/v1/filings/{fid}/documents",
                headers={"X-Demo-User-Id": str(filer)},
                data={"title": "New evidence", "document_type_code": "EXHIBIT"},
                files={"file": ("evidence.pdf", decision_pdf(), "application/pdf")}))
            await asyncio.wait_for(upload_started.wait(), 10)
            finish_read.set()
            snapshot, changed = await asyncio.wait_for(asyncio.gather(read, upload), 15)
            assert snapshot.status_code == 200 and changed.status_code == 200
            assert snapshot.json()["version"] == first.json()["version"]
            assert snapshot.json()["total_cents"] == 750
            assert len(snapshot.json()["filing"]["documents"]) == 1
            after = await client.get(f"/api/v1/filings/{fid}/fees",
                headers={"X-Demo-User-Id": str(filer)})
            assert after.json()["assessment_stale"]
            assert len(after.json()["filing"]["documents"]) == 2
    finally:
        finish_read.set()
        app.dependency_overrides.pop(get_db, None)


async def test_payment_audit_failure_rolls_back_credit_and_receipt(postgres_sessions, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.services import audit_service
    from tests.test_fee_assessments import assessment

    fid, filer, clerk = await prepare_filing(postgres_sessions)

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    async def fail_audit(*args, **kwargs):
        raise RuntimeError("Audit storage unavailable")

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app, raise_app_exceptions=False),
                               base_url="http://test") as client:
            first = await client.post(f"/api/v1/clerk/filings/{fid}/fees",
                headers={"X-Demo-User-Id": str(clerk)}, json=assessment(0, 750))
            assert first.status_code == 201, first.text
            monkeypatch.setattr(audit_service, "log_action", fail_audit)
            failed = await client.post("/api/v1/payments/process",
                headers={"X-Demo-User-Id": str(filer)}, json={
                    "envelope_id": fid, "amount_cents": 750, "payment_method": "credit_card",
                    "expected_fee_version": first.json()["version"],
                })
            assert failed.status_code == 500
        async with postgres_sessions() as db:
            filing = await filing_service.get_filing(db, fid)
            assert filing.payment_id is None
            assert await db.scalar(select(func.count()).select_from(Payment)) == 0
            assert await db.scalar(select(func.count()).select_from(FilingTransaction)) == 1
            assert await db.scalar(select(func.count()).select_from(Notification)) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


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
            result = await filing_service.review_filing(
                db, fid, clerk, "accept", expected_submission_count=1
            )
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


@pytest.mark.parametrize("postgres_sessions", [False, True], indirect=True)
async def test_review_rejects_a_new_submission_even_when_status_matches_its_old_read(
    postgres_sessions, monkeypatch,
):
    fid, _filer, clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        await filing_service.submit_filing(db, fid)
    async with postgres_sessions.begin() as reviewer:
        before = await filing_service.get_filing(reviewer, fid)
        assert before.submission_count == 1 and before.status == FilingStatus.SUBMITTED
        async with postgres_sessions.begin() as correction:
            await filing_service.review_filing(
                correction, fid, clerk, "return", "Correction needed", expected_submission_count=1
            )
            after = await filing_service.submit_filing(correction, fid)
            assert after.submission_count == 2 and after.status == before.status

        async def unexpected_verification(*args):
            pytest.fail("An outdated decision must stop before storage or CMS work")

        monkeypatch.setattr(filing_service, "verify_filing_documents", unexpected_verification)
        monkeypatch.setattr(filing_service, "submit_filing_to_cms", unexpected_verification)
        with pytest.raises(filing_service.StaleFilingReviewError, match="resubmitted"):
            await filing_service.review_filing(
                reviewer, fid, clerk, "accept", expected_submission_count=before.submission_count
            )
    async with postgres_sessions() as db:
        filing = await filing_service.get_filing(db, fid)
        assert filing.status == FilingStatus.SUBMITTED and filing.submission_count == 2
        assert filing.case_id is None and filing.reviewer_id is None
        assert await db.scalar(select(func.count()).select_from(Case)) == 0
        assert await db.scalar(select(func.count()).select_from(FilingTransaction)) == 3
        assert await db.scalar(select(func.count()).select_from(Notification)) == 3


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
async def test_postgres_retained_records_reject_sql_mutation(postgres_sessions):
    from datetime import UTC, date, datetime

    from sqlalchemy.exc import DBAPIError

    from app.models.audit import AuditLog
    from app.models.court_calendar import CourtCalendar
    from app.models.notification import NotificationDeliveryEvent

    fid, _filer, clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        filing = await filing_service.submit_filing(db, fid)
        db.add(AuditLog(user_id=clerk, action="retention_fixture", entity_type="user"))
        notice_id = await db.scalar(select(Notification.id))
        db.add(NotificationDeliveryEvent(
            notification_id=notice_id, attempt_number=0, outcome="queued",
            occurred_at=datetime.now(UTC), message="Synthetic retained message",
        ))
        db.add(CourtCalendar(
            court_id=filing.court_id, timezone="America/Detroit",
            valid_from=date(2026, 1, 1), valid_through=date(2026, 12, 31),
            closed_dates={"2026-09-07": "Labor Day"}, authority_reference="Test court calendar",
            published_by=clerk, published_at=datetime.now(UTC),
        ))
    for statement in (
        "UPDATE filing_transactions SET actor_name = 'Changed'",
        "DELETE FROM filing_transactions",
        "UPDATE court_calendars SET timezone = 'UTC'",
        "DELETE FROM court_calendars",
        "UPDATE notification_delivery_events SET outcome = 'changed'",
        "DELETE FROM notification_delivery_events",
        "UPDATE audit_log SET action = 'changed'",
        "DELETE FROM audit_log",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            async with postgres_sessions.begin() as db:
                await db.execute(text(statement))
    async with postgres_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(FilingTransaction)) == 1
        assert await db.scalar(select(func.count()).select_from(CourtCalendar)) == 1
        assert await db.scalar(select(func.count()).select_from(NotificationDeliveryEvent)) == 1
        assert await db.scalar(select(func.count()).select_from(AuditLog)) == 1


@pytest.mark.parametrize("postgres_sessions", [False, True], indirect=True)
async def test_postgres_workers_claim_a_notice_once(postgres_sessions, smtp_sink):
    from app.services import email_delivery_service as delivery
    from tests.test_email_delivery import prepare_notice

    async with postgres_sessions.begin() as db:
        nid, *_ = await prepare_notice(db)
    outcomes = await asyncio.gather(delivery.deliver_next(postgres_sessions),
                                    delivery.deliver_next(postgres_sessions))
    assert sorted(outcomes) == [False, True]
    assert len(smtp_sink["messages"]) == 1
    async with postgres_sessions() as db:
        notice = await db.get(Notification, nid)
        assert notice.delivery_status.value == "sent" and notice.attempt_count == 1
