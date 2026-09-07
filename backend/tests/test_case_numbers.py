"""Assigned identifiers stay consistent across the case and retained receipt."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from app.models.case import Case, CaseParticipant, ParticipantRole
from app.models.court import CaseType, Court, CourtType
from app.models.filing import FilingEnvelope
from app.schemas.court_calendar import FilingDateAssessment
from app.services import filing_service
from tests.filing_requests import submission_review
from tests.test_filing_history import record_filing as record_filing
from tests.test_filing_history import upload


@pytest.mark.parametrize("court_type,code,suffix", [
    (CourtType.CIRCUIT, "CIV-GEN", "CZ"),
    (CourtType.CIRCUIT, "CIV-CONT", "CK"),
    (CourtType.DISTRICT, "CIV-GEN", "GC"),
    (CourtType.PROBATE, "PR-EST", "DE"),
    (CourtType.CIRCUIT, "NI", "NI"),
])
async def test_acceptance_uses_filing_year_and_court_case_code(
    api_client, db_session, record_filing, monkeypatch, court_type, code, suffix,
):
    fid, _filer, clerk, _other = record_filing
    filing = await db_session.get(FilingEnvelope, fid)
    court = await db_session.get(Court, filing.court_id)
    kind = await db_session.get(CaseType, filing.case_type_id)
    court.court_type = court_type
    kind.code = code
    await db_session.flush()
    await upload(api_client, fid, b"Complaint")
    await db_session.refresh(filing, ["documents"])
    submitted = await api_client.post(
        f"/api/v1/filings/{fid}/submit", json=await submission_review(api_client, fid),
    )
    assert submitted.status_code == 200, submitted.text
    # A delayed review must use the assessed filing year, not the acceptance year.
    monkeypatch.setattr(filing_service, "filing_date_for_receipt", AsyncMock(
        return_value=FilingDateAssessment(filing_date=date(2024, 12, 31)),
    ))
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    accepted = await api_client.post(f"/api/v1/clerk/filings/{fid}/review", json={
        "action": "accept", "expected_submission_count": 1,
    })
    assert accepted.status_code == 200, accepted.text
    expected = f"2024-{fid:06d}-{suffix}"
    assert accepted.json()["cms_case_number"] == expected
    case_id = accepted.json()["case_id"]
    case = (await api_client.get(f"/api/v1/cases/{case_id}")).json()
    assert case["case_number"] == expected
    history = (await api_client.get(f"/api/v1/filings/{fid}/history")).json()
    receipt = history["transactions"][0]
    assert receipt["event_type"] == "accepted"
    assert receipt["details"]["cms_case_number"] == expected


async def test_existing_case_keeps_its_assigned_number(
    api_client, db_session, record_filing,
):
    fid, filer, clerk, _other = record_filing
    filing = await db_session.get(FilingEnvelope, fid)
    case = Case(
        court_id=filing.court_id, case_type_id=filing.case_type_id,
        case_number="25-001234-CK", title="Existing case",
        filed_date=datetime(2025, 1, 2, tzinfo=UTC),
    )
    db_session.add(case)
    await db_session.flush()
    db_session.add(CaseParticipant(
        case_id=case.id, user_id=filer, role=ParticipantRole.PLAINTIFF,
        party_name="Receipt Filer", access_enabled=True,
        reviewed_at=datetime(2025, 1, 2, tzinfo=UTC),
    ))
    filing.case_id = case.id
    filing.filing_type = "subsequent"
    await db_session.flush()
    await upload(api_client, fid, b"Amended complaint")
    await db_session.refresh(filing, ["documents"])
    submitted = await api_client.post(
        f"/api/v1/filings/{fid}/submit", json=await submission_review(api_client, fid),
    )
    assert submitted.status_code == 200, submitted.text
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    accepted = await api_client.post(f"/api/v1/clerk/filings/{fid}/review", json={
        "action": "accept", "expected_submission_count": 1,
    })
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["case_id"] == case.id
    assert accepted.json()["cms_case_number"] == "25-001234-CK"
    assert case.case_number == "25-001234-CK"
