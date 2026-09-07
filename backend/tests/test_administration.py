"""Identity lifecycle, court delegation, revocation and atomic audit history."""

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.api import auth
from app.config import settings
from app.models.audit import AuditLog
from app.models.court import Court, CourtType
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import audit_service


@pytest_asyncio.fixture
async def administrators(db_session, api_client):
    users = [
        User(
            email=f"identity{i}@example.com",
            first_name="Identity",
            last_name=str(i),
            keycloak_id=f"subject-{i}",
            user_type=kind,
        )
        for i, kind in enumerate(
            [
                UserType.ADMIN,
                UserType.ADMIN,
                UserType.CLERK,
                UserType.CLERK,
                UserType.JUDGE,
                UserType.ATTORNEY,
            ]
        )
    ]
    courts = [
        Court(name=f"Identity Court {i}", county="Wayne", court_type=CourtType.CIRCUIT)
        for i in range(2)
    ]
    db_session.add_all([*users, *courts])
    await db_session.flush()
    db_session.add(UserCourtRole(user_id=users[2].id, court_id=courts[0].id, role=CourtRole.ADMIN))
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(users[0].id)
    return users, courts


def account_payload(user, **changes):
    return {
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "user_type": user.user_type.value,
        "keycloak_id": user.keycloak_id,
        "is_active": user.is_active,
        "bar_number": user.bar_number,
        "bar_number_verified": user.bar_number_verified,
        "expected_version": user.administration_version,
        "reason": "Approved staffing record ADM-42",
        **changes,
    }


async def test_provisioning_binds_subject_without_inventing_verification(
    administrators,
    api_client,
    db_session,
    monkeypatch,
):
    users, _ = administrators
    monkeypatch.setattr(settings, "allow_demo_mode", False)

    async def decode(_token):
        return {"sub": users[0].keycloak_id, "email": users[0].email, "email_verified": True}

    monkeypatch.setattr(auth, "decode_keycloak_access_token", decode)
    api_client.headers["Authorization"] = "Bearer administrator"
    data = {
        "email": "New.Clerk@example.com",
        "first_name": "New",
        "last_name": "Clerk",
        "user_type": "clerk",
        "reason": "Court appointment ADM-42",
    }
    assert (await api_client.post("/api/v1/admin/users", json=data)).status_code == 422
    data["keycloak_id"] = "new-staff-subject"
    response = await api_client.post("/api/v1/admin/users", json=data)
    assert response.status_code == 201
    saved = response.json()
    assert saved["email"] == "new.clerk@example.com" and not saved["email_verified"]
    assert saved["court_roles"] == []
    assert (await api_client.post("/api/v1/admin/users", json=data)).status_code == 409
    data["email"] = "another@example.com"
    assert (await api_client.post("/api/v1/admin/users", json=data)).status_code == 409
    history = (await api_client.get(f"/api/v1/admin/users/{saved['id']}/history")).json()
    assert history["total"] == 1
    event = history["events"][0]
    assert event["details"]["after"]["keycloak_id"] == "new-staff-subject"
    assert event["details"]["before"] is None and event["occurred_at"].endswith("+00:00")
    assert await db_session.scalar(select(func.count()).select_from(User)) == len(users) + 1


async def test_court_administrator_can_only_manage_eligible_staff_in_assigned_court(
    administrators,
    api_client,
):
    users, courts = administrators
    delegated, staff = users[2:4]
    api_client.headers["X-Demo-User-Id"] = str(delegated.id)
    access = (await api_client.get("/api/v1/admin/access")).json()
    assert not access["system_admin"] and [c["id"] for c in access["courts"]] == [courts[0].id]
    assert (await api_client.get("/api/v1/admin/users")).status_code == 403
    assert (await api_client.get(f"/api/v1/admin/users?court_id={courts[1].id}")).status_code == 403
    lookup = (
        await api_client.get(
            "/api/v1/admin/users",
            params={
                "court_id": courts[0].id,
                "email": staff.email,
            },
        )
    ).json()["users"][0]
    assert lookup["id"] == staff.id and "keycloak_id" not in lookup and "bar_number" not in lookup
    assert (
        await api_client.put(f"/api/v1/admin/users/{staff.id}", json=account_payload(staff))
    ).status_code == 403
    role = {"role": "admin", "action": "grant", "expected_version": 0, "reason": "Delegation"}
    path = f"/api/v1/admin/courts/{courts[0].id}/users/{staff.id}/roles"
    assert (await api_client.post(path, json=role)).status_code == 403
    role["role"] = "judge"
    assert (await api_client.post(path, json=role)).status_code == 422
    role["role"] = "clerk"
    assert (
        await api_client.post(
            path.replace(f"courts/{courts[0].id}", f"courts/{courts[1].id}"), json=role
        )
    ).status_code == 403
    assert (await api_client.post(path, json=role)).status_code == 200
    assert (await api_client.get(f"/api/v1/admin/users/{staff.id}/history")).status_code == 403
    history = (
        await api_client.get(
            f"/api/v1/admin/users/{staff.id}/history", params={"court_id": courts[0].id}
        )
    ).json()
    assert history["total"] == 1 and history["events"][0]["details"]["after"] == ["clerk"]


