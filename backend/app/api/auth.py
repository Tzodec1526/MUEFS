from fastapi import APIRouter, Depends, Header, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User, UserType
from app.schemas.user import UserCreate, UserProfile, UserResponse
from app.services.user_provision_service import provision_user_from_oidc
from app.utils.keycloak_jwt import decode_keycloak_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    raw = authorization[7:].strip()
    return raw or None


async def _resolve_demo_user_id(db: AsyncSession, x_demo_user_id: int) -> int:
    """Validate demo header user exists (court systems: no implicit default user)."""
    result = await db.execute(select(User.id).where(User.id == x_demo_user_id))
    uid = result.scalar_one_or_none()
    if uid is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown demo user id",
        )
    return uid


async def get_current_user_id(
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(None),
    x_demo_user_id: int | None = Header(default=None, alias="X-Demo-User-Id"),
) -> int:
    """Resolve the authenticated internal user id. Fail closed.

    - Production (allow_demo_mode=False): valid Keycloak Bearer JWT only; user must
      exist with matching keycloak_id (OIDC 'sub').
    - Demo (allow_demo_mode=True): JWT if valid and provisioned, else X-Demo-User-Id
      when the user id exists in the database (no default user).
    """
    token = _bearer_token(authorization)

    if token:
        try:
            claims = await decode_keycloak_access_token(token)
        except JWTError:
            if settings.allow_demo_mode and x_demo_user_id is not None:
                return await _resolve_demo_user_id(db, x_demo_user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            ) from None
        sub = claims.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )
        result = await db.execute(select(User).where(User.keycloak_id == sub))
        user = result.scalar_one_or_none()
        if not user and settings.provision_user_on_first_oidc_login:
            user = await provision_user_from_oidc(db, sub=sub, claims=claims)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not provisioned for this system",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account disabled",
            )
        return user.id

    if settings.allow_demo_mode and x_demo_user_id is not None:
        return await _resolve_demo_user_id(db, x_demo_user_id)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def require_user_may_manage_efilings(current_user: User = Depends(get_current_user)) -> User:
    """Public docket accounts may search and read non-sealed matters but not file or pay."""
    if current_user.user_type == UserType.PUBLIC:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public docket accounts cannot create or manage e-filings.",
        )
    return current_user


@router.get("/me", response_model=UserProfile)
async def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    # Court production: self-registration off; identities come from IdP or admin invite.
    if not settings.allow_public_registration and not settings.allow_demo_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-registration is disabled. Sign in through your court identity provider.",
        )
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    # Only allow non-privileged user types on self-registration
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
