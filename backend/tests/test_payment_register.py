"""Reconciliation reads retained events, with precise periods and court isolation."""

import csv
import io
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models.filing import FilingEnvelope
from app.models.filing_transaction import FilingTransaction
from app.models.user import User, UserType
from app.services import filing_record_service
from tests.test_external_payments import external_filing as external_filing
from tests.test_external_payments import external_receipt
from tests.test_fee_assessments import fee_filing as fee_filing

PERIOD = {"date_from": "2026-03-08", "date_to": "2026-03-08", "timezone": "America/Detroit"}


def activity(fid, actor, *, amount=400, simulated=False, reference="SYN-REGISTER", at=None):
    return FilingTransaction(
        id=str(uuid4()), filing_id=fid, submission_number=0,
        event_type="fee_payment_recorded" if amount > 0 else "fee_payment_reversed",
        actor_id=actor, actor_name="Register evaluator",
        occurred_at=at or datetime(2026, 3, 8, 8, tzinfo=UTC),
        details={"reason": "Synthetic receipt verification", "payment": {
            "id": 100, "amount_cents": abs(amount), "is_simulated": simulated,
            "external_receipt": {"system": "Synthetic cashier", "reference": reference,
                                 "received_at": "2026-01-01T12:00:00Z"},
        }},
    )


async def test_reversal_of_an_older_credit_appears_in_its_recorded_day(
    external_filing, api_client, db_session, monkeypatch,
):
    fid, _, clerk, _, _ = external_filing
    court = (await db_session.get(FilingEnvelope, fid)).court_id
    recorded_at = datetime(2026, 3, 8, 4, 30, tzinfo=UTC)  # March 7 in Detroit.
    monkeypatch.setattr(filing_record_service, "datetime",
                        SimpleNamespace(now=lambda _: recorded_at))
    base = f"/api/v1/filings/{fid}"
    credit = await api_client.post(f"{base}/external-payments", json=external_receipt(),
                                   headers={"Idempotency-Key": str(uuid4())})
    assert credit.status_code == 201, credit.text
    recorded_at = datetime(2026, 3, 8, 7, 30, tzinfo=UTC)
    reversed_credit = await api_client.post(
        f"{base}/external-payments/{credit.json()['id']}/reverse",
        json={"expected_payment_version": 1, "reason": "Receipt belonged to another filing",
              "reviewed": True},
    )
    assert reversed_credit.status_code == 200, reversed_credit.text
    monkeypatch.setattr(settings, "external_payments_enabled", False)
    response = await api_client.get("/api/v1/clerk/payment-register",
                                    params={"court_id": court, **PERIOD})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["range_start"] == "2026-03-08T05:00:00Z"
    assert report["range_end"] == "2026-03-09T04:00:00Z"  # 23-hour DST day.
    assert report["totals"] == {"credits_cents": 0, "reversals_cents": 1000}
    assert report["total"] == 1
    entry = report["entries"][0]
    assert entry["amount_cents"] == -1000 and entry["actor_id"] == clerk
    assert entry["payment_id"] == credit.json()["id"]
    assert entry["reason"] == "Receipt belonged to another filing"
    assert entry["receipt_reference"] == "SYN-RECEIPT-1"
    assert entry["received_at"] == "2026-01-01T17:00:00Z"
    both = (await api_client.get("/api/v1/clerk/payment-register", params={
        "court_id": court, **PERIOD, "date_from": "2026-03-07",
    })).json()
    assert both["totals"] == {"credits_cents": 1000, "reversals_cents": 1000}
    assert [row["amount_cents"] for row in both["entries"]] == [-1000, 1000]


async def test_page_totals_exclude_other_courts_and_keep_simulations_separate(
    external_filing, db_session, api_client,
):
    fid, filer, clerk, _, _ = external_filing
    filing = await db_session.get(FilingEnvelope, fid)
    from app.models.court import Court, CourtType

    foreign = Court(name="Other synthetic court", county="Other", court_type=CourtType.CIRCUIT)
    db_session.add(foreign)
    await db_session.flush()
    other = FilingEnvelope(court_id=foreign.id, filer_id=filer, case_type_id=filing.case_type_id)
    db_session.add(other)
    await db_session.flush()
    entries = [activity(fid, clerk, amount=100_000_000) for _ in range(51)]
    db_session.add_all([*entries, activity(fid, clerk, amount=-400),
                        activity(fid, clerk, simulated=True, amount=999),
                        activity(other.id, clerk, amount=777)])
    await db_session.flush()
    params = {"court_id": filing.court_id, **PERIOD}
    first = (await api_client.get("/api/v1/clerk/payment-register", params=params)).json()
    second = (await api_client.get("/api/v1/clerk/payment-register",
                                   params={**params, "page": 2})).json()
    assert first["total"] == second["total"] == 52
    assert first["totals"] == {"credits_cents": 5_100_000_000, "reversals_cents": 400}
    assert second["totals"] == first["totals"]
    assert len(first["entries"]) == 50 and len(second["entries"]) == 2
    assert len({row["event_id"] for row in first["entries"] + second["entries"]}) == 52
    empty_page = (await api_client.get("/api/v1/clerk/payment-register",
                                      params={**params, "page": 3})).json()
    assert empty_page["total"] == 52 and empty_page["entries"] == []
    simulations = (await api_client.get("/api/v1/clerk/payment-register",
                                        params={**params, "include_simulated": True})).json()
    assert simulations["total"] == 53
    assert simulations["totals"] == first["totals"]
    assert simulations["simulated_totals"] == {"credits_cents": 999, "reversals_cents": 0}


