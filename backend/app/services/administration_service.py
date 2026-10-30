from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.court import Court
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.schemas.administration import AccountChange, AccountUpdate, CourtRoleChange
from app.services import audit_service

ACCOUNT_FIELDS = (
    "first_name",
    "last_name",
    "email",
    "user_type",
    "keycloak_id",
    "is_active",
    "bar_number",
    "bar_number_verified",
)


def account_snapshot(user: User) -> dict:
    return {
        "id": user.id,
        **{field: getattr(user, field) for field in ACCOUNT_FIELDS},
        "administration_version": user.administration_version,
    }


def require_system_administrator(user: User) -> None:
    if not user.is_active or user.user_type != UserType.ADMIN:
        raise HTTPException(403, "System administrator access required")


async def require_court_administrator(db: AsyncSession, user: User, court_id: int) -> None:
    if not user.is_active:
        raise HTTPException(403, "Account disabled")
    if user.user_type != UserType.ADMIN and not await db.scalar(
        select(
            select(UserCourtRole.id)
            .where(
                UserCourtRole.user_id == user.id,
                UserCourtRole.court_id == court_id,
                UserCourtRole.role == CourtRole.ADMIN,
            )
            .exists()
        )
    ):
        raise HTTPException(403, "Administrator assignment for this court required")
    if await db.get(Court, court_id) is None:
        raise HTTPException(404, "Court not found")


