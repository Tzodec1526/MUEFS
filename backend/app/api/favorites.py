from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.database import get_db
from app.models.case import Case
from app.models.user import FavoriteCase

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


@router.get("", response_model=FavoriteCaseListResponse)
async def list_favorites(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(FavoriteCase).where(FavoriteCase.user_id == user_id).order_by(
            FavoriteCase.created_at.desc()
        )
    )
    favorites = list(result.scalars().all())

    items = []
    for fav in favorites:
        case_result = await db.execute(select(Case).where(Case.id == fav.case_id))
        case = case_result.scalar_one_or_none()
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
    user_id: int = Depends(get_current_user_id),
):
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
    user_id: int = Depends(get_current_user_id),
):
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
