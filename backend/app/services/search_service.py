from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.case import Case, CaseParticipant, CaseStatus


def _escape_like(value: str) -> str:
    """Escape LIKE/ILIKE wildcard characters in user input."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def search_cases(
    db: AsyncSession,
    *,
    case_number: str | None = None,
    party_name: str | None = None,
    attorney_bar_number: str | None = None,
    court_id: int | None = None,
    status: CaseStatus | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[Case], int]:
    query = (
        select(Case)
        .options(selectinload(Case.participants))
        .where(Case.is_sealed.is_(False))
    )
    count_query = select(func.count()).select_from(Case).where(Case.is_sealed.is_(False))

    if case_number:
        escaped = _escape_like(case_number)
        query = query.where(Case.case_number.ilike(f"%{escaped}%"))
        count_query = count_query.where(Case.case_number.ilike(f"%{escaped}%"))

    if party_name:
        escaped = _escape_like(party_name)
        subq = select(CaseParticipant.case_id).where(
            CaseParticipant.party_name.ilike(f"%{escaped}%")
        )
        query = query.where(Case.id.in_(subq))
        count_query = count_query.where(Case.id.in_(subq))

    if attorney_bar_number:
        subq = select(CaseParticipant.case_id).where(
            CaseParticipant.attorney_bar_number == attorney_bar_number
        )
        query = query.where(Case.id.in_(subq))
        count_query = count_query.where(Case.id.in_(subq))

    if court_id:
        query = query.where(Case.court_id == court_id)
        count_query = count_query.where(Case.court_id == court_id)

    if status:
        query = query.where(Case.status == status)
        count_query = count_query.where(Case.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(Case.filed_date.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all()), total
