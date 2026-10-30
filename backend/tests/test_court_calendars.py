from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.case import Case
from app.models.court_calendar import CourtCalendar
from app.models.filing_transaction import FilingTransaction
from app.models.user import CourtRole, UserCourtRole
from app.services import filing_service
from app.services.court_calendar_service import assess_date
from tests.test_filing_history import filing_fixture


def calendar(
    *, id=1, timezone="America/Detroit", start="2026-01-01", end="2026-12-31", closed=None
):
    return CourtCalendar(
        id=id,
        court_id=1,
        timezone=timezone,
        valid_from=date.fromisoformat(start),
        valid_through=date.fromisoformat(end),
        closed_dates=closed or {},
        authority_reference="Synthetic court calendar",
        published_by=1,
        published_at=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    "timestamp,timezone,expected",
    [
        ("2026-09-04T23:59:59.999999-04:00", "America/Detroit", "2026-09-04"),
        ("2026-09-05T00:00:00-04:00", "America/Detroit", "2026-09-08"),
        ("2026-09-05T04:30:00+00:00", "America/Chicago", "2026-09-04"),
        ("2026-09-05T04:30:00+00:00", "America/Detroit", "2026-09-08"),
        ("2026-03-08T06:30:00+00:00", "America/Detroit", "2026-03-09"),
        ("2026-03-08T07:30:00+00:00", "America/Detroit", "2026-03-09"),
        ("2026-11-01T05:30:00+00:00", "America/Detroit", "2026-11-02"),
        ("2026-11-01T06:30:00+00:00", "America/Detroit", "2026-11-02"),
    ],
)
def test_business_day_and_timezone_boundaries(timestamp, timezone, expected):
    result = assess_date(
        [calendar(timezone=timezone, closed={"2026-09-07": "Labor Day"})],
        datetime.fromisoformat(timestamp),
    )
    assert result.filing_date == date.fromisoformat(expected)
    assert result.timezone == timezone and result.calendar_ids == [1]


def test_year_boundary_uses_adjacent_calendars_and_fails_on_missing_coverage():
    current = calendar(closed={"2026-12-31": "Court-ordered closure"})
    following = calendar(
        id=2, start="2027-01-01", end="2027-12-31", closed={"2027-01-01": "New Year's Day"}
    )
    received = datetime.fromisoformat("2026-12-31T16:00:00-05:00")
    result = assess_date([following, current], received)
    assert result.filing_date == date(2027, 1, 4)
    assert result.calendar_ids == [1, 2]
    assert len(result.skipped_dates) == 4
    missing = assess_date([current], received)
    assert missing.filing_date is None and "coverage" in missing.error
    assert assess_date([], received).filing_date is None


def test_newest_applicable_revision_wins_and_timezone_change_requires_review():
    old = calendar()
    new = calendar(
        id=2,
        start="2026-09-04",
        end="2026-09-08",
        closed={
            "2026-09-04": "Emergency closure",
            "2026-09-07": "Labor Day",
        },
    )
    result = assess_date([new, old], datetime.fromisoformat("2026-09-04T14:00:00-04:00"))
    assert result.filing_date == date(2026, 9, 8) and result.calendar_ids == [2]
    new.timezone = "America/Chicago"
    new.valid_through = date(2026, 9, 4)
    result = assess_date([new, old], datetime.fromisoformat("2026-09-04T14:00:00-04:00"))
    assert result.filing_date is None and "timezone" in result.error


