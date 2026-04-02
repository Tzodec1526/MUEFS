"""Tests for court-related functionality."""

import pytest
from sqlalchemy import select

from app.models.court import CaseCategory, CaseType, Court, CourtType, FilingRequirement


@pytest.mark.asyncio
async def test_create_court(db_session):
    court = Court(
        name="3rd Circuit Court",
        county="Wayne",
        court_type=CourtType.CIRCUIT,
        city="Detroit",
        state="MI",
        zip_code="48226",
        cms_type="JIS",
        is_efiling_enabled=True,
    )
    db_session.add(court)
    await db_session.flush()

    result = await db_session.execute(select(Court).where(Court.id == court.id))
    saved = result.scalar_one()
    assert saved.name == "3rd Circuit Court"
    assert saved.county == "Wayne"
    assert saved.court_type == CourtType.CIRCUIT
    assert saved.is_efiling_enabled is True


@pytest.mark.asyncio
async def test_create_case_type(db_session):
    court = Court(
        name="Test Court",
        county="Test",
        court_type=CourtType.CIRCUIT,
    )
    db_session.add(court)
    await db_session.flush()

    case_type = CaseType(
        court_id=court.id,
        code="CIV",
        name="Civil - General",
        category=CaseCategory.CIVIL,
        filing_fee_cents=17500,
        description="General civil action",
    )
    db_session.add(case_type)
    await db_session.flush()

    result = await db_session.execute(select(CaseType).where(CaseType.court_id == court.id))
    saved = result.scalar_one()
    assert saved.code == "CIV"
    assert saved.filing_fee_cents == 17500
    assert saved.category == CaseCategory.CIVIL


@pytest.mark.asyncio
async def test_filing_requirement(db_session):
    court = Court(name="Test Court", county="Test", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()

    req = FilingRequirement(
        court_id=court.id,
        document_type_code="COMPLAINT",
        is_required=True,
        description="Complaint",
        mcr_reference="MCR 2.111",
    )
    db_session.add(req)
    await db_session.flush()

    result = await db_session.execute(
        select(FilingRequirement).where(FilingRequirement.court_id == court.id)
    )
    saved = result.scalar_one()
    assert saved.is_required is True
    assert saved.mcr_reference == "MCR 2.111"
