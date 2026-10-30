from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.params import Page, RecordId
from app.database import get_db
from app.models.audit import AuditLog
from app.models.case import Case
from app.models.court import Court
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.schemas.administration import AccountChange, AccountUpdate, CourtRoleChange
from app.schemas.common import MAX_RECORD_ID
from app.services import administration_service as administration
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(prefix="/admin", tags=["Admin"])


@asynccontextmanager
async def _administration_transaction(db: AsyncSession) -> AsyncIterator[None]:
    try:
        async with db.begin_nested():
            yield
    except IntegrityError as exc:
        raise HTTPException(
            409, "This email address, identity subject or court grant is already assigned"
        ) from exc
    except DBAPIError as exc:
        # Authentication may have updated the actor's verified email before we take
        # ordered access locks. Let the operator refresh after an overlapping change;
        # never automatically replay an authority change or expose a database failure.
        if getattr(exc.orig, "sqlstate", None) == "40P01":
            raise HTTPException(
                409, "Another administration change overlapped this one. Refresh before retrying"
            ) from exc
        raise


async def _require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    administration.require_system_administrator(current_user)
    return current_user


@router.get("/stats")
async def get_system_stats(
    db: AsyncSession = Depends(get_db, scope="function"),
    _admin: User = Depends(_require_admin),
):
    totals = await db.execute(
        select(
            select(func.count()).select_from(Court).scalar_subquery().label("total_courts"),
            select(func.count()).select_from(User).scalar_subquery().label("total_users"),
            select(func.count()).select_from(Case).scalar_subquery().label("total_cases"),
            select(func.count())
            .select_from(FilingEnvelope)
            .scalar_subquery()
            .label("total_filings"),
            select(func.count())
            .select_from(FilingEnvelope)
            .where(
                FilingEnvelope.status.in_([FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW]),
            )
            .scalar_subquery()
            .label("pending_review"),
        )
    )
    return dict(totals.mappings().one())


@router.get("/audit-log")
async def get_audit_log(
    action: str | None = None,
    entity_type: str | None = None,
    user_id: int | None = Query(None, ge=1, le=MAX_RECORD_ID),
    page: Page = 1,
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db, scope="function"),
    _admin: User = Depends(_require_admin),
):
    query = select(AuditLog).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())

    if action:
        query = query.where(AuditLog.action == action)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    entries = result.scalars().all()

    return {
        "entries": [
            {
                "id": e.id,
                "user_id": e.user_id,
                "action": e.action,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "details": e.details,
                "ip_address": e.ip_address,
                "user_agent": e.user_agent,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            }
            for e in entries
        ],
        "page": page,
        "page_size": page_size,
    }


@router.get("/access")
async def administration_access(
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(get_current_user),
):
    system_admin = current_user.user_type == UserType.ADMIN
    query = select(Court.id, Court.name).order_by(Court.name, Court.id)
    if not system_admin:
        query = query.where(
            Court.id.in_(
                select(UserCourtRole.court_id).where(
                    UserCourtRole.user_id == current_user.id,
                    UserCourtRole.role == CourtRole.ADMIN,
                )
            )
        )
    courts = [dict(row) for row in (await db.execute(query)).mappings()]
    if not system_admin and not courts:
        raise HTTPException(403, "Administrator access required")
    return {"system_admin": system_admin, "courts": courts, "user_id": current_user.id}


async def _user_records(
    db: AsyncSession,
    users: list[User],
    *,
    include_identity: bool,
    court_id: int | None = None,
) -> list[dict]:
    grants: dict[int, list[dict]] = {}
    if users:
        query = (
            select(UserCourtRole, Court.name)
            .join(Court)
            .where(
                UserCourtRole.user_id.in_([user.id for user in users]),
            )
            .order_by(Court.name, UserCourtRole.role)
        )
        if court_id is not None and not include_identity:
            query = query.where(UserCourtRole.court_id == court_id)
        for role, court_name in await db.execute(query):
            grants.setdefault(role.user_id, []).append(
                {
                    "court_id": role.court_id,
                    "court_name": court_name,
                    "role": role.role,
                }
            )
    return [
        {
            **(
                administration.account_snapshot(user)
                if include_identity
                else {
                    "id": user.id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "user_type": user.user_type,
                    "is_active": user.is_active,
                    "administration_version": user.administration_version,
                }
            ),
            "court_roles": grants.get(user.id, []),
            **(
                {
                    "email_verified": bool(
                        user.verified_email and user.verified_email == user.email.lower()
                    )
                }
                if include_identity
                else {}
            ),
        }
        for user in users
    ]


