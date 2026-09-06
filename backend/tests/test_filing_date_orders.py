"""Court orders change civil dates while preserving receipt and document evidence."""

import hashlib
from datetime import UTC, date

import pytest
from sqlalchemy import func, select

from app.api import filing_dates
from app.config import settings
from app.models.case import Case
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.notification import Notification
from app.models.user import User, UserType
from app.services import audit_service, document_service, filing_service
from app.storage_audit import inspect_receipts
from tests.test_document_publication import prepare_copy, publication_pdf
from tests.test_filing_history import filing_fixture

ORDER = publication_pdf("SYNTHETIC TEST ORDER: filing date September 3, 2026")
DECISION = {
    "filing_date": "2026-09-03",
    "order_signed_date": "2026-09-05",
    "authority_reference": "Synthetic order REF-101, Judge Test",
    "reason": "Relief stated in the signed order",
    "reviewed": "true",
    "expected_version": "1",
}


@pytest.fixture
async def date_record(db_session, api_client, stored_document):
    fid, filer, clerk, other = await filing_fixture(db_session)
    db_session.add(stored_document(fid))
    await db_session.flush()
    await filing_service.submit_filing(db_session, fid)
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    return fid, filer, clerk, other


async def test_order_preserves_receipt_and_acceptance_honors_it_without_calendar(
    date_record,
    db_session,
    api_client,
    monkeypatch,
):
    fid, filer, clerk, _ = date_record
    url = f"/api/v1/clerk/filings/{fid}/filing-date"
    history_url = f"/api/v1/filings/{fid}/history"
    original_receipt = (await api_client.get(history_url)).json()["transactions"][0]
    original_state = (await api_client.get(url)).json()
    assert original_state["submitted_at"].endswith("+00:00")
    result = await api_client.post(url, data=DECISION, files={"file": ("order.pdf", ORDER)})
    assert result.status_code == 201, result.text
    state = (await api_client.get(url)).json()
    assert state["filing_date"] == "2026-09-03" and state["version"] == 2
    assert state["submitted_at"] == original_state["submitted_at"]
    assert state["status"] == "submitted"
    history = (await api_client.get(history_url)).json()["transactions"]
    assert history[-1] == original_receipt
    order_receipt = history[0]
    assert order_receipt["id"] == result.json()["transaction_id"]
    assert (
        order_receipt["details"]["previous_filing_date_basis"]
        == original_state["filing_date_basis"]
    )
    doc = await db_session.get(FilingDocument, state["filing_date_basis"]["order_document_id"])
    assert doc.retained_at is not None and doc.is_confidential
    assert doc.sha256_hash == hashlib.sha256(ORDER).hexdigest()
    assert (
        await api_client.get(
            f"/api/v1/documents/{doc.id}/download",
            headers={
                "X-Demo-User-Id": str(filer),
            },
        )
    ).content == ORDER
    references = [row async for row in inspect_receipts(await db_session.connection())]
    assert len(references) == 2 and all(
        row["status"] == "metadata_consistent" for row in references
    )

    async def no_calendar(*args, **kwargs):
        raise AssertionError("A signed date decision must not be replaced by calendar assessment")

    monkeypatch.setattr(filing_service, "filing_date_for_receipt", no_calendar)
    document_service.upload_document(b"corrupt order", doc.file_key, "application/pdf")
    with pytest.raises(filing_service.FilingDocumentError, match="fingerprint"):
        await filing_service.review_filing(db_session, fid, clerk, "accept")
    document_service.upload_document(ORDER, doc.file_key, "application/pdf")
    # A date order does not bypass the real CMS integration boundary.
    monkeypatch.setattr(settings, "allow_demo_mode", False)
    failed = await filing_service.review_filing(db_session, fid, clerk, "accept")
    assert failed.status == FilingStatus.UNDER_REVIEW and failed.case_id is None
    assert "not configured" in failed.cms_error
    monkeypatch.setattr(settings, "allow_demo_mode", True)
    accepted = await filing_service.review_filing(db_session, fid, clerk, "accept")
    case = await db_session.get(Case, accepted.case_id)
    assert case.filing_date == accepted.filing_date == date(2026, 9, 3)
    assert case.filed_date.replace(tzinfo=UTC) == accepted.submitted_at.replace(tzinfo=UTC)
    assert doc.id not in [attachment.id for attachment in accepted.documents]
    assert (await api_client.get(history_url)).json()["transactions"][-1] == original_receipt


