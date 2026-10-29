"""Exercise date decision conflicts and authority changes on PostgreSQL."""

import asyncio
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.api import filing_dates
from app.database import get_db
from app.main import app
from app.models.case import CaseParticipant, ParticipantRole
from app.models.filing import FilingDocument, FilingEnvelope
from app.models.filing_transaction import FilingTransaction
from app.models.user import User, UserCourtRole
from app.services import filing_service
from tests.test_filing_concurrency import POSTGRES_URL, prepare_filing
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions
from tests.test_filing_date_orders import DECISION, ORDER

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest.mark.parametrize("postgres_sessions", [True], indirect=True)
@pytest.mark.parametrize("shared", ["filing", "case"])
async def test_competing_orders_commit_once(postgres_sessions, stored_document, shared, tmp_path):
    fid, filer, clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        await filing_service.submit_filing(db, fid)
        first = await filing_service.review_filing(
            db, fid, clerk, "accept", expected_submission_count=1
        )
        second_id = fid
        if shared == "case":
            db.add(CaseParticipant(
                case_id=first.case_id, user_id=filer, role=ParticipantRole.PLAINTIFF,
                party_name="Reviewed filer", access_enabled=True,
                reviewed_at=datetime.now(UTC),
            ))
            second = FilingEnvelope(
                court_id=first.court_id,
                case_id=first.case_id,
                case_type_id=first.case_type_id,
                filer_id=filer,
            )
            db.add(second)
            await db.flush()
            db.add(stored_document(second.id))
            await db.flush()
            await filing_service.submit_filing(db, second.id)
            await filing_service.review_filing(
                db, second.id, clerk, "accept", expected_submission_count=1
            )
            second_id = second.id

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            decision = {**DECISION, "expected_version": "2"}
            if shared == "case":
                decision.update(update_case_date="true", expected_case_version="0")
            responses = await asyncio.wait_for(
                asyncio.gather(
                    *[
                        client.post(
                            f"/api/v1/clerk/filings/{filing_id}/filing-date",
                            headers={"X-Demo-User-Id": str(clerk)},
                            data=decision,
                            files={"file": ("order.pdf", ORDER)},
                        )
                        for filing_id in (fid, second_id)
                    ]
                ),
                15,
            )
            assert sorted(response.status_code for response in responses) == [201, 409]
        async with postgres_sessions() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FilingTransaction)
                    .where(
                        FilingTransaction.event_type == "filing_date_ordered",
                    )
                )
                == 1
            )
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FilingDocument)
                    .where(
                        FilingDocument.document_type_code == "FILING_DATE_ORDER",
                    )
                )
                == 1
            )
        assert len(list(tmp_path.rglob("*.pdf"))) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize(
    "change", ["deactivation", "court_assignment", "acceptance", "resubmission"]
)
async def test_change_during_inspection_blocks_stale_order(
    postgres_sessions,
    monkeypatch,
    change,
    tmp_path,
):
    fid, _, clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        await filing_service.submit_filing(db, fid)
    inspected, proceed = asyncio.Event(), asyncio.Event()
    inspect = filing_dates.inspect_upload

    async def paused_inspection(*args, **kwargs):
        result = await inspect(*args, **kwargs)
        inspected.set()
        await asyncio.wait_for(proceed.wait(), 10)
        return result

    monkeypatch.setattr(filing_dates, "inspect_upload", paused_inspection)

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            pending = asyncio.create_task(
                client.post(
                    f"/api/v1/clerk/filings/{fid}/filing-date",
                    headers={"X-Demo-User-Id": str(clerk)},
                    data=DECISION,
                    files={"file": ("order.pdf", ORDER)},
                )
            )
            try:
                await asyncio.wait_for(inspected.wait(), 10)
                async with postgres_sessions.begin() as db:
                    if change in ("deactivation", "court_assignment"):
                        actor = await db.scalar(
                            select(User).where(User.id == clerk).with_for_update()
                        )
                        if change == "deactivation":
                            actor.is_active = False
                        else:
                            await db.execute(
                                delete(UserCourtRole).where(UserCourtRole.user_id == clerk)
                            )
                    elif change == "acceptance":
                        await filing_service.review_filing(
                            db, fid, clerk, "accept", expected_submission_count=1
                        )
                    else:
                        await filing_service.review_filing(
                            db, fid, clerk, "return", "Correction", expected_submission_count=1
                        )
                        await filing_service.submit_filing(db, fid)
                proceed.set()
                response = await asyncio.wait_for(pending, 10)
                assert response.status_code == (
                    403 if change in ("deactivation", "court_assignment") else 409
                ), response.text
            finally:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        async with postgres_sessions() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FilingTransaction)
                    .where(
                        FilingTransaction.event_type == "filing_date_ordered",
                    )
                )
                == 0
            )
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FilingDocument)
                    .where(
                        FilingDocument.document_type_code == "FILING_DATE_ORDER",
                    )
                )
                == 0
            )
        assert not list(tmp_path.rglob("*.pdf"))
    finally:
        app.dependency_overrides.pop(get_db, None)
