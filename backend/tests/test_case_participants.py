"""Court-reviewed participation, restricted access, retained history and court scoping."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.api import auth
from app.config import settings
from app.models.audit import AuditLog
from app.models.case import Case, CaseParticipant, ParticipantRole
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import audit_service


@pytest.fixture
async def participants_case(db_session, api_client):
    users = [
        User(
            email=f"participant{i}@example.com",
            first_name="Participant",
            last_name=str(i),
            user_type=kind,
            keycloak_id=f"participant-subject-{i}",
            bar_number="P12345" if kind == UserType.ATTORNEY else None,
            bar_number_verified=kind == UserType.ATTORNEY,
        )
        for i, kind in enumerate(
            [
                UserType.CLERK,
                UserType.CLERK,
                UserType.SELF_REPRESENTED,
                UserType.ATTORNEY,
                UserType.ADMIN,
            ]
        )
    ]
    courts = [
        Court(name=f"Participant Court {i}", county="Wayne", court_type=CourtType.CIRCUIT)
        for i in range(2)
    ]
    db_session.add_all([*users, *courts])
    await db_session.flush()
    types = [
        CaseType(court_id=c.id, code="C", name="Civil", category=CaseCategory.CIVIL) for c in courts
    ]
    db_session.add_all(types)
    await db_session.flush()
    cases = [
        Case(
            court_id=c.id,
            case_type_id=t.id,
            case_number=f"SEALED-{c.id}",
            title="Restricted matter",
            is_sealed=True,
            filed_date=datetime.now(UTC),
        )
        for c, t in zip(courts, types, strict=True)
    ]
    db_session.add_all(cases)
    db_session.add_all(
        [
            UserCourtRole(user_id=users[i].id, court_id=courts[i].id, role=CourtRole.CLERK)
            for i in range(2)
        ]
    )
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(users[0].id)
    return users, cases


async def test_grant_retirement_preserves_own_filing_and_records_authority(
    participants_case,
    api_client,
    db_session,
):
    users, cases = participants_case
    staff, _, party, *_ = users
    case = cases[0]
    path = f"/api/v1/cases/{case.id}/participants"
    own = FilingEnvelope(
        court_id=case.court_id,
        case_type_id=case.case_type_id,
        case_id=case.id,
        filer_id=party.id,
        status=FilingStatus.ACCEPTED,
    )
    db_session.add(own)
    await db_session.flush()
    party_headers = {"X-Demo-User-Id": str(party.id)}
    assert (
        await api_client.get(f"/api/v1/cases/{case.id}", headers=party_headers)
    ).status_code == 403
    data = {
        "party_name": "Named defendant",
        "role": "defendant",
        "account_email": party.email,
        "access_enabled": True,
        "expected_version": 0,
        "reason": "Order 42 reviewed",
    }
    response = await api_client.post(path, json=data)
    assert response.status_code == 201, response.text
    pid = response.json()["id"]
    assert (
        await api_client.get(f"/api/v1/cases/{case.id}", headers=party_headers)
    ).status_code == 200
    listing = (await api_client.get(path)).json()
    assert listing["participant_version"] == 1
    assert listing["participants"][0]["reviewed_at"].endswith("+00:00")
    assert "keycloak_id" not in listing["participants"][0]
    assert (await api_client.put(f"{path}/{pid}", json=data)).status_code == 409
    data.update(
        expected_version=1,
        is_active=False,
        access_enabled=False,
        reason="Court order 43 ends this access",
    )
    assert (await api_client.put(f"{path}/{pid}", json=data)).status_code == 200
    assert (
        await api_client.get(f"/api/v1/cases/{case.id}", headers=party_headers)
    ).status_code == 403
    assert (
        await api_client.get(f"/api/v1/filings/{own.id}", headers=party_headers)
    ).status_code == 200
    history = (await api_client.get(f"{path}/history")).json()
    assert history["total"] == 2
    event = history["events"][0]
    assert event["details"]["before"]["access_enabled"] is True
    assert event["details"]["after"]["access_enabled"] is False
    assert event["details"]["actor_name"] == staff.full_name
    assert event["details"]["reason"] == data["reason"]
    # Re-saving an unchanged reviewed row should not create fake history or version churn.
    data["expected_version"] = 2
    assert (await api_client.put(f"{path}/{pid}", json=data)).status_code == 200
    assert (await api_client.get(f"{path}/history")).json()["total"] == 2
    assert await db_session.scalar(select(func.count()).select_from(CaseParticipant)) == 1


async def test_private_management_requires_this_courts_assignment(participants_case, api_client):
    users, cases = participants_case
    path = f"/api/v1/cases/{cases[0].id}/participants"
    for user in users[1:]:  # Other court, filer, counsel, even an unassigned system admin.
        headers = {"X-Demo-User-Id": str(user.id)}
        for suffix in ["", "/history"]:
            assert (await api_client.get(path + suffix, headers=headers)).status_code == 403
        assert (
            await api_client.post(
                path,
                headers=headers,
                json={
                    "party_name": "Party",
                    "role": "defendant",
                    "expected_version": 0,
                    "reason": "Not authorized at this court",
                },
            )
        ).status_code == 403
    self_change = await api_client.post(
        path,
        json={
            "party_name": "Staff member",
            "role": "defendant",
            "expected_version": 0,
            "account_email": users[0].email,
            "reason": "Self change",
        },
    )
    assert self_change.status_code == 409
    capability = (await api_client.get(f"/api/v1/cases/{cases[0].id}")).json()
    assert capability["can_manage_participants"] is True


@pytest.mark.parametrize(
    "changes",
    [
        {"account_email": None},
        {"account_email": "unknown@example.com"},
        {"is_active": False},
        {"attorney_bar_number": "P99999"},
    ],
)
async def test_counsel_grants_reject_missing_or_conflicting_identity(
    participants_case,
    api_client,
    changes,
):
    users, cases = participants_case
    response = await api_client.post(
        f"/api/v1/cases/{cases[0].id}/participants",
        json={
            "party_name": "Counsel",
            "role": "attorney",
            "account_email": users[3].email,
            "attorney_bar_number": "P12345",
            "represented_party_name": "Intervenor",
            "access_enabled": True,
            "expected_version": 0,
            "reason": "Appearance reviewed",
            **changes,
        },
    )
    assert response.status_code == 422, response.text


async def test_independent_grants_and_public_records_do_not_expose_private_fields(
    participants_case,
    api_client,
    db_session,
):
    users, cases = participants_case
    case, party = cases[0], users[2]
    rows = [
        CaseParticipant(
            case_id=case.id,
            role=role,
            party_name="Named party",
            user_id=party.id,
            access_enabled=True,
            contact_email="private@example.com",
            contact_phone="private",
            contact_address="private",
        )
        for role in [ParticipantRole.DEFENDANT, ParticipantRole.RESPONDENT]
    ]
    db_session.add_all(rows)
    await db_session.flush()
    rows[0].access_enabled = False
    await db_session.flush()
    headers = {"X-Demo-User-Id": str(party.id)}
    response = await api_client.get(f"/api/v1/cases/{case.id}", headers=headers)
    assert response.status_code == 200  # The other grant still applies.
    rows[1].access_enabled = False
    case.is_sealed = False
    await db_session.flush()
    api_client.headers.pop("X-Demo-User-Id")
    response = await api_client.get(f"/api/v1/cases/{case.id}")
    assert response.status_code == 200 and not response.json()["can_manage_participants"]
    public = response.json()["participants"]
    assert {row["id"] for row in public} == {row.id for row in rows}
    assert all(
        not {
            "user_id",
            "account_email",
            "access_enabled",
            "contact_email",
            "contact_phone",
            "contact_address",
        }.intersection(row)
        for row in public
    )


async def test_audit_failure_rolls_back_record_and_version(
    participants_case,
    api_client,
    db_session,
    monkeypatch,
):
    _, cases = participants_case
    case_id = cases[0].id

    async def unavailable(*args, **kwargs):
        raise RuntimeError("Audit store unavailable")

    monkeypatch.setattr(audit_service, "log_action", unavailable)
    with pytest.raises(RuntimeError, match="Audit store unavailable"):
        await api_client.post(
            f"/api/v1/cases/{case_id}/participants",
            json={
                "party_name": "Defendant",
                "role": "defendant",
                "expected_version": 0,
                "reason": "Appearance reviewed",
            },
        )
    assert await db_session.scalar(select(func.count()).select_from(CaseParticipant)) == 0
    assert await db_session.scalar(select(Case.participant_version).where(Case.id == case_id)) == 0
    assert await db_session.scalar(select(func.count()).select_from(AuditLog)) == 0


async def test_court_directory_pages_sealed_cases_without_cross_court_leaks(
    participants_case,
    api_client,
    db_session,
):
    users, cases = participants_case
    template = cases[0]
    extras = [
        Case(
            court_id=template.court_id,
            case_type_id=template.case_type_id,
            case_number=f"BATCH-{i}",
            title=f"Case {i}",
            is_sealed=True,
            filed_date=datetime.now(UTC),
        )
        for i in range(30)
    ]
    db_session.add_all(extras)
    await db_session.flush()
    params = {"court_id": template.court_id}
    first = (await api_client.get("/api/v1/clerk/cases", params=params)).json()
    assert len(first["cases"]) == 25
    second = (
        await api_client.get(
            "/api/v1/clerk/cases",
            params={
                **params,
                "before_id": first["next_before_id"],
            },
        )
    ).json()
    assert len(second["cases"]) == 6 and second["next_before_id"] is None
    assert {row["id"] for row in first["cases"] + second["cases"]} == {
        template.id,
        *(row.id for row in extras),
    }
    found = (
        await api_client.get(
            "/api/v1/clerk/cases",
            params={
                **params,
                "case_number": template.case_number,
            },
        )
    ).json()
    assert [row["id"] for row in found["cases"]] == [template.id]
    assert (
        await api_client.get(
            "/api/v1/clerk/cases",
            params={
                "court_id": cases[1].court_id,
            },
        )
    ).status_code == 403
    api_client.headers["X-Demo-User-Id"] = str(users[2].id)
    assert (await api_client.get("/api/v1/clerk/cases", params=params)).status_code == 403


@pytest.mark.parametrize("state", ["unverified", "inactive", "unbound", "ambiguous"])
async def test_counsel_identity_must_be_current_and_unambiguous(
    participants_case,
    api_client,
    db_session,
    monkeypatch,
    state,
):
    users, cases = participants_case
    clerk, counsel = users[0], users[3]
    if state == "unverified":
        counsel.bar_number_verified = False
    elif state == "inactive":
        counsel.is_active = False
    elif state == "unbound":
        counsel.keycloak_id = None
    else:
        db_session.add(
            User(
                email=counsel.email.upper(),
                first_name="Different",
                last_name="Identity",
                user_type=UserType.ATTORNEY,
            )
        )
    await db_session.flush()

    async def decode(_token):
        return {"sub": clerk.keycloak_id}

    monkeypatch.setattr(settings, "allow_demo_mode", False)
    monkeypatch.setattr(auth, "decode_keycloak_access_token", decode)
    api_client.headers["Authorization"] = "Bearer court-staff"
    path = f"/api/v1/cases/{cases[0].id}/participants"
    response = await api_client.post(
        path,
        json={
            "party_name": "Counsel",
            "role": "attorney",
            "account_email": counsel.email,
            "attorney_bar_number": counsel.bar_number,
            "access_enabled": True,
            "expected_version": 0,
            "reason": "Identity must be reviewed",
        },
    )
    assert response.status_code == 422, response.text
    assert (await api_client.get(path)).json()["participant_version"] == 0
    assert (await api_client.get(f"{path}/history")).json()["total"] == 0


async def test_records_and_history_page_within_the_case(participants_case, api_client, db_session):
    _, cases = participants_case
    for i in range(31):
        for case in cases:
            db_session.add(
                CaseParticipant(
                    case_id=case.id,
                    role=ParticipantRole.DEFENDANT,
                    party_name=f"Case {case.id} participant {i}",
                )
            )
            db_session.add(
                AuditLog(
                    action="case.participant_created",
                    entity_type="case",
                    entity_id=case.id,
                    details={"reason": f"Case {case.id} event {i}"},
                )
            )
    await db_session.flush()
    path = f"/api/v1/cases/{cases[0].id}/participants"
    first, second = [(await api_client.get(path, params={"page": n})).json() for n in [1, 2]]
    assert first["total"] == second["total"] == 31
    assert len(first["participants"]) == 25 and len(second["participants"]) == 6
    assert len({row["id"] for row in first["participants"] + second["participants"]}) == 31
    assert all(
        row["party_name"].startswith(f"Case {cases[0].id} ")
        for row in first["participants"] + second["participants"]
    )
    history = (await api_client.get(f"{path}/history?page=2")).json()
    assert history["total"] == 31 and len(history["events"]) == 6
    assert all(
        row["details"]["reason"].startswith(f"Case {cases[0].id} ") for row in history["events"]
    )
