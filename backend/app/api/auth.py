from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserType
from app.schemas.user import UserCreate, UserProfile, UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


async def get_current_user_id(
    x_demo_user_id: int = Header(default=1, alias="X-Demo-User-Id"),
) -> int:
    """Demo mode: user ID comes from header. Production: decode JWT."""
    return x_demo_user_id


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.get("/me", response_model=UserProfile)
async def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    # Only allow non-privileged user types on self-registration
    allowed_types = {UserType.ATTORNEY, UserType.SELF_REPRESENTED}
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
