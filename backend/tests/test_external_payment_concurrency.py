"""PostgreSQL arbitrates external receipt conflicts and preserves migrated financial evidence."""

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError

from app.api import external_payments
from app.api.auth import get_current_user_id
from app.config import settings
from app.database import get_db
from app.main import app
from app.models.filing import FilingEnvelope
from app.models.filing_transaction import FilingTransaction
from app.models.payment import Payment, PaymentStatus
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import audit_service
from tests.test_external_payments import external_receipt
from tests.test_fee_assessments import assessment
from tests.test_filing_concurrency import POSTGRES_URL, prepare_filing
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest_asyncio.fixture
async def payment_client(postgres_sessions, monkeypatch):
    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    async def identity(request: Request):
        return int(request.headers["X-Test-User"])

    monkeypatch.setitem(app.dependency_overrides, get_db, database)
    monkeypatch.setitem(app.dependency_overrides, get_current_user_id, identity)
    monkeypatch.setattr(settings, "external_payments_enabled", True)
    monkeypatch.setattr(settings, "allow_demo_mode", False)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def payment_filings(postgres_sessions, payment_client, stored_document):
    first, filer, administrator = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        filing = await db.get(FilingEnvelope, first)
        second = FilingEnvelope(
            court_id=filing.court_id,
            case_type_id=filing.case_type_id,
            filer_id=filer,
            filing_type="initial",
            case_title="Second synthetic filing",
        )
        other_admin = User(
            email="second-cashier@example.com",
            first_name="Second",
            last_name="Administrator",
            user_type=UserType.CLERK,
        )
        db.add_all([second, other_admin])
        await db.flush()
        db.add(stored_document(second.id))
        db.add_all(
            [
                UserCourtRole(user_id=actor, court_id=filing.court_id, role=CourtRole.ADMIN)
                for actor in (administrator, other_admin.id)
            ]
        )
        second_id, other_id = second.id, other_admin.id
    for fid, actor in [(first, administrator), (second_id, other_id)]:
        response = await payment_client.post(
            f"/api/v1/clerk/filings/{fid}/fees",
            json=assessment(0, 1000),
            headers={"X-Test-User": str(actor)},
        )
        assert response.status_code == 201, response.text
    return first, second_id, administrator, other_id


@pytest.mark.parametrize("postgres_sessions", [False, True], indirect=True)
@pytest.mark.parametrize("conflict", ["same_filing", "same_receipt", "same_request_key"])
async def test_competing_receipts_commit_one_credit(
    postgres_sessions,
    payment_filings,
    payment_client,
    conflict,
):
    first, second, administrator, other_admin = payment_filings
    keys = [str(uuid4()), str(uuid4())]
    if conflict != "same_receipt":
        keys[1] = keys[0]
    if conflict == "same_filing":
        second, other_admin = first, administrator
    responses = await asyncio.gather(
        *[
            payment_client.post(
                f"/api/v1/filings/{fid}/external-payments",
                json=external_receipt(),
                headers={"X-Test-User": str(actor), "Idempotency-Key": key},
            )
            for fid, actor, key in [(first, administrator, keys[0]), (second, other_admin, keys[1])]
        ]
    )
    assert sorted(item.status_code for item in responses) == (
        [200, 201] if conflict == "same_filing" else [201, 409]
    ), [item.text for item in responses]
    async with postgres_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Payment)) == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(FilingTransaction)
                .where(FilingTransaction.event_type == "fee_payment_recorded")
            )
            == 1
        )
        assert await db.scalar(select(func.sum(FilingEnvelope.payment_version))) == 1


