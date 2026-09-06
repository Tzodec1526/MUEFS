"""Service instructions require court authority, current identity and retained history."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.models.audit import AuditLog
from app.models.case import CaseParticipant, ParticipantRole
from app.models.notification import Notification, ServiceContact
from tests.test_case_participants import participants_case as participants_case
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions


@pytest.fixture
async def service_case(participants_case, db_session):
    users, cases = participants_case
    party = users[2]
    party.verified_email = party.email
    participant = CaseParticipant(
        case_id=cases[0].id,
        user_id=party.id,
        party_name="Service recipient",
        role=ParticipantRole.DEFENDANT,
        is_active=True,
        access_enabled=True,
        reviewed_at=datetime.now(UTC),
    )
    db_session.add(participant)
    await db_session.flush()
    path = f"/api/v1/cases/{cases[0].id}/participants/{participant.id}/service-contact"
    data = {
        "method": "electronic",
        "email": party.email,
        "authority": "Registration 14 reviewed",
        "reason": "Record court-reviewed destination",
        "expected_version": 0,
        "expected_participant_version": 0,
    }
    return users, cases, participant, path, data


async def test_electronic_change_and_revocation_preserve_history_and_send_nothing(
    service_case,
    api_client,
    db_session,
):
    users, cases, participant, path, data = service_case
    response = await api_client.put(path, json=data)
    assert response.status_code == 200, response.text
    saved = (await api_client.get(path)).json()
    assert saved["court_id"] == cases[0].court_id
    assert saved["contact"]["version"] == 1
    assert saved["contact"]["participant_snapshot"]["user_id"] == users[2].id
    assert saved["issues"] == []
    assert (await api_client.put(path, json=data)).status_code == 409
    data["expected_version"] = 1
    # An unchanged save does not fabricate another review or retained event.
    assert (await api_client.put(path, json=data)).json()["version"] == 1
    users[2].email = "changed@example.com"
    await db_session.flush()
    changed = (await api_client.get(path)).json()
    assert "verified email" in " ".join(changed["issues"])
    assert (await api_client.put(path, json=data)).status_code == 422
    # A broken address must not prevent staff from deactivating the instructions.
    data.update(is_active=False, reason="Address changed; recipient must update registration")
    response = await api_client.put(path, json=data)
    assert response.status_code == 200, response.text
    history = (await api_client.get(f"{path}/history")).json()
    assert history["total"] == 2
    change = history["events"][0]
    assert change["details"]["before"]["email"] == "participant2@example.com"
    assert change["details"]["before"]["is_active"] is True
    assert change["details"]["after"]["is_active"] is False
    assert change["details"]["actor_name"] == users[0].full_name
    assert change["occurred_at"].endswith("+00:00")
    assert participant.access_enabled  # Service instructions never grant or revoke case access.
    assert await db_session.scalar(select(func.count()).select_from(Notification)) == 0


@pytest.mark.parametrize(
    "change",
    [
        "unverified",
        "no_account",
        "inactive_account",
        "inactive_participant",
        "unreviewed_participant",
        "restricted_access",
        "counsel_identity",
        "wrong_address",
        "foreign_participant",
        "unassigned_staff",
        "admin",
        "self",
        "stale_participant",
        "empty_authority",
        "oversize_case_id",
        "oversize_participant_id",
    ],
)
async def test_invalid_service_instructions_cannot_become_active(
    service_case,
    api_client,
    db_session,
    change,
):
    users, cases, participant, path, data = service_case
    expected = 422
    if change == "unverified":
        users[2].verified_email = None
    elif change == "no_account":
        participant.user_id = None
    elif change == "inactive_account":
        users[2].is_active = False
    elif change == "inactive_participant":
        participant.is_active = False
    elif change == "unreviewed_participant":
        participant.reviewed_at = None
    elif change == "restricted_access":
        participant.access_enabled = False
    elif change == "counsel_identity":
        participant.role = ParticipantRole.ATTORNEY
        participant.attorney_bar_number = users[3].bar_number
    elif change == "wrong_address":
        data["email"] = "unverified-other@example.com"
    elif change == "foreign_participant":
        participant.case_id = cases[1].id
        expected = 404
    elif change in ("unassigned_staff", "admin"):
        api_client.headers["X-Demo-User-Id"] = str(
            users[1 if change == "unassigned_staff" else 4].id
        )
        expected = 403
    elif change == "self":
        participant.user_id = users[0].id
        expected = 409
    elif change == "stale_participant":
        cases[0].participant_version = 1
        expected = 409
    elif change == "oversize_case_id":
        path = path.replace(f"/cases/{cases[0].id}/", "/cases/2147483648/")
    elif change == "oversize_participant_id":
        path = path.replace(f"/participants/{participant.id}/", "/participants/2147483648/")
    else:
        data["authority"] = "  "
    await db_session.flush()
    response = await api_client.put(path, json=data)
    assert response.status_code == expected, response.text
    assert await db_session.scalar(select(func.count()).select_from(ServiceContact)) == 0
    assert not await db_session.scalar(
        select(AuditLog.id).where(
            AuditLog.action == "case.service_contact_changed",
        )
    )


@pytest.mark.parametrize("method", ["mail", "hand_delivery"])
async def test_non_electronic_instructions_support_unregistered_parties_and_stay_private(
    service_case,
    api_client,
    db_session,
    method,
):
    users, _cases, participant, path, data = service_case
    participant.user_id, participant.access_enabled = None, False
    data.update(
        method=method,
        email=None,
        address="123 Synthetic Street, Lansing MI 48933",
        authority="Reviewed exemption and address notice 15",
    )
    await db_session.flush()
    response = await api_client.put(path, json=data)
    assert response.status_code == 200, response.text
    current = (await api_client.get(path)).json()
    assert current["issues"] == []
    assert current["contact"]["address"] == data["address"]
    for user in [users[1], users[2], users[4]]:
        for target in [path, f"{path}/history"]:
            assert (
                await api_client.get(
                    target,
                    headers={
                        "X-Demo-User-Id": str(user.id),
                    },
                )
            ).status_code == 403
    participant.party_name = "Reassigned participant"
    await db_session.flush()
    current = (await api_client.get(path)).json()
    assert "participant record changed" in " ".join(current["issues"]).lower()
    assert current["contact"]["name"] == "Service recipient"


async def test_service_history_is_scoped_and_paginated(service_case, api_client, db_session):
    users, cases, participant, path, data = service_case
    assert (await api_client.put(path, json=data)).status_code == 200
    for index in range(26):
        data.update(expected_version=index + 1, authority=f"Registration revision {index}")
        assert (await api_client.put(path, json=data)).status_code == 200
    first = (await api_client.get(f"{path}/history")).json()
    second = (await api_client.get(f"{path}/history?page=2")).json()
    assert first["total"] == second["total"] == 27
    assert len(first["events"]) == 25 and len(second["events"]) == 2
    assert not {row["id"] for row in first["events"]} & {row["id"] for row in second["events"]}
    assert (
        await api_client.get(
            path.replace(f"/{participant.id}/service-contact", "/999999/service-contact")
            + "/history"
        )
    ).json()["total"] == 0


@pytest.mark.skipif(not os.getenv("MUEFS_TEST_POSTGRES_URL"), reason="PostgreSQL not configured")
@pytest.mark.parametrize("postgres_sessions", ["d4e7a12b93f0"], indirect=True)
async def test_legacy_upgrade_and_simultaneous_court_edits(postgres_sessions):
    from alembic.config import Config
    from httpx import ASGITransport, AsyncClient

    from alembic import command
    from app.database import get_db
    from app.main import app
    from app.models.case import Case
    from app.models.court import CaseCategory, CaseType
    from app.models.user import CourtRole, User, UserCourtRole, UserType

    async with postgres_sessions.begin() as db:
        party = User(
            email="service-party@example.com", first_name="Service", last_name="Recipient",
            user_type=UserType.ATTORNEY, bar_number="P77777", bar_number_verified=True,
            verified_email="service-party@example.com", keycloak_id="synthetic-service-recipient",
        )
        clerk = User(email="first-service-clerk@example.com", first_name="First", last_name="Clerk",
                     user_type=UserType.CLERK)
        second = User(
            email="second-service-clerk@example.com",
            first_name="Second",
            last_name="Clerk",
            user_type=UserType.CLERK,
        )
        db.add_all([party, clerk, second])
        await db.flush()
        # Seed only columns present in the legacy schema being upgraded.
        court_id = await db.scalar(text(
            "INSERT INTO courts (name, county, court_type, state, is_efiling_enabled) "
            "VALUES ('Service Court', 'Wayne', 'CIRCUIT', 'MI', true) RETURNING id"
        ))
        kind = CaseType(court_id=court_id, code="CIV", name="Civil", category=CaseCategory.CIVIL)
        db.add(kind)
        await db.flush()
        case = Case(court_id=court_id, case_type_id=kind.id, case_number="SERVICE-CASE-1",
                    title="Synthetic service matter", filed_date=datetime.now(UTC))
        db.add(case)
        await db.flush()
        db.add_all(
            [
                UserCourtRole(user_id=actor.id, court_id=court_id, role=CourtRole.CLERK)
                for actor in [clerk, second]
            ]
        )
        participant = CaseParticipant(
            case_id=case.id, user_id=party.id, role=ParticipantRole.ATTORNEY_PLAINTIFF,
            party_name="Service Recipient", attorney_bar_number=party.bar_number,
            reviewed_at=datetime.now(UTC),
        )
        db.add(participant)
        await db.flush()
        await db.execute(
            text("""INSERT INTO service_contacts (case_id, user_id, name, email, method)
            VALUES (:case, :user, 'Legacy contact', 'old-service@example.com', 'ELECTRONIC')"""),
            {"case": case.id, "user": party.id},
        )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    async with postgres_sessions.kw["bind"].connect() as conn:

        def migrate(connection):
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        await conn.run_sync(migrate)
    async with postgres_sessions() as db:
        legacy = await db.scalar(select(ServiceContact))
        assert legacy.email == "old-service@example.com"
        assert legacy.participant_id is None and not legacy.is_active
        assert legacy.version == 0 and legacy.reviewed_at is None

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    path = f"/api/v1/cases/{case.id}/participants/{participant.id}/service-contact"
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            # Different staff accounts contend for both first creation and a later edit.
            for version in [0, 1]:
                results = await asyncio.wait_for(
                    asyncio.gather(
                        *[
                            client.put(
                                path,
                                headers={"X-Demo-User-Id": str(actor.id)},
                                json={
                                    "method": "electronic",
                                    "email": party.email,
                                    "authority": f"Reviewed by {actor.id} revision {version}",
                                    "reason": "Court registration reviewed",
                                    "expected_version": version,
                                    "expected_participant_version": 0,
                                },
                            )
                            for actor in [clerk, second]
                        ]
                    ),
                    10,
                )
                assert sorted(response.status_code for response in results) == [200, 409]
            history = await client.get(
                f"{path}/history",
                headers={
                    "X-Demo-User-Id": str(clerk.id),
                },
            )
            assert history.json()["total"] == 2
        async with postgres_sessions() as db:
            current = await db.scalar(
                select(ServiceContact).where(
                    ServiceContact.participant_id == participant.id,
                )
            )
            assert current.version == 2
            assert await db.scalar(select(func.count()).select_from(ServiceContact)) == 2
    finally:
        app.dependency_overrides.pop(get_db, None)
