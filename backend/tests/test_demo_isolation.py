"""Per-visitor demo isolation: each browser session gets its own copy of the seeded
template, and the per-session cap falls back to the shared sandbox."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.case import Case, CaseStatus
from app.models.court import CaseCategory, CaseType, Court, CourtType


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """Point the demo data dir at a temp folder and build a tiny seeded template."""
    monkeypatch.setenv("DEMO_DATA_DIR", str(tmp_path))
    import app.demo.session_db as sdb

    sdb._sessions_dir().mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{sdb._template_db()}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        court = Court(name="Demo Court", county="Wayne", court_type=CourtType.CIRCUIT)
        s.add(court)
        s.flush()
        s.add(CaseType(
            court_id=court.id, code="C", name="Civil",
            category=CaseCategory.CIVIL, filing_fee_cents=100,
        ))
        s.commit()
    engine.dispose()
    return sdb


async def _add_case(path, number):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add(Case(
            court_id=1, case_number=number, case_type_id=1,
            title="t", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
        ))
        await s.commit()
    await engine.dispose()


async def _count_cases(path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        n = len((await s.execute(select(Case))).scalars().all())
    await engine.dispose()
    return n


@pytest.mark.asyncio
async def test_sessions_are_isolated(demo):
    a = demo.ensure_session_db("a" * 32)
    b = demo.ensure_session_db("b" * 32)
    assert a != b

    await _add_case(a, "MI-A-1")
    assert await _count_cases(a) == 1
    assert await _count_cases(b) == 0  # B never sees A's filing


@pytest.mark.asyncio
async def test_template_is_copied_into_each_session(demo):
    # A fresh session starts from the seeded template (its court is present, no cases).
    a = demo.ensure_session_db("c" * 32)
    engine = create_async_engine(f"sqlite+aiosqlite:///{a}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        courts = len((await s.execute(select(Court))).scalars().all())
    await engine.dispose()
    assert courts == 1
    assert await _count_cases(a) == 0


def test_capacity_falls_back_to_shared(demo, monkeypatch):
    monkeypatch.setattr("app.config.settings.demo_max_sessions", 1)
    demo.ensure_session_db("d" * 32)  # one private sandbox => at capacity

    class _Req:
        cookies: dict = {}

    sid, set_cookie = demo.resolve_sid(_Req())
    assert sid == demo.SHARED_SID
    assert set_cookie is False
