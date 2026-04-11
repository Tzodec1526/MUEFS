"""Provision internal User rows from OIDC token claims on first login.

Court deployments typically disable auto-provision (provision_user_on_first_oidc_login=false)
and use admin invite, SCIM, or batch import instead.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserType

logger = logging.getLogger(__name__)


async def provision_user_from_oidc(
    db: AsyncSession,
    *,
    sub: str,
    claims: dict,
) -> User | None:
    """Create or link a User for this Keycloak subject.

    Returns None if provisioning is impossible (e.g. missing email claim).
    """
    email = claims.get("email")
    if not email or not isinstance(email, str):
        logger.warning("OIDC token missing email claim; cannot auto-provision user sub=%s", sub)
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
