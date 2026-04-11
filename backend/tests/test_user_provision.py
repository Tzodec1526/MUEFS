"""OIDC user provisioning on first login."""

import pytest

from app.models.user import UserType
from app.services.user_provision_service import provision_user_from_oidc


@pytest.mark.asyncio
async def test_provision_creates_user_from_claims(db_session):
    user = await provision_user_from_oidc(
        db_session,
        sub="oidc-subject-99",
        claims={
            "email": "newuser@example.com",
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
        claims={"given_name": "X"},
    ) is None