async def _lock_users(
    db: AsyncSession, actor_id: int, target_id: int | None = None
) -> dict[int, User]:
    rows = await db.scalars(
        select(User)
        .where(User.id.in_([actor_id, target_id or actor_id]))
        .order_by(User.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return {user.id: user for user in rows}


async def create_account(
    db: AsyncSession,
    actor_id: int,
    data: AccountChange,
    *,
    context: dict,
) -> User:
    actor = (await _lock_users(db, actor_id))[actor_id]
    require_system_administrator(actor)
    _validate_identity(data)
    if await db.scalar(select(User.id).where(func.lower(User.email) == data.email)):
        raise HTTPException(409, "An account already uses this email address")
    user = User(**data.model_dump(include=set(ACCOUNT_FIELDS)))
    db.add(user)
    await db.flush()
    await audit_service.log_action(
        db,
        user_id=actor.id,
        action="identity.account_created",
        entity_type="user",
        entity_id=user.id,
        details={
            "reason": data.reason,
            "actor_name": actor.full_name,
            "before": None,
            "after": account_snapshot(user),
        },
        **context,
    )
    return user


async def _advance_version(db: AsyncSession, user: User, expected: int) -> None:
    version = await db.scalar(
        update(User)
        .where(
            User.id == user.id,
            User.administration_version == expected,
        )
        .values(administration_version=expected + 1)
        .returning(User.administration_version)
    )
    if version is None:
        raise HTTPException(409, "This account changed. Refresh it before saving")
    user.administration_version = version


def _validate_identity(data: AccountChange) -> None:
    if data.is_active and not data.keycloak_id and not settings.allow_demo_mode:
        raise HTTPException(422, "An active account requires its identity provider subject")


async def update_account(
    db: AsyncSession,
    actor_id: int,
    user_id: int,
    data: AccountUpdate,
    *,
    context: dict,
) -> User:
    users = await _lock_users(db, actor_id, user_id)
    actor, user = users[actor_id], users.get(user_id)
    require_system_administrator(actor)
    if user is None:
        raise HTTPException(404, "Account not found")
    if user.administration_version != data.expected_version:
        raise HTTPException(409, "This account changed. Refresh it before saving")
    _validate_identity(data)
    if actor.id == user.id and (
        data.user_type != user.user_type
        or not data.is_active
        or data.keycloak_id != user.keycloak_id
    ):
        raise HTTPException(409, "Another system administrator must change your own access")
    if await db.scalar(
        select(User.id).where(
            func.lower(User.email) == data.email,
            User.id != user.id,
        )
    ):
        raise HTTPException(409, "An account already uses this email address")
    before = account_snapshot(user)
    if (
        data.user_type != user.user_type or data.keycloak_id != user.keycloak_id
    ) and await db.scalar(
        select(UserCourtRole.id)
        .where(
            UserCourtRole.user_id == user.id,
            UserCourtRole.role != CourtRole.FILER,
        )
        .limit(1)
    ):
        raise HTTPException(
            409,
            "Revoke this account's court staff roles before changing its type "
            "or identity provider binding",
        )
    changes = data.model_dump(include=set(ACCOUNT_FIELDS))
    if all(getattr(user, field) == value for field, value in changes.items()):
        return user
    await _advance_version(db, user, data.expected_version)
    if user.email != data.email or user.keycloak_id != data.keycloak_id or not data.is_active:
        user.verified_email = None
    for field, value in changes.items():
        setattr(user, field, value)
    await db.flush()
    await audit_service.log_action(
        db,
        user_id=actor.id,
        action="identity.account_updated",
        entity_type="user",
        entity_id=user.id,
        details={
            "reason": data.reason,
            "actor_name": actor.full_name,
            "before": before,
            "after": account_snapshot(user),
        },
        **context,
    )
    return user


async def change_court_role(
    db: AsyncSession,
    actor_id: int,
    user_id: int,
    court_id: int,
    data: CourtRoleChange,
    *,
    context: dict,
) -> User:
    users = await _lock_users(db, actor_id, user_id)
    actor, user = users[actor_id], users.get(user_id)
    await require_court_administrator(db, actor, court_id)
    if user is None:
        raise HTTPException(404, "Account not found")
    if actor.id == user.id:
        raise HTTPException(409, "Another administrator must change your own court access")
    if user.administration_version != data.expected_version:
        raise HTTPException(
            409, "This account changed. Refresh it before changing its court access"
        )
    if actor.user_type != UserType.ADMIN and (
        data.role == CourtRole.ADMIN or user.user_type == UserType.ADMIN
    ):
        raise HTTPException(403, "Only system administrators can change administrator access")
    if data.action == "grant":
        if not user.is_active or user.user_type not in (
            UserType.CLERK,
            UserType.JUDGE,
            UserType.ADMIN,
        ):
            raise HTTPException(
                422, "Grant court access only to active staff accounts that are set up"
            )
        if not user.keycloak_id and not settings.allow_demo_mode:
            raise HTTPException(
                422, "Bind this staff account to its identity provider subject first"
            )
        if data.role == CourtRole.JUDGE and user.user_type != UserType.JUDGE:
            raise HTTPException(422, "Judicial access requires a judge account that is set up")
    query = select(UserCourtRole).where(
        UserCourtRole.user_id == user.id,
        UserCourtRole.court_id == court_id,
    )
    existing = list(await db.scalars(query.order_by(UserCourtRole.role)))
    before = [grant.role.value for grant in existing]
    grant = next((grant for grant in existing if grant.role == data.role), None)
    if (data.action == "grant") == (grant is not None):
        return user
    await _advance_version(db, user, data.expected_version)
    if data.action == "grant":
        db.add(UserCourtRole(user_id=user.id, court_id=court_id, role=data.role))
        after = sorted([*before, data.role.value])
    elif grant is not None:
        await db.execute(delete(UserCourtRole).where(UserCourtRole.id == grant.id))
        after = [role for role in before if role != data.role.value]
    await audit_service.log_action(
        db,
        user_id=actor.id,
        action="identity.role_granted" if data.action == "grant" else "identity.role_revoked",
        entity_type="user",
        entity_id=user.id,
        details={
            "reason": data.reason,
            "actor_name": actor.full_name,
            "court_id": court_id,
            "before": before,
            "after": after,
        },
        **context,
    )
    return user
