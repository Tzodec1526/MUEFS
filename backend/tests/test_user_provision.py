"""OIDC user provisioning on first login."""

import pytest

from app.models.user import User, UserType
from app.services.user_provision_service import provision_user_from_oidc


@pytest.mark.asyncio
async def test_provision_creates_user_from_claims(db_session):
    user = await provision_user_from_oidc(
        db_session,
        sub="oidc-subject-99",
        claims={
            "email": "newuser@example.com",
            "email_verified": True,
            "given_name": "N",
            "family_name": "User",
        },
    )
    assert user is not None
    assert user.keycloak_id == "oidc-subject-99"
    assert user.email == "newuser@example.com"
    assert user.user_type == UserType.SELF_REPRESENTED


@pytest.mark.asyncio
async def test_provision_requires_email(db_session):
    assert await provision_user_from_oidc(
        db_session,
        sub="no-email",
        claims={"given_name": "X", "email_verified": True},
    ) is None


@pytest.mark.asyncio
async def test_provision_requires_verified_email(db_session):
    """An unverified or missing email_verified claim must not auto-provision or link."""
    assert await provision_user_from_oidc(
        db_session,
        sub="unverified-sub",
        claims={"email": "unverified@example.com", "email_verified": False},
    ) is None
    assert await provision_user_from_oidc(
        db_session,
        sub="missing-flag-sub",
        claims={"email": "noflag@example.com"},
    ) is None


@pytest.mark.asyncio
async def test_provision_refuses_privileged_account_autolink(db_session):
    """A first-login email match must not silently adopt a privileged (admin) account."""
    admin = User(
        email="admin@court.gov", first_name="A", last_name="dmin",
        user_type=UserType.ADMIN,
    )
    db_session.add(admin)
    await db_session.flush()

    linked = await provision_user_from_oidc(
        db_session,
        sub="attacker-sub",
        claims={"email": "admin@court.gov", "email_verified": True},
    )
    assert linked is None
    await db_session.refresh(admin)
    assert admin.keycloak_id is None


@pytest.mark.asyncio
async def test_provision_refuses_bar_account_autolink(db_session):
    """A bar-holding account is sensitive for sealed-case access; no email auto-link."""
    attorney = User(
        email="counsel@firm.com", first_name="C", last_name="ounsel",
        user_type=UserType.ATTORNEY, bar_number="P12345", bar_number_verified=True,
    )
    db_session.add(attorney)
    await db_session.flush()

    linked = await provision_user_from_oidc(
        db_session,
        sub="attacker-sub-2",
        claims={"email": "counsel@firm.com", "email_verified": True},
    )
    assert linked is None
    await db_session.refresh(attorney)
    assert attorney.keycloak_id is None