async def test_case_date_is_explicit_and_old_orders_remain_publishable(
    date_record,
    db_session,
    api_client,
):
    fid, filer, clerk, other = date_record
    accepted = await filing_service.review_filing(db_session, fid, clerk, "accept")
    cid = accepted.case_id
    case = await db_session.get(Case, cid)
    old_date, old_instant = case.filing_date, case.filed_date
    url = f"/api/v1/clerk/filings/{fid}/filing-date"
    first = await api_client.post(
        url, data={**DECISION, "expected_version": "2"}, files={"file": ("order.pdf", ORDER)}
    )
    assert first.status_code == 201, first.text
    assert case.filing_date == old_date and case.filed_date == old_instant
    state = (await api_client.get(url)).json()
    first_doc = state["filing_date_basis"]["order_document_id"]
    decision = {
        **DECISION,
        "expected_version": "3",
        "update_case_date": "true",
        "filing_date": "2026-09-02",
        "expected_case_version": "1",
    }
    stale = await api_client.post(url, data=decision, files={"file": ("order.pdf", ORDER)})
    assert stale.status_code == 409 and "case opening date changed" in stale.text
    assert (await api_client.get(url)).json() == state
    decision["expected_case_version"] = "0"
    second = await api_client.post(url, data=decision, files={"file": ("order.pdf", ORDER)})
    assert second.status_code == 201, second.text
    await db_session.refresh(case)
    assert case.filing_date == date(2026, 9, 2) and case.filed_date == old_instant
    assert case.filing_date_version == 1
    history = (await api_client.get(f"/api/v1/filings/{fid}/history")).json()["transactions"]
    assert history[0]["details"]["case_date_change"]["case_id"] == cid
    assert history[0]["details"]["previous_filing_date"] == "2026-09-03"
    assert len([event for event in history if event["event_type"] == "filing_date_ordered"]) == 2
    docket_url = f"/api/v1/cases/{cid}/filings"
    outsider = {"X-Demo-User-Id": str(other)}
    assert all(
        doc["id"] != first_doc
        for doc in (
            await api_client.get(
                docket_url,
                headers=outsider,
            )
        ).json()[0]["documents"]
    )
    copy, payload = await prepare_copy(api_client, first_doc)
    assert (
        await api_client.post(
            f"/api/v1/clerk/documents/{first_doc}/publication",
            json={
                "copy_id": copy["id"],
                "expected_version": 0,
                "reviewed": True,
                "reason": "Court-reviewed release of the earlier signed order",
            },
        )
    ).status_code == 200
    docket = (await api_client.get(docket_url, headers=outsider)).json()[0]
    public = next(doc for doc in docket["documents"] if doc["id"] == first_doc)
    assert public["copy_id"] == copy["id"] and public["title"] == copy["title"]
    assert docket["filing_date"] == "2026-09-02"
    assert (
        await api_client.get(f"/api/v1/documents/{first_doc}/download", headers=outsider)
    ).status_code == 403
    assert (
        await api_client.get(
            f"/api/v1/document-public-copies/{copy['id']}/download", headers=outsider
        )
    ).content == payload
    assert (
        await api_client.get(
            f"/api/v1/documents/{first_doc}/download",
            headers={
                "X-Demo-User-Id": str(filer),
            },
        )
    ).content == ORDER


async def test_return_and_resubmission_reset_date_without_rewriting_prior_order(
    date_record,
    db_session,
    api_client,
):
    fid, filer, clerk, _ = date_record
    url = f"/api/v1/clerk/filings/{fid}/filing-date"
    assert (
        await api_client.post(url, data=DECISION, files={"file": ("order.pdf", ORDER)})
    ).status_code == 201
    old_state = (await api_client.get(url)).json()
    did = old_state["filing_date_basis"]["order_document_id"]
    await filing_service.review_filing(db_session, fid, clerk, "return", "Correct attachment")
    owner = {"X-Demo-User-Id": str(filer)}
    assert (
        await api_client.delete(f"/api/v1/filings/{fid}/documents/{did}", headers=owner)
    ).status_code == 404
    for code in ("FILING_DATE_ORDER", "FEE_WAIVER_ORDER"):
        assert (
            await api_client.post(
                f"/api/v1/filings/{fid}/documents",
                headers=owner,
                data={"title": "Reserved court document", "document_type_code": code},
                files={"file": ("order.pdf", ORDER)},
            )
        ).status_code == 403
    await filing_service.submit_filing(db_session, fid)
    state = (await api_client.get(url)).json()
    assert state["submission_count"] == 2 and state["version"] == 4
    assert state["filing_date_basis"].get("source") != "court_order"
    assert (
        await api_client.post(
            url,
            data={**DECISION, "expected_version": "2"},
            files={"file": ("order.pdf", ORDER)},
        )
    ).status_code == 409
    history = (await api_client.get(f"/api/v1/filings/{fid}/history")).json()["transactions"]
    assert did not in [doc["id"] for doc in history[0]["details"]["documents"]]
    order_event = next(event for event in history if event["event_type"] == "filing_date_ordered")
    assert order_event["submission_number"] == 1
    assert order_event["details"]["filing_date_basis"] == old_state["filing_date_basis"]


