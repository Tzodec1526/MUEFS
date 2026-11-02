from datetime import UTC, datetime

import pytest

from app.api import auth
from app.config import settings
from app.models.case import Case, CaseStatus
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.utils.keycloak_jwt import IdentityProviderUnavailableError, JWTError


@pytest.fixture
async def accounts(db_session, monkeypatch):
    clerk = User(email="clerk@resolution.example.com", first_name="Court", last_name="Clerk",
                 user_type=UserType.CLERK, keycloak_id="clerk-subject")
    retired = User(email="retired@resolution.example.com", first_name="Retired", last_name="Clerk",
                   user_type=UserType.CLERK, keycloak_id="retired-subject", is_active=False)
    db_session.add_all([clerk, retired])
    court = Court(name="Resolution Court", county="Kent", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()
    case_type = CaseType(court_id=court.id, code="C", name="Civil",
                         category=CaseCategory.CIVIL, filing_fee_cents=0)
    db_session.add(case_type)
    db_session.add_all([
        UserCourtRole(user_id=user.id, court_id=court.id, role=CourtRole.CLERK)
        for user in (clerk, retired)
    ])
    await db_session.flush()
    case = Case(court_id=court.id, case_number="R-1", case_type_id=case_type.id,
                title="Sealed matter", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
                is_sealed=True)
    db_session.add(case)
    await db_session.commit()

    async def decode(token):
        if token == "unavailable":
            raise IdentityProviderUnavailableError("Synthetic outage")
        if token == "invalid":
            raise JWTError("Synthetic invalid token")
        return {"no-subject": {}, "stranger": {"sub": "unknown-subject"}}.get(
            token, {"sub": f"{token}-subject"},
        )

    monkeypatch.setattr(auth, "decode_keycloak_access_token", decode)
    monkeypatch.setattr(settings, "provision_user_on_first_oidc_login", False)
    return {"clerk": clerk.id, "retired": retired.id, "case": case.id}


def _headers(token=None, demo=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if demo is not None:
        headers["X-Demo-User-Id"] = str(demo)
    return headers


@pytest.mark.parametrize(("token", "demo", "status", "detail"), [
    (None, None, 401, "Authentication required"),
    (None, "clerk", 200, "clerk"),
    (None, "retired", 401, "This demo account is unknown or disabled"),
    (None, 999, 401, "This demo account is unknown or disabled"),
    ("invalid", None, 401, "Your sign-in is invalid or has expired"),
    ("invalid", "clerk", 200, "clerk"),
    ("invalid", 999, 401, "This demo account is unknown or disabled"),
    ("no-subject", "clerk", 401, "Your sign-in could not be verified"),
    ("stranger", "clerk", 401, "This account is not set up for this system"),
    ("retired", "clerk", 403, "Account disabled"),
    ("clerk", None, 200, "clerk"),
    ("clerk", "retired", 200, "clerk"),
    ("unavailable", "clerk", 503, "Sign-in verification is temporarily unavailable. "
                                  "Please retry shortly."),
])
async def test_a_signed_in_route_resolves_one_account_or_refuses(
    api_client, accounts, token, demo, status, detail,
):
    response = await api_client.get("/api/v1/auth/me", headers=_headers(
        token, accounts.get(demo, demo),
    ))
    assert response.status_code == status, response.text
    if status == 200:
        assert response.json()["id"] == accounts[detail]
    else:
        assert response.json()["detail"] == detail
    if status == 503:
        assert response.headers["Retry-After"] == "30"


@pytest.mark.parametrize(("token", "demo", "status"), [
    (None, None, 403),
    (None, "clerk", 200),
    (None, "retired", 403),
    (None, 999, 403),
    ("invalid", None, 403),
    ("invalid", "clerk", 200),
    ("no-subject", "clerk", 200),
    ("no-subject", None, 403),
    ("stranger", "clerk", 200),
    ("retired", None, 403),
    ("retired", "clerk", 200),
    ("clerk", None, 200),
    ("unavailable", "clerk", 503),
])
async def test_a_public_route_resolves_an_account_or_answers_anonymously(
    api_client, accounts, token, demo, status,
):
    response = await api_client.get(f"/api/v1/cases/{accounts['case']}", headers=_headers(
        token, accounts.get(demo, demo),
    ))
    assert response.status_code == status, response.text
    if status == 200:
        assert response.json()["can_manage_records"] is True
