from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.case import Case, CaseParticipant, CaseStatus
from app.models.court import Court


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
    if (case_number or party_name) and db.get_bind().dialect.name == "postgresql":
        # A rare name and a statewide match need different plans. Cached generic
        # plans can make broad searches slower after adding trigram indexes.
        await db.execute(text("SET LOCAL plan_cache_mode = force_custom_plan"))
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
        .options(
            selectinload(Case.court).load_only(Court.name, Court.county),
            selectinload(Case.participants).load_only(
                CaseParticipant.id, CaseParticipant.case_id, CaseParticipant.party_name,
                CaseParticipant.role, CaseParticipant.attorney_bar_number,
                CaseParticipant.represented_party_name, CaseParticipant.is_active,
                raiseload=True,
            ),
        )
        .where(*filters)
        .order_by(Case.filed_date.desc(), Case.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total