async def test_revoking_court_role_removes_access_on_the_next_request(administrators, api_client):
    users, courts = administrators
    staff, court = users[3], courts[0]
    path = f"/api/v1/admin/courts/{court.id}/users/{staff.id}/roles"
    grant = {"role": "clerk", "action": "grant", "expected_version": 0, "reason": "Assignment"}
    assert (await api_client.post(path, json=grant)).status_code == 200
    api_client.headers["X-Demo-User-Id"] = str(staff.id)
    assert (await api_client.get(f"/api/v1/clerk/queue?court_id={court.id}")).status_code == 200
    api_client.headers["X-Demo-User-Id"] = str(users[2].id)
    assert (
        await api_client.post(path, json={**grant, "action": "revoke", "expected_version": 1})
    ).status_code == 200
    api_client.headers["X-Demo-User-Id"] = str(staff.id)
    assert (await api_client.get(f"/api/v1/clerk/queue?court_id={court.id}")).status_code == 403
    api_client.headers["X-Demo-User-Id"] = str(users[0].id)
    history = (await api_client.get(f"/api/v1/admin/users/{staff.id}/history")).json()
    assert [e["action"] for e in history["events"]] == [
        "identity.role_revoked",
        "identity.role_granted",
    ]


async def test_deactivation_and_rebinding_reject_previously_valid_tokens(
    administrators,
    api_client,
    monkeypatch,
):
    users, _ = administrators
    staff = users[3]
    old_subject = staff.keycloak_id

    async def decode(token):
        return {
            "sub": "replacement-subject" if token == "new" else old_subject,
            "email": staff.email,
            "email_verified": True,
        }

    monkeypatch.setattr(auth, "decode_keycloak_access_token", decode)
    api_client.headers["Authorization"] = "Bearer old"
    assert (await api_client.get("/api/v1/auth/me")).status_code == 200
    api_client.headers.pop("Authorization")
    disabled = await api_client.put(
        f"/api/v1/admin/users/{staff.id}", json=account_payload(staff, is_active=False)
    )
    assert disabled.status_code == 200 and not disabled.json()["email_verified"]
    api_client.headers["Authorization"] = "Bearer old"
    assert (await api_client.get("/api/v1/auth/me")).status_code == 403
    api_client.headers.pop("Authorization")
    assert (
        await api_client.put(
            f"/api/v1/admin/users/{staff.id}",
            json=account_payload(
                staff,
                is_active=True,
                keycloak_id="replacement-subject",
            ),
        )
    ).status_code == 200
    api_client.headers["Authorization"] = "Bearer old"
    assert (await api_client.get("/api/v1/auth/me")).status_code == 401
    api_client.headers["Authorization"] = "Bearer new"
    assert (await api_client.get("/api/v1/auth/me")).status_code == 200


async def test_identity_rebinding_requires_revoking_court_staff_roles(
    administrators,
    api_client,
    db_session,
):
    users, _ = administrators
    court_admin = users[2]
    rebound = await api_client.put(
        f"/api/v1/admin/users/{court_admin.id}",
        json=account_payload(court_admin, keycloak_id="hijacked-subject"),
    )
    assert rebound.status_code == 409
    await db_session.refresh(court_admin)
    assert court_admin.keycloak_id == "subject-2"
    renamed = await api_client.put(
        f"/api/v1/admin/users/{court_admin.id}",
        json=account_payload(court_admin, first_name="Renamed"),
    )
    assert renamed.status_code == 200
    await db_session.refresh(court_admin)
    assert court_admin.first_name == "Renamed" and court_admin.keycloak_id == "subject-2"


async def test_stale_changes_and_audit_failure_cannot_overwrite_an_account(
    administrators,
    api_client,
    db_session,
    monkeypatch,
):
    users, _ = administrators
    staff = users[3]
    payload = account_payload(staff, first_name="Corrected")
    assert (
        await api_client.put(f"/api/v1/admin/users/{staff.id}", json=payload)
    ).status_code == 200
    assert (
        await api_client.put(
            f"/api/v1/admin/users/{staff.id}", json={**payload, "first_name": "Stale"}
        )
    ).status_code == 409

    async def unavailable(*args, **kwargs):
        raise RuntimeError("Audit storage unavailable")

    monkeypatch.setattr(audit_service, "log_action", unavailable)
    with pytest.raises(RuntimeError, match="Audit storage unavailable"):
        await api_client.put(
            f"/api/v1/admin/users/{staff.id}",
            json=account_payload(staff, first_name="Must roll back"),
        )
    await db_session.refresh(staff)
    assert staff.first_name == "Corrected" and staff.administration_version == 1
    assert await db_session.scalar(select(func.count()).select_from(AuditLog)) == 1


async def test_self_changes_and_incompatible_account_types_require_role_review(
    administrators,
    api_client,
):
    users, courts = administrators
    admin, judge = users[0], users[4]
    assert (
        await api_client.put(
            f"/api/v1/admin/users/{admin.id}", json=account_payload(admin, is_active=False)
        )
    ).status_code == 409
    grant = {"role": "judge", "action": "grant", "expected_version": 0, "reason": "Appointment"}
    assert (
        await api_client.post(
            f"/api/v1/admin/courts/{courts[0].id}/users/{judge.id}/roles", json=grant
        )
    ).status_code == 200
    assert (
        await api_client.put(
            f"/api/v1/admin/users/{judge.id}", json=account_payload(judge, user_type="clerk")
        )
    ).status_code == 409
    assert (
        await api_client.post(
            f"/api/v1/admin/courts/{courts[0].id}/users/{admin.id}/roles",
            json={**grant, "role": "admin"},
        )
    ).status_code == 409


@pytest.mark.parametrize("extra", [{"reason": " "}, {"verified_email": "invented@example.com"}])
async def test_identity_changes_require_a_reason_and_cannot_set_verification(
    administrators,
    api_client,
    extra,
):
    users, _ = administrators
    assert (
        await api_client.put(
            f"/api/v1/admin/users/{users[3].id}", json=account_payload(users[3], **extra)
        )
    ).status_code == 422
