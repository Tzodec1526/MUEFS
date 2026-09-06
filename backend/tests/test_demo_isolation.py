"""Per-visitor demo isolation: each browser session gets its own copy of the seeded
template, and the per-session cap falls back to the shared sandbox."""

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.main import app
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingEnvelope
from app.models.user import User, UserType


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """Point the demo data dir at a temp folder and build a tiny seeded template."""
    monkeypatch.setenv("DEMO_DATA_DIR", str(tmp_path))
    import app.demo.session_db as sdb

    sdb._sessions_dir().mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{sdb._template_db()}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        court = Court(
            name="Demo Court", county="Wayne", court_type=CourtType.CIRCUIT,
            is_efiling_enabled=True,
        )
        s.add(court)
        s.flush()
        s.add(CaseType(
            court_id=court.id, code="C", name="Civil",
            category=CaseCategory.CIVIL, filing_fee_cents=100,
        ))
        s.add(User(
            email="filer@example.invalid", first_name="Demo", last_name="Filer",
            user_type=UserType.SELF_REPRESENTED,
        ))
        s.commit()
    engine.dispose()
    return sdb


async def test_demo_api_commits_to_the_visitors_copy_of_the_template(demo, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_db, demo.get_demo_db)

    async def session_request(scope, receive, send):
        scope.setdefault("state", {})["demo_sid"] = demo.resolve_sid(Request(scope))[0]
        await app(scope, receive, send)

    async with AsyncClient(
        transport=ASGITransport(session_request), base_url="http://test",
        headers={"X-Demo-User-Id": "1"},
    ) as client:
        client.cookies.set(demo.COOKIE_NAME, "a" * 32)
        response = await client.post("/api/v1/filings", json={
            "court_id": 1, "case_type_id": 1, "filing_type": "initial", "case_title": "A's filing",
        })
        assert response.status_code == 201, response.text
        filing_id = response.json()["id"]
        assert (await client.get("/api/v1/filings")).json()["total"] == 1

        client.cookies.set(demo.COOKIE_NAME, "b" * 32)
        assert (await client.get("/api/v1/courts/1")).json()["name"] == "Demo Court"
        assert (await client.get("/api/v1/filings")).json()["total"] == 0
        assert (await client.get(f"/api/v1/filings/{filing_id}")).status_code == 404

        client.cookies.set(demo.COOKIE_NAME, "a" * 32)
        filing = (await client.get(f"/api/v1/filings/{filing_id}")).json()
        assert filing["case_title"] == "A's filing"
    engine = create_engine(f"sqlite:///{demo._template_db()}")
    with Session(engine) as observer:
        assert observer.scalar(select(func.count()).select_from(FilingEnvelope)) == 0
    engine.dispose()


def test_capacity_falls_back_to_shared(demo, monkeypatch):
    monkeypatch.setattr("app.config.settings.demo_max_sessions", 1)
    demo.ensure_session_db("d" * 32)  # one private sandbox => at capacity

    class _Req:
        cookies: dict = {}

    sid, set_cookie = demo.resolve_sid(_Req())
    assert sid == demo.SHARED_SID
    assert set_cookie is False
