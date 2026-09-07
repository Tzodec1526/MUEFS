"""A stale editor must not replace another tab's saved filing details."""

import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.main import app
from app.models.filing import FilingEnvelope, FilingStatus
from tests.test_document_http import filing_client as filing_client
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions
from tests.test_filing_history import filing_fixture


async def test_stale_editor_preserves_newer_details(filing_client):
    client, envelope, _ = filing_client
    client.headers["X-Demo-User-Id"] = str(envelope.filer_id)
    url = f"/api/v1/filings/{envelope.id}"
    opened = await client.get(url)
    assert opened.status_code == 200, opened.text
    original = opened.json()
    token = original["details_token"]
    saved = await client.patch(url, json={
        "expected_details_token": token,
        "case_title": "Saved from the first tab",
        "filing_description": "First tab's reviewed description",
    })
    assert saved.status_code == 200, saved.text
    stale = await client.patch(url, json={
        "expected_details_token": token,
        "case_title": "Unsaved second-tab title",
        "filing_description": "Older second-tab description",
    })
    assert stale.status_code == 409, stale.text
    current = (await client.get(url)).json()
    assert current["case_title"] == "Saved from the first tab"
    assert current["filing_description"] == "First tab's reviewed description"


@pytest.mark.parametrize("token", [None, "", "malformed"])
async def test_details_edit_requires_a_valid_opened_version(filing_client, token):
    client, envelope, _ = filing_client
    payload = {"case_title": "Must not be saved"}
    if token is not None:
        payload["expected_details_token"] = token
    response = await client.patch(f"/api/v1/filings/{envelope.id}", json=payload)
    assert response.status_code == 422
    assert envelope.case_title == "A v B"


async def test_fee_waiver_edits_require_opened_details_token(
    filing_client, db_session,
):
    client, envelope, _ = filing_client
    client.headers["X-Demo-User-Id"] = str(envelope.filer_id)
    url = f"/api/v1/filings/{envelope.id}"
    first = (await client.get(url)).json()
    missing = await client.patch(url, json={"fee_waiver_requested": True})
    assert missing.status_code == 422
    fees = await client.patch(url, json={
        "expected_details_token": first["details_token"],
        "fee_waiver_requested": True,
    })
    assert fees.status_code == 200, fees.text
    assert fees.json()["details_token"] != first["details_token"]
    stale = await client.patch(url, json={
        "expected_details_token": first["details_token"],
        "fee_waiver_requested": False,
    })
    assert stale.status_code == 409
    saved = await client.patch(url, json={
        "expected_details_token": fees.json()["details_token"],
        "case_title": first["case_title"], "filing_description": "",
    })
    assert saved.status_code == 200, saved.text
    unchanged = await client.patch(url, json={
        "expected_details_token": saved.json()["details_token"], "filing_description": "",
    })
    assert unchanged.json()["details_token"] == saved.json()["details_token"]
    envelope.status = FilingStatus.RETURNED
    envelope.submission_count = 1
    await db_session.flush()
    returned = (await client.get(url)).json()
    envelope.submission_count = 2
    await db_session.flush()
    stale_cycle = await client.patch(url, json={
        "expected_details_token": returned["details_token"], "case_title": "Earlier correction",
    })
    assert stale_cycle.status_code == 409
    assert envelope.case_title == first["case_title"]


@pytest.mark.skipif(not os.getenv("MUEFS_TEST_POSTGRES_URL"), reason="PostgreSQL not configured")
async def test_concurrent_editors_cannot_both_replace_the_same_saved_version(postgres_sessions):
    async with postgres_sessions.begin() as db:
        filing_id, filer, _clerk, _other = await filing_fixture(db)
        filing = await db.get(FilingEnvelope, filing_id)
        filing.status = FilingStatus.DRAFT
        await db.flush()
        token = filing.details_token

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                               headers={"X-Demo-User-Id": str(filer)}) as client:
            url = f"/api/v1/filings/{filing_id}"
            responses = await asyncio.gather(*[
                client.patch(url, json={
                    "expected_details_token": token, "case_title": title,
                    "filing_description": f"Description for {title}",
                }) for title in ("First editor", "Second editor")
            ])
            assert sorted(response.status_code for response in responses) == [200, 409]
            winner = next(response.json() for response in responses if response.status_code == 200)
            current = (await client.get(url)).json()
            assert current["case_title"] == winner["case_title"]
            assert current["filing_description"] == winner["filing_description"]
    finally:
        app.dependency_overrides.pop(get_db, None)
