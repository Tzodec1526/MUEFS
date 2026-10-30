from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.court import Court
from app.models.user import User, UserCourtRole, UserType
from app.schemas.common import MAX_RECORD_ID
from app.schemas.user import CourtAssignment, UserCreate, UserProfile, UserResponse
from app.security.demo_auth import demo_headers_permitted
from app.services import access_service
from app.services.user_provision_service import provision_user_from_oidc, sync_verified_email
from app.utils.keycloak_jwt import (
    IdentityProviderUnavailableError,
    JWTError,
    decode_keycloak_access_token,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _identity_provider_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Sign-in verification is temporarily unavailable. Please retry shortly.",
        headers={"Retry-After": "30"},
    )


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    raw = authorization[7:].strip()
    return raw or None


async def _resolve_user(
    db: AsyncSession,
    authorization: str | None,
    x_demo_user_id: int | None,
    x_demo_auth_secret: str | None,
    *,
    required: bool,
) -> User | None:
    token = _bearer_token(authorization)

    def demo_permitted() -> bool:
        return (
            settings.allow_demo_mode
            and x_demo_user_id is not None
            and demo_headers_permitted(x_demo_auth_secret)
        )

    if token:
        try:
            claims = await decode_keycloak_access_token(token)
        except IdentityProviderUnavailableError:
            raise _identity_provider_unavailable() from None
        except JWTError:
            if required and not demo_permitted():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Your sign-in is invalid or has expired",
                ) from None
            claims = None
        if claims is not None:
            sub = claims.get("sub")
            if not sub and required:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Your sign-in could not be verified",
                )
            if sub:
                user = await db.scalar(select(User).where(User.keycloak_id == sub))
                if not user and settings.provision_user_on_first_oidc_login:
                    user = await provision_user_from_oidc(db, sub=sub, claims=claims)
                if not user and required:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="This account is not set up for this system",
                    )
                if user and not user.is_active and required:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Account disabled",
                    )
                if user and user.is_active:
                    sync_verified_email(user, claims)
                    return user

    if demo_permitted():
        user = await db.scalar(select(User).where(
            User.id == x_demo_user_id, User.is_active.is_(True),
        ))
        if user is None and required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This demo account is unknown or disabled",
            )
        return user

    return None


async def get_current_user(
    db: AsyncSession = Depends(get_db, scope="function"),
    authorization: str | None = Header(None),
    x_demo_user_id: int | None = Header(
        default=None, alias="X-Demo-User-Id", le=MAX_RECORD_ID,
    ),
    x_demo_auth_secret: str | None = Header(default=None, alias="X-Demo-Auth-Secret"),
) -> User:
    user = await _resolve_user(
        db, authorization, x_demo_user_id, x_demo_auth_secret, required=True,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


async def get_current_user_id(current_user: User = Depends(get_current_user)) -> int:
    return current_user.id


async def get_optional_user(
    db: AsyncSession = Depends(get_db, scope="function"),
    authorization: str | None = Header(None),
    x_demo_user_id: int | None = Header(
        default=None, alias="X-Demo-User-Id", le=MAX_RECORD_ID,
    ),
    x_demo_auth_secret: str | None = Header(default=None, alias="X-Demo-Auth-Secret"),
) -> User | None:
    return await _resolve_user(
        db, authorization, x_demo_user_id, x_demo_auth_secret, required=False,
    )


async def get_optional_user_id(user: User | None = Depends(get_optional_user)) -> int | None:
    return user.id if user else None


async def require_user_may_manage_efilings(current_user: User = Depends(get_current_user)) -> User:
    if current_user.user_type == UserType.PUBLIC:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=access_service.PUBLIC_ACCOUNT_REFUSAL,
        )
    return current_user


async def lock_current_user(db: AsyncSession, user_id: int) -> User:
    user = await db.scalar(
        select(User).where(User.id == user_id).with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="This account is no longer active")
    return user


@router.get("/me", response_model=UserProfile)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(
        select(UserCourtRole, Court.name)
        .join(Court, Court.id == UserCourtRole.court_id)
        .where(UserCourtRole.user_id == current_user.id)
    )
    assignments = [
        CourtAssignment(court_id=ucr.court_id, role=ucr.role, court_name=name)
        for ucr, name in result.all()
    ]
    profile = UserProfile.model_validate(current_user)
    return profile.model_copy(update={"court_assignments": assignments})


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db, scope="function"),
):
    if not settings.allow_public_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-registration is disabled. Sign in through your court identity provider.",
        )
    if await db.scalar(select(User.id).where(func.lower(User.email) == data.email.lower())):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    allowed_types = {UserType.ATTORNEY, UserType.SELF_REPRESENTED, UserType.PUBLIC}
    if data.user_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot self-register with this user type",
        )

    user = User(**data.model_dump())
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user