@router.get("/users")
async def list_accounts(
    court_id: int | None = Query(None, ge=1, le=MAX_RECORD_ID),
    email: str | None = Query(default=None, max_length=255),
    page: Page = 1,
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(get_current_user),
):
    if court_id is None:
        administration.require_system_administrator(current_user)
    else:
        await administration.require_court_administrator(db, current_user, court_id)
    query = select(User)
    if email and email.strip():
        # Exact lookup lets court administrators add known staff without exposing a
        # statewide identity directory or other courts' assignments.
        query = query.where(func.lower(User.email) == email.strip().lower())
        if current_user.user_type != UserType.ADMIN:
            query = query.where(User.user_type.in_([UserType.CLERK, UserType.JUDGE]))
    elif court_id is not None:
        query = query.where(
            User.id.in_(
                select(UserCourtRole.user_id).where(
                    UserCourtRole.court_id == court_id,
                )
            )
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    users = list(await db.scalars(query.order_by(User.id.desc()).offset((page - 1) * 25).limit(25)))
    return {
        "users": await _user_records(
            db,
            users,
            court_id=court_id,
            include_identity=current_user.user_type == UserType.ADMIN,
        ),
        "total": total,
        "page": page,
        "page_size": 25,
    }


@router.post("/users", status_code=201)
async def provision_account(
    data: AccountChange,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(get_current_user),
):
    async with _administration_transaction(db):
        user = await administration.create_account(
            db,
            current_user.id,
            data,
            context={
                "ip_address": client_ip(request),
                "user_agent": client_user_agent(request),
            },
        )
    return (await _user_records(db, [user], include_identity=True))[0]


@router.put("/users/{user_id}")
async def change_account(
    user_id: RecordId,
    data: AccountUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(get_current_user),
):
    async with _administration_transaction(db):
        user = await administration.update_account(
            db,
            current_user.id,
            user_id,
            data,
            context={
                "ip_address": client_ip(request),
                "user_agent": client_user_agent(request),
            },
        )
    return (await _user_records(db, [user], include_identity=True))[0]


@router.post("/courts/{court_id}/users/{user_id}/roles")
async def change_role(
    court_id: RecordId,
    user_id: RecordId,
    data: CourtRoleChange,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(get_current_user),
):
    async with _administration_transaction(db):
        user = await administration.change_court_role(
            db,
            current_user.id,
            user_id,
            court_id,
            data,
            context={
                "ip_address": client_ip(request),
                "user_agent": client_user_agent(request),
            },
        )
    return (
        await _user_records(
            db, [user], court_id=court_id, include_identity=current_user.user_type == UserType.ADMIN
        )
    )[0]


@router.get("/users/{user_id}/history")
async def account_history(
    user_id: RecordId,
    court_id: int | None = Query(None, ge=1, le=MAX_RECORD_ID),
    page: Page = 1,
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(get_current_user),
):
    if court_id is None:
        administration.require_system_administrator(current_user)
    else:
        await administration.require_court_administrator(db, current_user, court_id)
    query = select(AuditLog).where(
        AuditLog.entity_type == "user",
        AuditLog.entity_id == user_id,
        AuditLog.action.startswith("identity."),
    )
    if court_id is not None:
        query = query.where(AuditLog.details["court_id"].as_integer() == court_id)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await db.scalars(query.order_by(AuditLog.id.desc()).offset((page - 1) * 25).limit(25))
    return {
        "events": [
            {
                "id": entry.id,
                "actor_id": entry.user_id,
                "action": entry.action,
                "details": entry.details,
                "occurred_at": entry.timestamp.isoformat(),
            }
            for entry in rows
        ],
        "total": total,
        "page": page,
        "page_size": 25,
    }