async def test_calendar_publication_is_scoped_validated_and_retained(db_session, api_client):
    fid, filer, clerk, other = await filing_fixture(db_session)
    filing = await filing_service.get_filing(db_session, fid)
    url = f"/api/v1/courts/{filing.court_id}/calendars"
    body = {
        "timezone": "America/Detroit",
        "valid_from": "2026-01-01",
        "valid_through": "2026-12-31",
        "closed_dates": {"2026-09-07": "Labor Day"},
        "authority_reference": "Court order 2026-1",
    }
    for user_id in [filer, clerk, other]:
        api_client.headers["X-Demo-User-Id"] = str(user_id)
        assert (await api_client.post(url, json=body)).status_code == 403
    db_session.add(UserCourtRole(user_id=clerk, court_id=filing.court_id, role=CourtRole.ADMIN))
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    for patch in [
        {"timezone": "Not/AZone"},
        {"valid_through": "2025-01-01"},
        {"closed_dates": {"2027-01-01": "Outside coverage"}},
        {"authority_reference": " "},
    ]:
        invalid = await api_client.post(url, json={**body, **patch})
        assert invalid.status_code == 422
    published = await api_client.post(url, json=body)
    assert published.status_code == 201, published.text
    cid = published.json()["id"]
    api_client.headers.pop("X-Demo-User-Id")
    listed = (await api_client.get(url)).json()
    assert listed["calendars"][0]["id"] == cid and listed["can_publish"] is False
    preview = await api_client.get(
        f"/api/v1/courts/{filing.court_id}/filing-date",
        params={
            "received_at": "2026-09-05T04:00:00Z",
        },
    )
    assert preview.json()["filing_date"] == "2026-09-08"
    no_offset = await api_client.get(
        f"/api/v1/courts/{filing.court_id}/filing-date",
        params={
            "received_at": "2026-09-05T04:00:00",
        },
    )
    assert no_offset.status_code == 400
    for statement in ["UPDATE court_calendars SET timezone='UTC'", "DELETE FROM court_calendars"]:
        with pytest.raises(IntegrityError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(text(statement))


async def test_acceptance_uses_receipt_date_and_preserves_old_calendar_evidence(
    db_session, monkeypatch, stored_document,
):
    fid, filer, clerk, _ = await filing_fixture(db_session)
    db_session.add(stored_document(fid))
    await db_session.flush()
    filing = await filing_service.get_filing(db_session, fid)
    old = calendar()
    old.court_id, old.published_by = filing.court_id, clerk
    db_session.add(old)
    await db_session.flush()
    received = datetime(2026, 9, 4, 20, tzinfo=UTC)

    class ReceiptClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return received

    monkeypatch.setattr(filing_service, "datetime", ReceiptClock)
    await filing_service.submit_filing(db_session, fid)
    first = await db_session.scalar(
        select(FilingTransaction).where(FilingTransaction.event_type == "submitted")
    )
    assert first.details["filing_date_basis"]["filing_date"] == "2026-09-04"
    newer = calendar(id=2, closed={"2026-09-04": "Emergency closure", "2026-09-07": "Labor Day"})
    newer.court_id, newer.published_by = filing.court_id, clerk
    db_session.add(newer)
    await db_session.flush()
    monkeypatch.setattr(filing_service, "datetime", datetime)
    accepted = await filing_service.review_filing(
        db_session, fid, clerk, "accept", expected_submission_count=1
    )
    case = await db_session.get(Case, accepted.case_id)
    assert accepted.filing_date == case.filing_date == date(2026, 9, 8)
    assert case.filed_date.replace(tzinfo=UTC) == received
    assert first.details["filing_date_basis"]["calendar_ids"] == [1]
    reassessment = await db_session.scalar(
        select(FilingTransaction).where(
            FilingTransaction.event_type == "filing_date_assessed",
        )
    )
    assert reassessment.details["previous_filing_date"] == "2026-09-04"
    assert reassessment.details["filing_date_basis"]["calendar_ids"] == [2]


async def test_production_acceptance_requires_calendar_coverage(
    db_session, monkeypatch, stored_document,
):
    fid, _filer, clerk, _ = await filing_fixture(db_session)
    db_session.add(stored_document(fid))
    await db_session.flush()
    filing = await filing_service.submit_filing(db_session, fid)
    assert filing.filing_date is None and filing.filing_date_basis["error"]
    monkeypatch.setattr(settings, "allow_demo_mode", False)
    with pytest.raises(filing_service.FilingDateUnavailableError, match="calendar"):
        await filing_service.review_filing(
            db_session, fid, clerk, "accept", expected_submission_count=1
        )
