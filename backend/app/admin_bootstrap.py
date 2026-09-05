"""Bind the first system administrator using an authorized database operator session."""

import argparse
import asyncio

from sqlalchemy import func, or_, select, text

from app.config import settings
from app.database import async_session, engine
from app.models.user import User, UserType
from app.schemas.administration import AccountChange
from app.services.administration_service import ACCOUNT_FIELDS, account_snapshot
from app.services.audit_service import log_action


async def bootstrap(data: AccountChange) -> int:
    if not data.keycloak_id or data.user_type != UserType.ADMIN or not data.is_active:
        raise ValueError("Bootstrap requires an active administrator and an identity subject")
    if settings.demo_isolated_sessions:
        raise ValueError("Bootstrap operates on the shared database, not isolated demo sessions")
    async with async_session() as db:
        # There is no existing administrator row to lock on an empty deployment. Serialize
        # this one-time bootstrap before checking whether someone has already completed it.
        if db.bind.dialect.name == "postgresql":
            await db.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
        else:
            await db.execute(text("BEGIN IMMEDIATE"))
        if await db.scalar(
            select(User.id)
            .where(
                User.user_type == UserType.ADMIN,
                User.is_active.is_(True),
                User.keycloak_id.is_not(None),
            )
            .limit(1)
        ):
            raise ValueError(
                "A bound administrator already exists; use administration in the portal"
            )
        if await db.scalar(
            select(User.id).where(
                or_(
                    func.lower(User.email) == data.email,
                    User.keycloak_id == data.keycloak_id,
                )
            )
        ):
            raise ValueError("Bootstrap requires an unused email and identity subject")
        user = User(**data.model_dump(include=set(ACCOUNT_FIELDS)))
        db.add(user)
        await db.flush()
        await log_action(
            db,
            user_id=None,
            action="identity.bootstrap",
            entity_type="user",
            entity_id=user.id,
            details={
                "source": "database_operator_bootstrap",
                "reason": data.reason,
                "before": None,
                "after": account_snapshot(user),
            },
        )
        await db.commit()
        return user.id


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("email", "first-name", "last-name", "subject", "reason"):
        parser.add_argument(f"--{option}", required=True)
    arguments = parser.parse_args()
    try:
        user_id = await bootstrap(
            AccountChange(
                email=arguments.email,
                first_name=arguments.first_name,
                last_name=arguments.last_name,
                keycloak_id=arguments.subject,
                reason=arguments.reason,
                user_type=UserType.ADMIN,
            )
        )
        print(
            f"Created system administrator account {user_id}; "
            "identity verification remains with the IdP"
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