async def test_period_uses_inclusive_local_dates_and_exclusive_upper_boundary(
    external_filing, db_session, api_client,
):
    fid, _, clerk, _, _ = external_filing
    filing = await db_session.get(FilingEnvelope, fid)
    times = ("2026-11-01T03:59:59Z", "2026-11-01T04:00:00Z",
             "2026-11-02T04:59:59Z", "2026-11-02T05:00:00Z")
    db_session.add_all(activity(fid, clerk, at=datetime.fromisoformat(at)) for at in times)
    await db_session.flush()
    report = (await api_client.get("/api/v1/clerk/payment-register", params={
        "court_id": filing.court_id, "date_from": "2026-11-01", "date_to": "2026-11-01",
        "timezone": "America/Detroit",
    })).json()
    assert report["total"] == 2
    # Local midnight is included and the next local midnight is not: [start, end).
    assert [row["occurred_at"] for row in report["entries"]] == [
        "2026-11-02T04:59:59Z", "2026-11-01T04:00:00Z",
    ]
    assert report["range_start"] == "2026-11-01T04:00:00Z"
    assert report["range_end"] == "2026-11-02T05:00:00Z"  # 25-hour DST day.


@pytest.mark.parametrize("change", [
    {"date_to": "2026-03-07"}, {"date_to": "2026-04-08"}, {"timezone": "../private"},
    {"timezone": "No/Such_Zone"}, {"date_from": "not-a-date"}, {"page": 0},
    {"date_from": "0001-01-01", "date_to": "0001-01-01", "timezone": "Asia/Tokyo"},
])
async def test_invalid_report_filters_are_rejected(external_filing, api_client, db_session, change):
    filing = await db_session.get(FilingEnvelope, external_filing[0])
    response = await api_client.get("/api/v1/clerk/payment-register",
                                    params={"court_id": filing.court_id, **PERIOD, **change})
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("account", ["filer", "unassigned_admin", "inactive"])
async def test_receipt_register_requires_active_court_administration(
    external_filing, api_client, db_session, account,
):
    fid, filer, clerk, other, actor = external_filing
    filing = await db_session.get(FilingEnvelope, fid)
    if account == "filer":
        actor["id"] = filer
    elif account == "unassigned_admin":
        actor["id"] = other
        (await db_session.get(User, other)).user_type = UserType.ADMIN
    else:
        (await db_session.get(User, clerk)).is_active = False
    await db_session.flush()
    for output in ("json", "csv"):
        response = await api_client.get("/api/v1/clerk/payment-register", params={
            "court_id": filing.court_id, **PERIOD, "format": output,
        })
        assert response.status_code == 403, response.text


async def test_csv_exports_the_whole_period_with_signed_cents_and_escaped_text(
    external_filing, api_client, db_session,
):
    fid, _, clerk, _, _ = external_filing
    filing = await db_session.get(FilingEnvelope, fid)
    references = ['=1+2', '+SUM(1)', '-1+2', '@SUM(1)', ' \t=1', '＝1+1', 'SYN,"quoted"\nline']
    db_session.add_all(activity(fid, clerk, reference=ref) for ref in references)
    db_session.add_all(activity(fid, clerk) for _ in range(49))
    db_session.add(activity(fid, clerk, amount=-200))
    await db_session.flush()
    before = await db_session.scalar(select(func.count()).select_from(FilingTransaction))
    params = {"court_id": filing.court_id, **PERIOD, "format": "csv", "page": 9}
    response = await api_client.get("/api/v1/clerk/payment-register", params=params)
    assert response.status_code == 200, response.text
    assert "no-store" in response.headers["cache-control"]
    assert "attachment;" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text.lstrip("\ufeff"))))
    assert len(rows) == 57
    assert sum(int(row["amount_cents"]) for row in rows) == 56 * 400 - 200
    exported = {row["receipt_reference"] for row in rows}
    assert {"'" + ref for ref in references[:6]} <= exported
    assert references[6] in exported
    assert all(row["currency"] == "USD" and row["period_timezone"] == PERIOD["timezone"]
               for row in rows)
    assert await db_session.scalar(select(func.count()).select_from(FilingTransaction)) == before


async def test_oversized_export_is_refused_without_silent_truncation(
    external_filing, api_client, db_session,
):
    fid, _, clerk, _, _ = external_filing
    filing = await db_session.get(FilingEnvelope, fid)
    db_session.add_all(activity(fid, clerk) for _ in range(5000))
    await db_session.flush()
    params = {
        "court_id": filing.court_id, **PERIOD, "format": "csv",
    }
    response = await api_client.get("/api/v1/clerk/payment-register", params=params)
    assert response.status_code == 200, response.text
    assert len(list(csv.DictReader(io.StringIO(response.text.lstrip("\ufeff"))))) == 5000
    db_session.add(activity(fid, clerk))
    await db_session.flush()
    response = await api_client.get("/api/v1/clerk/payment-register", params=params)
    assert response.status_code == 422 and "shorter date range" in response.json()["detail"]
