from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models.case import Case, CaseParticipant, ParticipantRole
from app.models.filing import FilingDocument, FilingEnvelope
from app.models.user import User, UserType
from app.services import access_service, filing_service
from tests.test_filing_history import filing_fixture


async def test_another_filer_cannot_edit_validate_or_change_documents(
    db_session, api_client, stored_document,
):
    fid, filer, _clerk, other = await filing_fixture(db_session)
    document = stored_document(fid)
    db_session.add(document)
    await db_session.flush()
    url = f"/api/v1/filings/{fid}"
    api_client.headers["X-Demo-User-Id"] = str(other)
    attempts = [
        await api_client.patch(url, json={
            "filing_description": "Changed", "expected_details_token": "0" * 64,
        }),
        await api_client.post(f"{url}/validate"),
        await api_client.post(
            f"{url}/documents", headers={"Idempotency-Key": str(uuid4())},
            data={"title": "Intruder", "document_type_code": "COMPLAINT"},
            files={"file": ("x.txt", b"Synthetic intruder document", "text/plain")},
        ),
        await api_client.delete(f"{url}/documents/{document.id}"),
    ]
    assert [response.status_code for response in attempts] == [403, 403, 403, 403]
    assert await db_session.scalar(select(func.count()).select_from(FilingDocument)) == 1

    await filing_service.submit_filing(db_session, fid)
    api_client.headers["X-Demo-User-Id"] = str(filer)
    removed = await api_client.delete(f"{url}/documents/{document.id}")
    assert removed.status_code == 400, removed.text


@pytest.mark.parametrize("user_type", ["clerk", "judge", "admin"])
async def test_self_registration_cannot_create_court_or_administrator_accounts(
    api_client, db_session, monkeypatch, user_type,
):
    monkeypatch.setattr(settings, "allow_public_registration", True)
    response = await api_client.post("/api/v1/auth/register", json={
        "email": f"{user_type}@example.com", "first_name": "Self", "last_name": "Named",
        "user_type": user_type,
    })
    assert response.status_code == 403, response.text
    assert await db_session.scalar(select(func.count()).select_from(User)) == 0


async def test_registration_rejects_case_variants_and_can_be_disabled(
    api_client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "allow_public_registration", True)
    person = {"first_name": "Alice", "last_name": "Filer", "user_type": "self_represented"}
    created = await api_client.post(
        "/api/v1/auth/register", json={**person, "email": "Alice@example.com"},
    )
    assert created.status_code == 201, created.text
    variant = await api_client.post(
        "/api/v1/auth/register", json={**person, "email": "alice@EXAMPLE.com"},
    )
    assert variant.status_code == 409, variant.text

    monkeypatch.setattr(settings, "allow_public_registration", False)
    closed = await api_client.post(
        "/api/v1/auth/register", json={**person, "email": "bob@example.com"},
    )
    assert closed.status_code == 403
    assert await db_session.scalar(select(func.count()).select_from(User)) == 1


async def test_court_staff_cannot_decide_their_own_filing(db_session, api_client, stored_document):
    fid, _filer, clerk, _other = await filing_fixture(db_session)
    source = await db_session.get(FilingEnvelope, fid)
    own = FilingEnvelope(
        court_id=source.court_id, case_type_id=source.case_type_id, filer_id=clerk,
        case_title="Staff member's own case", filing_type="initial",
    )
    db_session.add(own)
    await db_session.flush()
    db_session.add(stored_document(own.id))
    await db_session.flush()
    await filing_service.submit_filing(db_session, own.id)
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    single = await api_client.post(f"/api/v1/clerk/filings/{own.id}/review", json={
        "action": "accept", "expected_submission_count": 1,
    })
    assert single.status_code == 403, single.text
    batch = await api_client.post("/api/v1/clerk/queue/batch-review", json={
        "action": "accept", "filings": [{"filing_id": own.id, "expected_submission_count": 1}],
    })
    assert batch.status_code == 200, batch.text
    assert batch.json()["failed"] == [own.id]
    assert "Another court reviewer" in batch.json()["errors"][str(own.id)]


async def test_public_docket_accounts_are_never_offered_filing(db_session):
    fid, filer, _clerk, _other = await filing_fixture(db_session)
    source = await db_session.get(FilingEnvelope, fid)
    case = Case(
        court_id=source.court_id, case_type_id=source.case_type_id, case_number="PUB-1",
        title="Public matter", filed_date=datetime.now(UTC),
    )
    db_session.add(case)
    await db_session.flush()
    db_session.add(CaseParticipant(
        case_id=case.id, user_id=filer, role=ParticipantRole.PLAINTIFF, party_name="Party",
        access_enabled=True, reviewed_at=datetime.now(UTC),
    ))
    await db_session.flush()
    assert await access_service.user_may_file_on_case(
        db_session, await db_session.get(User, filer), case.id,
    )
    (await db_session.get(User, filer)).user_type = UserType.PUBLIC
    await db_session.flush()
    assert not await access_service.user_may_file_on_case(
        db_session, await db_session.get(User, filer), case.id,
    )
