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

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserType

logger = logging.getLogger(__name__)


def verified_email_from_claims(claims: dict) -> str | None:
    value = claims.get("email_verified")
    if not (value is True or isinstance(value, str) and value.strip().lower() == "true"):
        return None
    email = claims.get("email")
    if not isinstance(email, str):
        return None
    try:
        return validate_email(
            email.strip(), check_deliverability=False, allow_smtputf8=False
        ).normalized.lower()
    except EmailNotValidError:
        return None


def sync_verified_email(user: User, claims: dict) -> None:
    email = verified_email_from_claims(claims)
    user.verified_email = email if email == user.email.strip().lower() else None


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
    email = verified_email_from_claims(claims)
    if email is None:
        logger.warning("OIDC token email not verified; refusing to auto-provision/link sub=%s", sub)
        return None

    first = (claims.get("given_name") or claims.get("first_name") or "").strip() or "User"
    last = (claims.get("family_name") or claims.get("last_name") or "").strip() or "Name"

    # Link existing row that matched email before OIDC was attached (e.g. migrated demo account).
    # Stored addresses keep their original case; legacy case variants are ambiguous.
    matches = (await db.scalars(
        select(User).where(func.lower(User.email) == email).limit(2)
    )).all()
    if len(matches) > 1:
        logger.warning("Email %s matches several accounts; refusing to auto-provision", email)
        return None
    existing = matches[0] if matches else None
    if existing:
        if existing.keycloak_id and existing.keycloak_id != sub:
            logger.warning("Email %s already bound to another OIDC subject", email)
            return None
        if not existing.keycloak_id:
            # A bar number can grant access to sealed cases. Bind these accounts explicitly.
            if (
                existing.user_type in (UserType.ADMIN, UserType.CLERK, UserType.JUDGE)
                or existing.bar_number
            ):
                logger.warning(
                    "Refusing to auto-link OIDC sub=%s to privileged account %s; "
                    "an administrator must bind keycloak_id explicitly",
                    sub,
                    email,
                )
                return None
            existing.keycloak_id = sub
            sync_verified_email(existing, claims)
            await db.flush()
            await db.refresh(existing)
            return existing
        return existing

    user = User(
        email=email,
        verified_email=email,
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
