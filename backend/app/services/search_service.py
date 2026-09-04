from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.case import Case, CaseParticipant, CaseStatus


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
    filters: list[ColumnElement[bool]] = [Case.is_sealed.is_(False)]

    if case_number:
        filters.append(Case.case_number.icontains(case_number, autoescape=True))

    if party_name:
        subq = select(CaseParticipant.case_id).where(
            CaseParticipant.party_name.icontains(party_name, autoescape=True)
        )
        filters.append(Case.id.in_(subq))

    if attorney_bar_number:
        subq = select(CaseParticipant.case_id).where(
            CaseParticipant.attorney_bar_number == attorney_bar_number
        )
        filters.append(Case.id.in_(subq))

    if court_id is not None:
        filters.append(Case.court_id == court_id)

    if status:
        filters.append(Case.status == status)

    count_query = select(func.count()).select_from(Case).where(*filters)
    total = (await db.execute(count_query)).scalar() or 0
    if not total:
        return [], 0
    query = (
        select(Case)
        .options(selectinload(Case.participants))
        .where(*filters)
        .order_by(Case.filed_date.desc(), Case.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total
