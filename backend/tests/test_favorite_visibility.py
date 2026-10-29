"""Favorites must not preserve case access after sealing or account revocation."""

from datetime import UTC, datetime

from app.models.case import Case, CaseParticipant, ParticipantRole
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.user import User, UserType


async def test_favorites_follow_current_case_access(db_session, api_client):
    court = Court(name="Favorite Court", county="Wayne", court_type=CourtType.CIRCUIT)
    owner = User(email="favorite@test.com", first_name="Favorite", last_name="Filer",
                 user_type=UserType.ATTORNEY)
    stranger = User(email="stranger@test.com", first_name="Stranger", last_name="Filer",
                    user_type=UserType.ATTORNEY)
    db_session.add_all([court, owner, stranger])
    await db_session.flush()
    case_type = CaseType(court_id=court.id, code="CIV", name="Civil", category=CaseCategory.CIVIL)
    db_session.add(case_type)
    await db_session.flush()
    case = Case(court_id=court.id, case_type_id=case_type.id, title="Private title",
                case_number="FAV-1", filed_date=datetime.now(UTC))
    db_session.add(case)
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(owner.id)
    added = await api_client.post("/api/v1/favorites", json={"case_id": case.id})
    assert added.status_code == 201
    case.is_sealed = True
    await db_session.flush()
    listing = await api_client.get("/api/v1/favorites")
    assert listing.json() == {"favorites": [], "total": 0}
    api_client.headers["X-Demo-User-Id"] = str(stranger.id)
    denied = await api_client.post("/api/v1/favorites", json={"case_id": case.id})
    assert denied.status_code == 404
    assert case.title not in denied.text

    participant = CaseParticipant(case_id=case.id, user_id=owner.id,
                                  role=ParticipantRole.PLAINTIFF, access_enabled=True,
                                  party_name="Owner")
    db_session.add(participant)
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(owner.id)
    permitted = await api_client.get("/api/v1/favorites")
    assert permitted.json()["favorites"][0]["case_title"] == case.title
    participant.access_enabled = False
    await db_session.flush()
    assert (await api_client.get("/api/v1/favorites")).json() == {"favorites": [], "total": 0}
    owner.is_active = False
    await db_session.flush()
    assert (await api_client.get("/api/v1/favorites")).status_code == 401
    assert (await api_client.get(f"/api/v1/cases/{case.id}")).status_code == 403


async def test_removing_favorites_is_idempotent(db_session, api_client):
    court = Court(name="Idempotent Court", county="Kent", court_type=CourtType.CIRCUIT)
    owner = User(email="twice@test.com", first_name="Twice", last_name="Filer",
                 user_type=UserType.ATTORNEY)
    db_session.add_all([court, owner])
    await db_session.flush()
    case_type = CaseType(court_id=court.id, code="CIV", name="Civil", category=CaseCategory.CIVIL)
    db_session.add(case_type)
    await db_session.flush()
    case = Case(court_id=court.id, case_type_id=case_type.id, title="Public title",
                case_number="FAV-2", filed_date=datetime.now(UTC))
    db_session.add(case)
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(owner.id)
    added = await api_client.post("/api/v1/favorites", json={"case_id": case.id})
    assert added.status_code == 201
    assert (await api_client.post(
        "/api/v1/favorites/courts", json={"court_id": court.id},
    )).status_code == 201
    # A second tab may already have removed it; the requested state still holds.
    for path in (f"/api/v1/favorites/{case.id}", f"/api/v1/favorites/courts/{court.id}") * 2:
        assert (await api_client.delete(path)).status_code == 204, path
    assert (await api_client.get("/api/v1/favorites")).json()["total"] == 0


async def test_duplicate_favorites_and_long_notes_are_client_errors(db_session, api_client):
    court = Court(name="Duplicate Court", county="Ingham", court_type=CourtType.CIRCUIT)
    owner = User(email="duplicate@test.com", first_name="Duplicate", last_name="Filer",
                 user_type=UserType.ATTORNEY)
    db_session.add_all([court, owner])
    await db_session.flush()
    case_type = CaseType(court_id=court.id, code="CIV", name="Civil", category=CaseCategory.CIVIL)
    db_session.add(case_type)
    await db_session.flush()
    case = Case(court_id=court.id, case_type_id=case_type.id, title="Starred twice",
                case_number="FAV-3", filed_date=datetime.now(UTC))
    db_session.add(case)
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(owner.id)
    # A request from a second tab reaches the unique constraint rather than a 500.
    for path, body in (("/api/v1/favorites", {"case_id": case.id}),
                       ("/api/v1/favorites/courts", {"court_id": court.id})):
        assert (await api_client.post(path, json=body)).status_code == 201
        again = await api_client.post(path, json=body)
        assert again.status_code == 409, again.text
        assert "already in favorites" in again.json()["detail"]
        # The notes column holds 500 characters.
        long = await api_client.post(path, json={**body, "notes": "x" * 501})
        assert long.status_code == 422, long.text
    assert (await api_client.get("/api/v1/favorites")).json()["total"] == 1