@pytest.mark.parametrize("postgres_sessions", [False, True], indirect=True)
async def test_reversed_receipt_can_be_correctly_reallocated_but_never_erased(
    postgres_sessions,
    payment_filings,
    payment_client,
):
    first, second, administrator, other_admin = payment_filings
    response = await payment_client.post(
        f"/api/v1/filings/{first}/external-payments",
        json=external_receipt(),
        headers={"X-Test-User": str(administrator), "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    original = response.json()
    response = await payment_client.post(
        f"/api/v1/filings/{second}/external-payments",
        json={**external_receipt(), "receipt_system": "  SYNTHETIC   COURT CASHIER "},
        headers={"X-Test-User": str(other_admin), "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 409 and f"#{first}" in response.text
    reverse = await payment_client.post(
        f"/api/v1/filings/{first}/external-payments/{original['id']}/reverse",
        json={
            "expected_payment_version": 1,
            "reason": "Reallocate to the correct filing",
            "reviewed": True,
        },
        headers={"X-Test-User": str(administrator)},
    )
    assert reverse.status_code == 200, reverse.text
    corrected = await payment_client.post(
        f"/api/v1/filings/{second}/external-payments",
        json=external_receipt(),
        headers={"X-Test-User": str(other_admin), "Idempotency-Key": str(uuid4())},
    )
    assert corrected.status_code == 201, corrected.text
    for mutation in [
        "UPDATE payments SET amount_cents=1",
        "DELETE FROM payments",
        "UPDATE payments SET status='COMPLETED' WHERE status='REVERSED'",
    ]:
        with pytest.raises(DBAPIError, match="External payment evidence is retained"):
            async with postgres_sessions.begin() as db:
                await db.execute(text(mutation))
    async with postgres_sessions() as db:
        records = list(await db.scalars(select(Payment).order_by(Payment.id)))
        assert [payment.status for payment in records] == [
            PaymentStatus.REVERSED,
            PaymentStatus.COMPLETED,
        ]
        assert records[0].external_receipt == original["external_receipt"]


async def test_credit_rechecks_authority_after_a_concurrent_revocation(
    postgres_sessions,
    payment_filings,
    payment_client,
    monkeypatch,
):
    first, _, administrator, _ = payment_filings
    reached = asyncio.Event()
    real_lock = external_payments.lock_current_user

    async def observed_lock(*args):
        reached.set()
        return await real_lock(*args)

    monkeypatch.setattr(external_payments, "lock_current_user", observed_lock)
    task = None
    try:
        async with postgres_sessions.begin() as editor:
            await editor.scalar(select(User).where(User.id == administrator).with_for_update())
            task = asyncio.create_task(
                payment_client.post(
                    f"/api/v1/filings/{first}/external-payments",
                    json=external_receipt(),
                    headers={"X-Test-User": str(administrator), "Idempotency-Key": str(uuid4())},
                )
            )
            await asyncio.wait_for(reached.wait(), 5)
            await editor.execute(
                delete(UserCourtRole).where(
                    UserCourtRole.user_id == administrator, UserCourtRole.role == CourtRole.ADMIN
                )
            )
        response = await asyncio.wait_for(task, 5)
        assert response.status_code == 403, response.text
        async with postgres_sessions() as db:
            assert await db.scalar(select(func.count()).select_from(Payment)) == 0
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_failed_audit_cannot_commit_a_credit_or_payment_version(
    postgres_sessions,
    payment_filings,
    payment_client,
    monkeypatch,
):
    first, _, administrator, _ = payment_filings

    async def unavailable(*args, **kwargs):
        raise RuntimeError("Synthetic audit outage")

    monkeypatch.setattr(audit_service, "log_action", unavailable)
    with pytest.raises(RuntimeError, match="Synthetic audit outage"):
        await payment_client.post(
            f"/api/v1/filings/{first}/external-payments",
            json=external_receipt(),
            headers={"X-Test-User": str(administrator), "Idempotency-Key": str(uuid4())},
        )
    async with postgres_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Payment)) == 0
        assert (await db.get(FilingEnvelope, first)).payment_version == 0
        assert (
            await db.scalar(
                select(func.count())
                .select_from(FilingTransaction)
                .where(FilingTransaction.event_type == "fee_payment_recorded")
            )
            == 0
        )


@pytest.mark.parametrize("postgres_sessions", ["a17d42b9c8e3"], indirect=True)
async def test_external_payment_migration_preserves_legacy_payments_and_retained_credits(
    postgres_sessions,
):
    from alembic.config import Config

    from alembic import command

    fid, filer, _ = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        legacy_id = await db.scalar(
            text("""INSERT INTO payments
            (envelope_id, payer_id, amount_cents, status, transaction_ref, is_simulated)
            VALUES (:filing, :filer, 250, 'COMPLETED', 'SYN-LEGACY', true) RETURNING id"""),
            {"filing": fid, "filer": filer},
        )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))

    def migrate(connection, operation, target):
        config.attributes["connection"] = connection
        getattr(command, operation)(config, target)

    engine = postgres_sessions.kw["bind"]
    for operation, target in [
        ("upgrade", "head"),
        ("downgrade", "a17d42b9c8e3"),
        ("upgrade", "head"),
    ]:
        async with engine.connect() as connection:
            await connection.run_sync(migrate, operation, target)
    async with postgres_sessions.begin() as db:
        legacy = await db.get(Payment, legacy_id)
        assert legacy.amount_cents == 250 and legacy.transaction_ref == "SYN-LEGACY"
        assert legacy.external_receipt is None and legacy.external_request_key is None
        assert (await db.get(FilingEnvelope, fid)).payment_version == 0
        db.add(
            Payment(
                envelope_id=fid,
                payer_id=filer,
                amount_cents=750,
                status=PaymentStatus.COMPLETED,
                external_request_key=str(uuid4()),
                external_receipt_key="a" * 64,
                external_receipt={"reference": "SYN-RETAINED"},
            )
        )
    with pytest.raises(RuntimeError, match="Cannot discard retained external payment"):
        async with engine.connect() as connection:
            await connection.run_sync(migrate, "downgrade", "a17d42b9c8e3")
    async with postgres_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Payment)) == 2