async def test_authority_and_validation_block_unreviewed_or_unreceived_orders(
    date_record,
    db_session,
    api_client,
    tmp_path,
):
    fid, filer, clerk, other = date_record
    url = f"/api/v1/clerk/filings/{fid}/filing-date"
    admin = User(
        email="date-admin@test.com",
        first_name="System",
        last_name="Admin",
        user_type=UserType.ADMIN,
    )
    db_session.add(admin)
    await db_session.flush()
    for actor in (filer, other, admin.id):
        headers = {"X-Demo-User-Id": str(actor)}
        assert (await api_client.get(url, headers=headers)).status_code == 403
        assert (
            await api_client.post(
                url,
                headers=headers,
                data=DECISION,
                files={"file": ("order.pdf", ORDER)},
            )
        ).status_code == 403
    for patch in (
        {"reviewed": "false"},
        {"authority_reference": " "},
        {"reason": " "},
        {"filing_date": "invalid"},
        {"update_case_date": "true"},
    ):
        assert (
            await api_client.post(
                url,
                data={**DECISION, **patch},
                files={"file": ("order.pdf", ORDER)},
            )
        ).status_code == 422
    assert (await api_client.post(url, data=DECISION)).status_code == 422
    assert (
        await api_client.post(
            url,
            data=DECISION,
            files={"file": ("not-an-order.txt", b"This is not a PDF", "text/plain")},
        )
    ).status_code == 415
    filing = await db_session.get(FilingEnvelope, fid)
    for status in (FilingStatus.DRAFT, FilingStatus.SERVED):
        filing.status = status
        await db_session.flush()
        assert (await api_client.get(url)).json()["order_block"]
        assert (
            await api_client.post(
                url,
                data=DECISION,
                files={"file": ("order.pdf", ORDER)},
            )
        ).status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(FilingDocument)) == 1
    assert len(list(tmp_path.rglob("*.txt"))) == 1
    assert not list(tmp_path.rglob("*.pdf"))


async def test_audit_failure_rolls_back_case_filing_order_and_notice(
    date_record,
    db_session,
    api_client,
    monkeypatch,
    tmp_path,
):
    fid, _, clerk, _ = date_record
    await filing_service.review_filing(db_session, fid, clerk, "accept")
    url = f"/api/v1/clerk/filings/{fid}/filing-date"
    before = (await api_client.get(url)).json()
    count = await db_session.scalar(select(func.count()).select_from(Notification))

    async def fail_audit(*args, **kwargs):
        raise RuntimeError("Audit store unavailable")

    monkeypatch.setattr(audit_service, "log_action", fail_audit)
    with pytest.raises(RuntimeError, match="Audit store unavailable"):
        await api_client.post(
            url,
            data={
                **DECISION,
                "expected_version": "2",
                "update_case_date": "true",
                "expected_case_version": "0",
            },
            files={"file": ("order.pdf", ORDER)},
        )
    assert (await api_client.get(url)).json() == before
    assert await db_session.scalar(select(func.count()).select_from(Notification)) == count
    assert await db_session.scalar(select(func.count()).select_from(FilingDocument)) == 1
    assert not list(tmp_path.rglob("*.pdf"))


async def test_authority_rechecked_after_pdf_inspection_and_legacy_receipt_not_invented(
    date_record,
    db_session,
    api_client,
    monkeypatch,
):
    fid, _, clerk, _ = date_record
    filing = await db_session.get(FilingEnvelope, fid)
    filing.status = FilingStatus.ACCEPTED
    filing.submission_count = 0
    filing.submitted_at = None
    await db_session.flush()
    url = f"/api/v1/clerk/filings/{fid}/filing-date"
    inspect = filing_dates.inspect_upload

    async def revoke_during_inspection(*args, **kwargs):
        result = await inspect(*args, **kwargs)
        actor = await db_session.get(User, clerk)
        actor.is_active = False
        await db_session.flush()
        return result

    monkeypatch.setattr(filing_dates, "inspect_upload", revoke_during_inspection)
    denied = await api_client.post(url, data=DECISION, files={"file": ("order.pdf", ORDER)})
    assert denied.status_code == 403
    assert await db_session.scalar(select(func.count()).select_from(FilingDocument)) == 1
    actor = await db_session.get(User, clerk)
    actor.is_active = True
    await db_session.flush()
    monkeypatch.setattr(filing_dates, "inspect_upload", inspect)
    recorded = await api_client.post(url, data=DECISION, files={"file": ("order.pdf", ORDER)})
    assert recorded.status_code == 201, recorded.text
    state = (await api_client.get(url)).json()
    assert state["submitted_at"] is None and state["submission_count"] == 0
    order = await db_session.get(FilingTransaction, recorded.json()["transaction_id"])
    assert order.submission_number == 0
    assert "legacy filing" in order.details["documents"][0]["title"]
