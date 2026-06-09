"""Provision internal User rows from OIDC token claims on first login.

Court deployments typically disable auto-provision (provision_user_on_first_oidc_login=false)
and use admin invite, SCIM, or batch import instead.

Security: auto-provisioning trusts the IdP's email claim to locate or create an account, so
it only acts on a *verified* email (the ``email_verified`` claim) and refuses to silently
adopt a pre-existing privileged account (admin / clerk / judge, or any account carrying a
bar number). Those must be bound to an OIDC subject explicitly by an administrator.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserType

logger = logging.getLogger(__name__)

# Account kinds that must never be auto-linked to an OIDC subject by a first-login email
# match. Binding these requires explicit admin provisioning of keycloak_id. The exclusion
# is deliberately limited to elevated/bar-holding accounts; low-privilege SELF_REPRESENTED
# and PUBLIC accounts may still be adopted by a verified-email first login (no escalation).
_PRIVILEGED_USER_TYPES = frozenset({UserType.ADMIN, UserType.CLERK, UserType.JUDGE})


def _email_is_verified(claims: dict) -> bool:
    """True only if the IdP asserts the email is verified (boolean True or the string "true")."""
    value = claims.get("email_verified")
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def _is_privileged_account(user: User) -> bool:
    # A bar number grants counsel-of-record access to sealed cases, so bar-holding
    # accounts are sensitive too — never auto-adopt them by email match.
    return user.user_type in _PRIVILEGED_USER_TYPES or bool(user.bar_number)


async def provision_user_from_oidc(
    db: AsyncSession,
    *,
    sub: str,
    claims: dict,
) -> User | None:
    """Create or link a User for this Keycloak subject.

    Returns None if provisioning is impossible or disallowed (missing/unverified email,
    an email already bound to a different subject, or an attempt to auto-adopt a
    privileged pre-existing account).
    """
    email = claims.get("email")
    if not email or not isinstance(email, str):
        logger.warning("OIDC token missing email claim; cannot auto-provision user sub=%s", sub)
        return None

    if not _email_is_verified(claims):
        logger.warning(
            "OIDC token email not verified; refusing to auto-provision/link sub=%s", sub
        )
        return None

    email = email.strip().lower()
    first = (claims.get("given_name") or claims.get("first_name") or "").strip() or "User"
    last = (claims.get("family_name") or claims.get("last_name") or "").strip() or "Name"

    # Link existing row that matched email before OIDC was attached (e.g. migrated demo account)
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()
    if existing:
        if existing.keycloak_id and existing.keycloak_id != sub:
            logger.warning("Email %s already bound to another OIDC subject", email)
            return None
        if not existing.keycloak_id:
            # Never let a first-login email match silently take over a privileged account.
            if _is_privileged_account(existing):
                logger.warning(
                    "Refusing to auto-link OIDC sub=%s to privileged account %s; "
                    "an administrator must bind keycloak_id explicitly",
                    sub,
                    email,
                )
                return None
            existing.keycloak_id = sub
            await db.flush()
            await db.refresh(existing)
            return existing
        return existing

    user = User(
        email=email,
        first_name=first[:100],
        last_name=last[:100],
        user_type=UserType.SELF_REPRESENTED,
        keycloak_id=sub,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    logger.info("Provisioned user id=%s from OIDC sub=%s", user.id, sub)
    return user
