from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user_id, require_user_may_manage_efilings
from app.database import get_db
from app.models.case import Case
from app.models.court import Court
from app.models.user import FavoriteCase, FavoriteCourt, User

router = APIRouter(prefix="/favorites", tags=["Favorites"])


class FavoriteCaseCreate(BaseModel):
    case_id: int
    notes: str | None = None


class FavoriteCaseResponse(BaseModel):
    id: int
    case_id: int
    case_number: str | None = None
    case_title: str | None = None
    notes: str | None
    created_at: str


class FavoriteCaseListResponse(BaseModel):
    favorites: list[FavoriteCaseResponse]
    total: int


class FavoriteCourtCreate(BaseModel):
    court_id: int
    notes: str | None = None


class FavoriteCourtResponse(BaseModel):
    id: int
    court_id: int
    court_name: str | None = None
    county: str | None = None
    court_type: str | None = None
    notes: str | None
    created_at: str


class FavoriteCourtListResponse(BaseModel):
    favorites: list[FavoriteCourtResponse]
    total: int


@router.get("", response_model=FavoriteCaseListResponse)
async def list_favorites(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(FavoriteCase)
        .options(selectinload(FavoriteCase.case))
        .where(FavoriteCase.user_id == user_id)
        .order_by(FavoriteCase.created_at.desc())
    )
    favorites = list(result.scalars().all())

    items = []
    for fav in favorites:
        case = fav.case
        items.append(FavoriteCaseResponse(
            id=fav.id,
            case_id=fav.case_id,
            case_number=case.case_number if case else None,
            case_title=case.title if case else None,
            notes=fav.notes,
            created_at=fav.created_at.isoformat() if fav.created_at else "",
        ))

    return FavoriteCaseListResponse(favorites=items, total=len(items))


@router.post("", response_model=FavoriteCaseResponse, status_code=status.HTTP_201_CREATED)
async def add_favorite(
    data: FavoriteCaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_may_manage_efilings),
):
    user_id = current_user.id
    # Check case exists
    case_result = await db.execute(select(Case).where(Case.id == data.case_id))
    case = case_result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # Check not already favorited
    existing = await db.execute(
        select(FavoriteCase).where(
            FavoriteCase.user_id == user_id,
            FavoriteCase.case_id == data.case_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Case already in favorites"
        )

    fav = FavoriteCase(user_id=user_id, case_id=data.case_id, notes=data.notes)
    db.add(fav)
    await db.flush()

    return FavoriteCaseResponse(
        id=fav.id,
        case_id=fav.case_id,
        case_number=case.case_number,
        case_title=case.title,
        notes=fav.notes,
        created_at=fav.created_at.isoformat() if fav.created_at else "",
    )


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_may_manage_efilings),
):
    user_id = current_user.id
    result = await db.execute(
        select(FavoriteCase).where(
            FavoriteCase.user_id == user_id,
            FavoriteCase.case_id == case_id,
        )
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorite not found")

    await db.delete(fav)
    await db.flush()


# --- Court Favorites ---

@router.get("/courts", response_model=FavoriteCourtListResponse)
async def list_favorite_courts(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(FavoriteCourt)
        .options(selectinload(FavoriteCourt.court))
        .where(FavoriteCourt.user_id == user_id)
        .order_by(FavoriteCourt.created_at.desc())
    )
    favorites = list(result.scalars().all())

    items = []
    for fav in favorites:
        court = fav.court
        items.append(FavoriteCourtResponse(
            id=fav.id,
            court_id=fav.court_id,
            court_name=court.name if court else None,
            county=court.county if court else None,
            court_type=court.court_type if court else None,
            notes=fav.notes,
            created_at=fav.created_at.isoformat() if fav.created_at else "",
        ))

    return FavoriteCourtListResponse(favorites=items, total=len(items))


@router.post("/courts", response_model=FavoriteCourtResponse, status_code=status.HTTP_201_CREATED)
async def add_favorite_court(
    data: FavoriteCourtCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_may_manage_efilings),
):
    user_id = current_user.id
    # Check court exists
    court_result = await db.execute(select(Court).where(Court.id == data.court_id))
    court = court_result.scalar_one_or_none()
    if not court:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Court not found")

    # Check not already favorited
    existing = await db.execute(
        select(FavoriteCourt).where(
            FavoriteCourt.user_id == user_id,
            FavoriteCourt.court_id == data.court_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Court already in favorites"
        )

    fav = FavoriteCourt(user_id=user_id, court_id=data.court_id, notes=data.notes)
    db.add(fav)
    await db.flush()

    return FavoriteCourtResponse(
        id=fav.id,
        court_id=fav.court_id,
        court_name=court.name,
        county=court.county,
        court_type=court.court_type,
        notes=fav.notes,
        created_at=fav.created_at.isoformat() if fav.created_at else "",
    )


@router.delete("/courts/{court_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite_court(
    court_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_may_manage_efilings),
):
    user_id = current_user.id
    result = await db.execute(
        select(FavoriteCourt).where(
            FavoriteCourt.user_id == user_id,
            FavoriteCourt.court_id == court_id,
        )
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorite not found")

    await db.delete(fav)
    await db.flush()
