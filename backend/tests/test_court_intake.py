from copy import deepcopy
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models.audit import AuditLog
from app.models.court import Court, CourtType
from app.models.user import CourtRole, User, UserCourtRole, UserType
from tests.test_motions_and_search import create_court_with_case


@pytest_asyncio.fixture
async def intake(db_session, api_client):
    filer, administrator, court, case_type, other_type, _case = await create_court_with_case(
        db_session,
    )
    db_session.add(UserCourtRole(user_id=administrator.id, court_id=court.id, role=CourtRole.ADMIN))
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(administrator.id)
    body = {
        "expected_version": 0, "is_efiling_enabled": False,
        "public_notice": "Call the court at the published number for filing arrangements.",
        "case_types": [{"id": item.id, "is_active": True} for item in (case_type, other_type)],
        "reason": "Synthetic internal operations review", "authority_reference": "Synthetic ADM-1",
    }
    return court, filer, administrator, body


async def test_published_closure_is_public_but_its_authority_history_is_private(
    intake, db_session, api_client,
):
    court, filer, administrator, body = intake
    url = f"/api/v1/courts/{court.id}/intake"
    initial = await api_client.get(url)
    assert initial.status_code == 200 and initial.json()["can_manage"]
    published = await api_client.put(url, json=body)
    assert published.status_code == 200, published.text
    assert published.json()["version"] == 1
    assert published.json()["is_efiling_enabled"] is False
    history = await api_client.get(f"{url}/history")
    assert history.status_code == 200
    change = history.json()["changes"][0]
    assert change["before"]["is_efiling_enabled"] is True
    assert change["after"]["is_efiling_enabled"] is False
    assert change["actor_name"] == f"{administrator.first_name} {administrator.last_name}"
    assert change["authority_reference"] == body["authority_reference"]
    assert change["reason"] == body["reason"]
    assert change["after"]["public_notice"] == body["public_notice"]
    api_client.headers.pop("X-Demo-User-Id")
    public = await api_client.get(url)
    assert public.status_code == 200 and public.json()["can_manage"] is False
    assert public.json()["public_notice"] == body["public_notice"]
    assert body["reason"] not in public.text and body["authority_reference"] not in public.text
    assert (await api_client.get(f"{url}/history")).status_code == 401
    api_client.headers["X-Demo-User-Id"] = str(filer.id)
    rejected = await api_client.post("/api/v1/filings", headers={"Idempotency-Key": str(uuid4())},
        json={"court_id": court.id, "case_type_id": body["case_types"][0]["id"],
              "filing_type": "initial", "case_title": "Synthetic filing"})
    assert rejected.status_code == 409
    assert body["public_notice"] in rejected.json()["detail"]
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.action == "court_intake_changed",
    )) == 1


async def test_case_type_closure_leaves_other_types_available(intake, api_client):
    court, filer, _administrator, body = intake
    body["is_efiling_enabled"] = True
    body["case_types"][0]["is_active"] = False
    response = await api_client.put(f"/api/v1/courts/{court.id}/intake", json=body)
    assert response.status_code == 200, response.text
    api_client.headers["X-Demo-User-Id"] = str(filer.id)
    for index, expected in [(0, 409), (1, 201)]:
        response = await api_client.post("/api/v1/filings",
            headers={"Idempotency-Key": str(uuid4())},
            json={"court_id": court.id, "case_type_id": body["case_types"][index]["id"],
                  "filing_type": "initial", "case_title": "Synthetic filing"})
        assert response.status_code == expected, response.text


@pytest.mark.parametrize("actor", ["filer", "clerk", "foreign_admin", "inactive", "anonymous"])
async def test_intake_changes_require_current_administrator_authority(
    intake, api_client, db_session, actor,
):
    court, filer, administrator, body = intake
    if actor == "anonymous":
        api_client.headers.pop("X-Demo-User-Id")
    elif actor == "filer":
        api_client.headers["X-Demo-User-Id"] = str(filer.id)
    elif actor == "inactive":
        administrator.is_active = False
    else:
        user = User(email=f"{actor}@intake.test", first_name="Other", last_name="Staff",
                    user_type=UserType.CLERK)
        db_session.add(user)
        await db_session.flush()
        target_id = court.id
        if actor == "foreign_admin":
            other = Court(name="Other Court", county="Wayne", court_type=CourtType.CIRCUIT)
            db_session.add(other)
            await db_session.flush()
            target_id = other.id
        db_session.add(UserCourtRole(user_id=user.id, court_id=target_id,
                                     role=CourtRole.CLERK if actor == "clerk" else CourtRole.ADMIN))
        api_client.headers["X-Demo-User-Id"] = str(user.id)
    await db_session.flush()
    url = f"/api/v1/courts/{court.id}/intake"
    response = await api_client.put(url, json=body)
    assert response.status_code in (401, 403), response.text
    assert (await api_client.get(f"{url}/history")).status_code in (401, 403)
    assert court.intake_version == 0 and court.is_efiling_enabled


async def test_stale_changes_cannot_overwrite_a_publication_and_noops_create_no_history(
    intake, api_client, db_session,
):
    court, _filer, _administrator, body = intake
    url = f"/api/v1/courts/{court.id}/intake"
    first = await api_client.put(url, json=body)
    assert first.status_code == 200, first.text
    stale = deepcopy(body)
    stale["is_efiling_enabled"] = True
    assert (await api_client.put(url, json=stale)).status_code == 409
    body["expected_version"] = 1
    noop = await api_client.put(url, json=body)
    assert noop.status_code == 200 and noop.json()["version"] == 1
    stale["expected_version"] = 1
    stale["public_notice"] = None
    reopened = await api_client.put(url, json=stale)
    assert reopened.status_code == 200 and reopened.json()["version"] == 2
    assert reopened.json()["is_efiling_enabled"] is True
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.action == "court_intake_changed",
    )) == 2


@pytest.mark.parametrize("invalid", ["notice", "reason", "authority", "duplicate", "unknown_type",
                                    "missing_type", "extra_setting", "string_flag"])
async def test_invalid_publications_have_no_partial_effect(intake, api_client, invalid):
    court, _filer, _administrator, body = intake
    expected = 422
    if invalid == "notice":
        body["public_notice"] = "   "
    elif invalid == "reason":
        body["reason"] = "   "
    elif invalid == "authority":
        body["authority_reference"] = "   "
    elif invalid == "duplicate":
        body["case_types"].append(body["case_types"][0])
    elif invalid == "unknown_type":
        body["case_types"][0]["id"] = 2000000000
        expected = 409
    elif invalid == "missing_type":
        body["case_types"].pop()
        expected = 409
    elif invalid == "extra_setting":
        body["filing_fee_cents"] = 1
    else:
        body["is_efiling_enabled"] = "false"
    response = await api_client.put(f"/api/v1/courts/{court.id}/intake", json=body)
    assert response.status_code == expected, response.text
    assert court.intake_version == 0 and court.is_efiling_enabled
