"""A filing must target the court, case and intake configuration the filer selected."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from tests.test_motions_and_search import create_court_with_case


@pytest.mark.parametrize("scenario,expected", [
    ("foreign_type", 400), ("wrong_case_type", 400), ("closed_court", 409),
    ("inactive_type", 409), ("unknown_kind", 422), ("initial_existing_case", 422),
    ("subsequent_without_case", 422), ("service_without_case", 422),
    ("missing_court", 404), ("missing_type", 404),
])
async def test_invalid_intake_cannot_create_a_filing(db_session, api_client, scenario, expected):
    user, _clerk, court, case_type, other_type, case = await create_court_with_case(db_session)
    other_court = Court(name="Other Court", county="Alcona", court_type=CourtType.CIRCUIT)
    db_session.add(other_court)
    await db_session.flush()
    foreign_type = CaseType(court_id=other_court.id, code="CIV", name="Other Civil",
                            category=CaseCategory.CIVIL, filing_fee_cents=0)
    db_session.add(foreign_type)
    await db_session.flush()
    body = {"court_id": court.id, "case_type_id": case_type.id,
            "case_id": case.id, "filing_type": "subsequent", "case_title": case.title}
    if scenario == "foreign_type":
        body["case_type_id"] = foreign_type.id
    elif scenario == "wrong_case_type":
        body["case_type_id"] = other_type.id
    elif scenario == "closed_court":
        court.is_efiling_enabled = False
    elif scenario == "inactive_type":
        case_type.is_active = False
    elif scenario == "unknown_kind":
        body["filing_type"] = "ignore_rules"
    elif scenario == "initial_existing_case":
        body["filing_type"] = "initial"
    elif scenario == "missing_court":
        body["court_id"] = 2_000_000_000
    elif scenario == "missing_type":
        body["case_type_id"] = 2_000_000_000
    else:
        body.pop("case_id")
        if scenario == "service_without_case":
            body["filing_type"] = "service_only"
    await db_session.flush()

    response = await api_client.post("/api/v1/filings", json=body,
                                     headers={"X-Demo-User-Id": str(user.id),
                                              "Idempotency-Key": str(uuid4())})
    assert response.status_code == expected, response.text
    assert await db_session.scalar(select(func.count()).select_from(FilingEnvelope)) == 0


@pytest.mark.parametrize("change,expected", [
    ("court_closed", 409), ("type_inactive", 409),
    ("case_reclassified", 400), ("case_restricted", 403),
])
async def test_saved_draft_rechecks_intake_and_retry_preserves_its_receipt(
    db_session, api_client, stored_document, monkeypatch, change, expected,
):
    from app.services import document_service

    user, _clerk, court, case_type, other_type, case = await create_court_with_case(db_session)
    case_type.filing_fee_cents = 0
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(user.id)
    created = await api_client.post("/api/v1/filings", json={
        "court_id": court.id, "case_type_id": case_type.id, "case_id": case.id,
        "filing_type": "subsequent", "case_title": case.title,
    }, headers={"Idempotency-Key": str(uuid4())})
    assert created.status_code == 201, created.text
    fid = created.json()["id"]
    document = stored_document(fid)
    db_session.add(document)
    await db_session.flush()
    assert (await api_client.post(f"/api/v1/filings/{fid}/validate")).json()["is_valid"]
    if change == "court_closed":
        court.is_efiling_enabled = False
    elif change == "type_inactive":
        case_type.is_active = False
    elif change == "case_reclassified":
        case.case_type_id = other_type.id
    else:
        case.is_sealed = True
    await db_session.flush()
    validation = await api_client.post(f"/api/v1/filings/{fid}/validate")
    assert validation.status_code == 200
    assert not validation.json()["is_valid"]
    assert validation.json()["errors"]
    if change == "type_inactive":
        available = await api_client.get(f"/api/v1/courts/{court.id}/case-types")
        assert case_type.id not in {item["id"] for item in available.json()}
        history = await api_client.get(f"/api/v1/courts/{court.id}/case-types",
                                       params={"include_inactive": True})
        names = {item["id"]: item["name"] for item in history.json()}
        assert names[case_type.id] == case_type.name
    key = {"Idempotency-Key": str(uuid4())}
    with monkeypatch.context() as blocked:
        def unexpected_read(_key):
            pytest.fail("Invalid intake reached document storage")
        blocked.setattr(document_service, "stored_integrity", unexpected_read)
        response = await api_client.post(f"/api/v1/filings/{fid}/submit", headers=key)
    assert response.status_code == expected, response.text
    filing = await db_session.get(FilingEnvelope, fid)
    assert filing.status == FilingStatus.DRAFT
    assert filing.submission_count == 0
    assert filing.submitted_at is None
    assert document.retained_at is None
    assert await db_session.scalar(select(func.count()).select_from(FilingTransaction)) == 0

    court.is_efiling_enabled = case_type.is_active = True
    case.case_type_id, case.is_sealed = case_type.id, False
    await db_session.flush()
    submitted = await api_client.post(f"/api/v1/filings/{fid}/submit", headers=key)
    assert submitted.status_code == 200, submitted.text
    receipt = submitted.json()
    assert receipt["submission_count"] == 1
    assert receipt["documents"][0]["id"] == document.id
    assert receipt["updated_at"] and receipt["submitted_at"]
    court.is_efiling_enabled = False
    await db_session.flush()
    replay = await api_client.post(f"/api/v1/filings/{fid}/submit", headers=key)
    assert replay.status_code == 200, replay.text
    assert replay.json() == receipt
    assert await db_session.scalar(select(func.count()).select_from(FilingTransaction)) == 1


@pytest.mark.parametrize("batch", [False, True])
async def test_review_checks_legacy_routing_but_can_finish_after_intake_closes(
    db_session, api_client, stored_document, monkeypatch, batch,
):
    from app.integrations.cms_adapter import CMSFilingResult
    from app.models.user import CourtRole, UserCourtRole
    from app.services import filing_service

    user, clerk, court, case_type, other_type, case = await create_court_with_case(db_session)
    db_session.add(UserCourtRole(user_id=clerk.id, court_id=court.id, role=CourtRole.CLERK))
    records = [FilingEnvelope(
        court_id=court.id, case_type_id=case_type.id, case_id=case.id, filer_id=user.id,
        filing_type="subsequent", case_title=title,
    ) for title in ("Misrouted legacy record", "Valid pending record")]
    db_session.add_all(records)
    await db_session.flush()
    for filing in records:
        db_session.add(stored_document(filing.id))
        await db_session.flush()
        await filing_service.submit_filing(db_session, filing.id)
    bad, good = records
    # A legacy/imported record cannot rely on validation at its original creation.
    bad.case_type_id = other_type.id
    court.is_efiling_enabled = case_type.is_active = False
    case.is_sealed = True
    await db_session.flush()
    cms_calls = []

    async def cms(case_number, filing_id):
        cms_calls.append(filing_id)
        return CMSFilingResult(success=True, cms_case_number=case_number, cms_filing_id="test")

    monkeypatch.setattr(filing_service, "submit_filing_to_cms", cms)
    api_client.headers["X-Demo-User-Id"] = str(clerk.id)
    if batch:
        response = await api_client.post("/api/v1/clerk/queue/batch-review", json={
            "action": "accept", "filings": [
                {"filing_id": filing.id, "expected_submission_count": 1} for filing in records
            ],
        })
        assert response.status_code == 200, response.text
        assert response.json()["failed"] == [bad.id]
        assert response.json()["succeeded"] == [good.id]
        assert "Case type" in response.json()["errors"][str(bad.id)]
    else:
        response = await api_client.post(f"/api/v1/clerk/filings/{bad.id}/review", json={
            "action": "accept", "expected_submission_count": 1,
        })
        assert response.status_code == 409, response.text
        assert "Case type" in response.text
        assert not cms_calls
        response = await api_client.post(f"/api/v1/clerk/filings/{good.id}/review", json={
            "action": "accept", "expected_submission_count": 1,
        })
        assert response.status_code == 200, response.text
    assert cms_calls == [good.id]
    await db_session.refresh(bad)
    await db_session.refresh(good)
    assert bad.status == FilingStatus.SUBMITTED and bad.reviewed_at is None
    assert good.status == FilingStatus.ACCEPTED
    assert not await db_session.scalar(select(FilingTransaction.id).where(
        FilingTransaction.filing_id == bad.id, FilingTransaction.event_type == "accepted",
    ))
    returned = await api_client.post(f"/api/v1/clerk/filings/{bad.id}/review", json={
        "action": "return", "expected_submission_count": 1,
        "reason": "Correct the case destination",
    })
    assert returned.status_code == 200, returned.text
